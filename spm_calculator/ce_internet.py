"""Home internet spending for the CE in-kind replication.

BLS's FCSUti includes "home internet service expenditures"
(https://www.bls.gov/pir/spmhome.htm). The FMLI file has no internet
summary, so the out-of-pocket replication in
:mod:`spm_calculator.ce_threshold` omits it, and so do its archived receipt
and the canonical forecasts, whose code identities seal that module and
:mod:`spm_calculator.fcsuti_cpi`. This module adds home internet for the
research runs that compose the in-kind stage, without changing either
sealed module.

- Spending: CE Interview UCC 690114, "Computer information services",
  which BLS's CE-to-CPI concordance (CPI Handbook of Methods, Appendix 5,
  https://www.bls.gov/cpi/additional-resources/ce-cpi-concordance.htm)
  maps to ELI EE031, "Internet access and other information services".
  Each unit's cost is the sum of its MTBI records for that UCC in the
  same bundle and quarter as its FMLI record, gift records included as in
  FMLI's summaries. That is a three-month figure, on the same footing as
  the FMLI ``*PQ`` + ``*CQ`` pairs, and is annualized the same way.
- UCC 690116, "Internet services away from home", maps to the same ELI
  but stays out: BLS's methods page counts home internet service, and
  UCC 690114 alone reproduces BLS's in-band home internet for the 2019
  thresholds.
- Prices: CPI-U series CUUR0000SEEE03, "Internet services and electronic
  information providers", joins the FCSUti composite with the weight
  :func:`spm_calculator.fcsuti_cpi.compute_fcsuti_weights_from_ce` would
  give it: weighted three-month spending over units with children, as a
  share of the FCSUti total. The series is pinned in
  ``data/bls/cpi_internet_receipt.json`` by ``scripts/fetch_internet_cpi.py``.
- Internet enters FCSUti only, not shelter and utilities (SU).

Invariants, tested in ``tests/test_ce_internet.py``:

- zero internet spending reproduces the out-of-pocket run exactly;
- the composite price factor follows
  :func:`spm_calculator.fcsuti_cpi.get_fcsuti_inflation_factor` exactly
  when internet has no weight;
- the internet CPI weight is its expenditure share among units with
  children, and the other weights scale down in proportion;
- unit costs equal the sum of their MTBI UCC 690114 records.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from spm_calculator.ce_inkind_stage import (
    IN_KIND_OMITTED,
    OMITTED_APPROXIMATION,
    OutOfPocketRun,
    _digest,
)
from spm_calculator.ce_threshold import estimate_thresholds
from spm_calculator.equivalence_scale import REFERENCE_RAW_SCALE
from spm_calculator.fcsuti_cpi import CPI_SERIES, combine_cpi_series

#: CE Interview UCC for home internet ("Computer information services").
INTERNET_UCC = 690114
#: Column holding each unit's three-month UCC 690114 cost.
INTERNET_COLUMN = "internet_quarterly"
#: Name of the internet component in CPI weights.
INTERNET_COMPONENT = "internet"
#: CPI-U, internet services and electronic information providers, NSA.
INTERNET_CPI_SERIES = "CUUR0000SEEE03"
#: Pinned BLS API responses for :data:`INTERNET_CPI_SERIES`.
INTERNET_CPI_RECEIPT = (
    Path(__file__).parent / "data" / "bls" / "cpi_internet_receipt.json"
)
#: Prefix of methodology identifiers for runs with home internet added.
METHODOLOGY_PREFIX = "ce-fmli-internet-research-v1"

_ANNUALIZATION = {"quarter4": 4.0, "pqcq2": 2.0}
#: Approximations the out-of-pocket run records, as runs with home internet
#: record them. BLS applies an annual-average FCSUti CPI-U to quarterly CE
#: data (https://www.bls.gov/pir/spmhome.htm) and does not say which year's
#: average each quarter gets, so "quarterly treatment" overstates the
#: difference; the sealed module keeps its wording.
_APPROXIMATIONS = {
    OMITTED_APPROXIMATION: IN_KIND_OMITTED,
    "annual CPI by collection year instead of BLS quarterly treatment": (
        "annual-average CPI by collection year; BLS does not say which "
        "year's annual average each quarter gets"
    ),
}
_SETTINGS = {
    "implementation": "mtbi-ucc-690114-v1",
    "ucc": INTERNET_UCC,
    "cpi_series": INTERNET_CPI_SERIES,
    "cpi_weight": "weighted spending share, units with children",
    "enters": "fcsuti",
}


def mtbi_member(fmli_member: str) -> str:
    """The MTBI member that sits beside an FMLI member in a CE bundle."""
    head, slash, base = fmli_member.rpartition("/")
    if base[:4].lower() != "fmli":
        raise ValueError(f"Not an FMLI member: {fmli_member!r}")
    prefix = "MTBI" if base[:4].isupper() else "mtbi"
    return f"{head}{slash}{prefix}{base[4:]}"


def read_internet_costs(fmli: pd.DataFrame) -> pd.Series:
    """Each FMLI unit's three-month UCC 690114 cost, aligned to its rows.

    ``fmli`` must come from :func:`spm_calculator.ce_threshold.load_ce_quarter`,
    whose ``attrs["source"]`` names the bundle and member; the MTBI file is
    read from the same bundle and quarter. Units with no record get zero.
    """
    source = fmli.attrs.get("source") or {}
    bundle, member = source.get("bundle_path"), source.get("member")
    if not bundle or not member:
        raise ValueError(
            "FMLI frame lacks attrs['source'] from load_ce_quarter"
        )
    target = mtbi_member(member)
    with zipfile.ZipFile(bundle) as archive:
        if target not in archive.namelist():
            raise FileNotFoundError(f"{target} not found in {bundle}")
        with archive.open(target) as handle:
            mtbi = pd.read_csv(
                handle, usecols=["NEWID", "UCC", "COST"], low_memory=False
            )
    rows = mtbi.loc[
        pd.to_numeric(mtbi["UCC"], errors="coerce") == INTERNET_UCC
    ]
    cost = pd.to_numeric(rows["COST"], errors="raise").astype(float)
    if not np.isfinite(cost.to_numpy()).all():
        raise ValueError(f"{target}: UCC {INTERNET_UCC} costs must be finite")
    totals = cost.groupby(rows["NEWID"].to_numpy()).sum()
    newids = fmli["NEWID"]
    if not newids.is_unique:
        raise ValueError(f"{member}: NEWID repeats")
    unknown = totals.index.difference(pd.Index(newids))
    if len(unknown):
        raise ValueError(
            f"{target}: {len(unknown)} NEWIDs with UCC {INTERNET_UCC} "
            f"are not in {member}"
        )
    values = totals.reindex(newids.to_numpy(), fill_value=0.0).to_numpy()
    return pd.Series(values, index=fmli.index, name=INTERNET_COLUMN)


def load_internet_cpi(path: Path = INTERNET_CPI_RECEIPT) -> pd.Series:
    """Annual averages (period M13) of :data:`INTERNET_CPI_SERIES`."""
    document = json.loads(Path(path).read_text())
    if document.get("series_id") != INTERNET_CPI_SERIES:
        raise ValueError(f"{path} does not hold {INTERNET_CPI_SERIES}")
    values: dict[int, float] = {}
    for exchange in document["exchanges"]:
        for series in exchange["response"]["Results"]["series"]:
            if series["seriesID"] != INTERNET_CPI_SERIES:
                raise ValueError(f"{path}: unexpected {series['seriesID']}")
            for row in series["data"]:
                if row["period"] != "M13":
                    continue
                year = int(row["year"])
                if year in values:
                    raise ValueError(f"{path}: two annual values for {year}")
                values[year] = float(row["value"])
    if not values:
        raise ValueError(f"{path}: no annual averages")
    return pd.Series(values, name=INTERNET_CPI_SERIES).sort_index()


def with_internet_cpi(
    cpi_series: Mapping[str, pd.Series], internet: pd.Series | None = None
) -> dict[str, pd.Series]:
    """CPI series by BLS id, with the pinned internet series added."""
    if INTERNET_CPI_SERIES in cpi_series:
        raise ValueError(f"{INTERNET_CPI_SERIES} is already present")
    series = load_internet_cpi() if internet is None else internet
    return {**cpi_series, INTERNET_CPI_SERIES: series}


def _series_id(component: str) -> str:
    if component == INTERNET_COMPONENT:
        return INTERNET_CPI_SERIES
    return CPI_SERIES[component]


def composite_inflation_factor(
    from_year: int,
    to_year: int,
    weights: Mapping[str, float],
    cpi_series: Mapping[str, pd.Series],
) -> float:
    """FCSUti price factor between two years, internet included.

    Follows :func:`spm_calculator.fcsuti_cpi.get_fcsuti_inflation_factor`
    step for step (same range, base year and weight order), so without an
    internet weight it returns the same float.
    """
    if from_year == to_year:
        return 1.0
    components = {
        component: cpi_series[_series_id(component)] for component in weights
    }
    composite = combine_cpi_series(
        components,
        weights,
        min(from_year, to_year),
        max(from_year, to_year),
        from_year,
    )
    factor = float(composite[to_year] / composite[from_year])
    if not np.isfinite(factor) or factor <= 0:
        raise ValueError(
            f"FCSUti factor for ({from_year}, {to_year}) must be finite "
            "and positive"
        )
    return factor


def internet_cpi_weights(
    frame: pd.DataFrame, weights: Mapping[str, float]
) -> dict[str, float]:
    """Add internet to CE-derived FCSUti CPI weights.

    ``weights`` are the shares
    :func:`spm_calculator.fcsuti_cpi.compute_fcsuti_weights_from_ce` gave
    for ``frame``. Telephone's share and its weighted total recover the
    FCSUti total, so internet's share is its weighted total over that
    total plus itself, and the others scale down in proportion. Without
    internet spending the weights come back unchanged.
    """
    with_children = frame.loc[frame["PERSLT18"] > 0]
    survey = with_children["FINLWT21"].to_numpy(dtype=float)
    internet = float(
        np.sum(with_children[INTERNET_COLUMN].to_numpy() * survey)
    )
    if internet == 0:
        return dict(weights)
    telephone = float(
        np.sum(
            (
                with_children["TELEPHPQ"].fillna(0).to_numpy()
                + with_children["TELEPHCQ"].fillna(0).to_numpy()
            )
            * survey
        )
    )
    if weights.get("telephone", 0) <= 0 or telephone <= 0:
        raise ValueError("Internet weights need positive telephone spending")
    ratio = internet * weights["telephone"] / telephone
    out = {
        component: value / (1 + ratio) for component, value in weights.items()
    }
    out[INTERNET_COMPONENT] = ratio / (1 + ratio)
    if not all(np.isfinite(v) and v > 0 for v in out.values()):
        raise ValueError(f"Invalid FCSUti weights with internet: {out}")
    return out


def expenditures_with_internet(
    expenditures: pd.DataFrame,
    construction: Mapping,
    target_year: int,
    cpi_series: Mapping[str, pd.Series],
) -> tuple[pd.DataFrame, dict[str, float], dict[int, float]]:
    """Normalized expenditures with home internet added to FCSUti.

    ``expenditures`` and ``construction`` come from
    :func:`spm_calculator.ce_threshold.construct_normalized_expenditures`,
    with :data:`INTERNET_COLUMN` carried through from the FMLI records.
    The CPI weights gain internet, every unit's price factor is
    recomputed, FCSUti gains the annualized internet cost, and SU keeps its
    spending at the new price factor. Returns the frame, the CPI weights
    and the price factors by collection year.
    """
    annual = _ANNUALIZATION[construction["annualization"]]
    frame = expenditures.copy()
    if INTERNET_COLUMN not in frame:
        raise ValueError(f"Expenditures lack {INTERNET_COLUMN}")
    cost = frame[INTERNET_COLUMN].to_numpy(dtype=float)
    if not np.isfinite(cost).all():
        raise ValueError(f"{INTERNET_COLUMN} must be finite")
    weights = internet_cpi_weights(
        frame, construction["cpi_component_weights"]
    )
    factors = {
        int(year): composite_inflation_factor(
            int(year), int(target_year), weights, cpi_series
        )
        for year in sorted(frame["ce_year"].unique())
    }
    previous = frame["inflation_factor"]
    frame["inflation_factor"] = frame["ce_year"].map(factors)
    frame["fcsuti"] = frame["fcsuti"] + frame[INTERNET_COLUMN] * annual
    frame["fcsuti_threshold_year"] = (
        frame["fcsuti"] * frame["inflation_factor"]
    )
    # Same association as construct_normalized_expenditures, so zero
    # internet reproduces its floats exactly.
    scale = REFERENCE_RAW_SCALE / frame["equiv_scale"]
    frame["fcsuti_2a2c"] = frame["fcsuti_threshold_year"] * scale
    frame["su_2a2c"] = frame["su_2a2c"] * (
        frame["inflation_factor"] / previous
    )
    if not np.isfinite(frame[["fcsuti_2a2c", "su_2a2c"]].to_numpy()).all():
        raise ValueError("Expenditures with internet contain nonfinite values")
    return frame, weights, factors


def add_home_internet(
    run: OutOfPocketRun, cpi_series: Mapping[str, pd.Series]
) -> OutOfPocketRun:
    """The out-of-pocket run with home internet added to FCSUti.

    ``run.expenditures`` must carry :data:`INTERNET_COLUMN`; ``cpi_series``
    must hold :data:`INTERNET_CPI_SERIES` beside the package's FCSUti
    series (see :func:`with_internet_cpi`). See
    :func:`expenditures_with_internet` for the frame. The result has the
    same form, so the in-kind stage applies to it unchanged; the
    out-of-pocket thresholds ride along under ``without_home_internet``.
    """
    result, construction = run.result, run.result["construction"]
    approximations = list(construction["approximations"])
    if OMITTED_APPROXIMATION not in approximations:
        raise ValueError("Run does not omit home internet")
    frame, weights, factors = expenditures_with_internet(
        run.expenditures, construction, result["target_year"], cpi_series
    )
    thresholds, estimation = estimate_thresholds(frame, run.median_share)
    config = {**result["methodology_config"], "home_internet": dict(_SETTINGS)}
    annual = _ANNUALIZATION[construction["annualization"]]
    cost = frame[INTERNET_COLUMN].to_numpy(dtype=float)
    survey = frame["ce_weight"].to_numpy(dtype=float)
    annual_threshold_year = (
        cost * annual * frame["inflation_factor"].to_numpy()
    )
    summary = {
        **_SETTINGS,
        "cpi_weight": weights.get(INTERNET_COMPONENT, 0.0),
        "weighted_share_reporting": float(
            np.sum(survey * (cost != 0)) / np.sum(survey)
        ),
        "weighted_mean_threshold_year_dollars": float(
            np.average(annual_threshold_year, weights=survey)
        ),
        "units_with_negative_cost": int(np.sum(cost < 0)),
    }
    return OutOfPocketRun(
        {
            **result,
            "methodology_id": f"{METHODOLOGY_PREFIX}:{_digest(config)}",
            "methodology_config": config,
            "thresholds": thresholds,
            "construction": {
                **construction,
                "cpi_component_weights": weights,
                "inflation_factors": factors,
                "approximations": [
                    _APPROXIMATIONS.get(item, item) for item in approximations
                ],
                "home_internet": summary,
            },
            "estimation": estimation,
            "without_home_internet": {
                "methodology_id": result["methodology_id"],
                "thresholds": result["thresholds"],
            },
        },
        frame,
        run.median_share,
    )
