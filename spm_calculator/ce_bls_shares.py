"""BLS's published threshold components beside the replication's.

BLS publishes, for each threshold year and housing tenure, the share of the
SPM threshold each component supplies, based on the components' values
within the percentile band behind the thresholds
(https://www.bls.gov/pir/spm/spm_shares.xlsx). It also publishes each
year's weighted distribution of consumer units by tenure
(https://www.bls.gov/pir/spm/spm_thresholds.xlsx). A threshold

    T_h = m (1.2 F - SU + SU_h)

with F = C + SU, where C sums the components every tenure shares (food,
clothing, telephone, internet and the benefits that pay for them) and SU
sums shelter and utilities, rearranges to two identities:

    T_h / m = C + SU_h + 0.2 F          (1)
    F = C + sum_h P_h SU_h              (2)

So a share times ``T_h / m`` gives a component's in-band dollars, and the
"Other" share gives ``0.2 F``. :func:`bls_band_components` checks both
identities against BLS's published values. They hold to a fraction of a
cent in every year from 2019 to 2025. The identities cannot pin down the
mix themselves: other mixes that sum to one also satisfy (2). The mix comes
from footnote 3 of BLS's thresholds workbooks, which defines each tenure's
percentage as its share of the consumer units with children in the
47th-53rd percentile band.

:class:`BandComponents` holds the same quantities for BLS and for the
replication, so :func:`level_gap` can split the difference between two
thresholds term by term, with no assumption about either band.

A threshold's terms can treat ``0.2 F`` in two ways (:data:`ACCOUNTINGS`).
``"other_spread"`` gives each component its part of the 1.2 multiplier, so
a component's term is what the threshold would lose without it, with the
band held fixed. ``"other_separate"`` keeps ``0.2 F`` as an ``"other"`` term
of its own, as BLS's workbook does in its "Other Share" row, so each
component's term is its share of the threshold as BLS publishes it. Both
sum to the threshold.

The internet term needs care. Through 2024 the workbook's "OOP Internet"
row holds equal dollars across tenures and "Total Internet Share" does not;
in 2025 the reverse holds. Identity (2) balances with the row that holds
equal dollars, and the leaf rows sum to one except in 2023 and 2024, when
they exceed it by exactly the broadband row. So the tenure-invariant row
already includes broadband, and :func:`bls_band_components` takes home
internet spending as that row less the band's mean broadband subsidy.

Invariants, tested in ``tests/test_ce_bls_shares.py``:

- :func:`band_mask` selects the rows of
  :func:`spm_calculator.ce_threshold.estimate_thresholds`;
- a unit's components sum to its FCSUti, and its shelter, utilities, LIHEAP
  and rental assistance to its SU;
- :meth:`BandComponents.threshold` reproduces ``estimate_thresholds``, and
  the same mean over implicates reproduces the mean threshold;
- under either accounting, a threshold's terms sum to the threshold, and
  :func:`level_gap`'s terms sum to the difference between two thresholds;
- under ``"other_separate"``, BLS's terms over its thresholds reproduce its
  published shares (:func:`separate_share_errors`);
- imputed and non-imputed shares of growth beyond inflation sum to one;
- :func:`apply_bls_paper_definition` lowers each unit's FCSUti by exactly
  the amounts it removes, and a second application changes nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from spm_calculator.ce_threshold import (
    MEDIAN_SHARE,
    _food_expenditure,
    _sum_pair,
)
from spm_calculator.equivalence_scale import REFERENCE_RAW_SCALE

TENURES = ("renter", "owner_with_mortgage", "owner_without_mortgage")
#: Components every tenure shares in a threshold.
COMMODITIES = (
    "food",
    "clothing",
    "telephone",
    "internet",
    "nslp",
    "wic",
    "broadband",
)
#: Components that set the tenure-specific part of a threshold.
SHELTER_UTILITIES = ("shelter", "utilities", "rental_assistance", "liheap")
COMPONENTS = COMMODITIES + SHELTER_UTILITIES
#: The imputed in-kind benefits.
IMPUTED = ("nslp", "wic", "liheap", "broadband", "rental_assistance")
#: Components BLS reports separately by tenure.
TENURE_COMPONENTS = SHELTER_UTILITIES + ("broadband",)
#: How threshold terms treat ``0.2 F``: spread across the components in
#: proportion to their size, or kept as its own :data:`OTHER` term.
ACCOUNTINGS = ("other_spread", "other_separate")
#: The term that holds ``0.2 F`` under ``"other_separate"``.
OTHER = "other"

SHARES_WORKBOOK = "data/current/bls_spm_shares.xlsx"
#: Dollars of disagreement the published-value checks accept.
PUBLISHED_TOLERANCE = 0.01

_TENURE_SECTIONS = {
    "Owners with mortgages": "owner_with_mortgage",
    "Owners without mortgages": "owner_without_mortgage",
    "Renters": "renter",
}
_ROWS = {
    "oop food": "food",
    "nslp": "nslp",
    "wic": "wic",
    "total clothing share": "clothing",
    "oop shelter": "shelter",
    "rental assistance": "rental_assistance",
    "oop utilities (no telephone)": "utilities",
    "liheap": "liheap",
    "total telephone share": "telephone",
    "oop internet": "internet_oop_row",
    "broadband subsidy": "broadband",
    "total internet share": "internet_total_row",
    "other share": "other",
}
#: FMLI summaries the replication's shelter holds beyond BLS's written
#: definition, or food beyond it.
_REMOVED_PAIRS = {
    "other_lodging": ("OTHLODPQ", "OTHLODCQ"),
    "rent_as_pay": ("RNTAPYPQ", "RNTAPYCQ"),
    "meals_as_pay": ("FDMAPPQ", "FDMAPCQ"),
    "vacation_home_principal": ("MRTPRNOP", "MRTPRNOC"),
}
#: FMLI summaries of vacation-home utilities, which ``UTIL`` holds, as
#: (owned vacation homes, rented vacation homes) for each ``UTIL`` column.
_VACATION_UTILITIES = {
    "UTILPQ": ("UTILOWNP", "UTILRNTP"),
    "UTILCQ": ("UTILOWNC", "UTILRNTC"),
}
#: ``CUTENURE`` codes for owners: with a mortgage, without one, and with
#: mortgage status not reported.
OWNER_CODES = (1, 2, 3)
#: The FMLI columns that hold amounts the definition removes.
_REMOVED_COLUMNS = tuple(
    column for pair in _REMOVED_PAIRS.values() for column in pair
) + tuple(column for pair in _VACATION_UTILITIES.values() for column in pair)
#: The FMLI columns :func:`band_definition_pieces` and
#: :func:`apply_bls_paper_definition` read, beyond the replication's own.
DEFINITION_COLUMNS = _REMOVED_COLUMNS + (
    "OWNDWEPQ",
    "OWNDWECQ",
    "RNTXRPPQ",
    "RNTXRPCQ",
)
#: The columns :func:`apply_bls_paper_definition` and
#: :func:`removed_by_bls_paper_definition` need.
_DEFINITION_INPUTS = (
    ("CUTENURE",) + tuple(_VACATION_UTILITIES) + _REMOVED_COLUMNS
)


def _normal_label(label: str) -> str:
    return re.sub(r"[\s,\d]+$", "", label).strip().lower()


def read_threshold_shares(
    path: Optional[Path] = None,
    years: Sequence[int] = range(2019, 2026),
) -> dict[int, dict[str, dict[str, float]]]:
    """Read BLS's threshold shares as year -> tenure -> row -> share.

    Year 2019 reads the workbook's "2019 Revised" column. BLS's "n/a"
    reads as zero, the value those rows add to a threshold.
    """
    import openpyxl

    if path is None:
        path = resources.files("spm_calculator").joinpath(SHARES_WORKBOOK)
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = list(workbook.worksheets[0].values)
    finally:
        workbook.close()
    sections: dict[str, dict[str, dict[str, object]]] = {}
    tenure, header = None, None
    for row in rows:
        first = row[0]
        if not isinstance(first, str):
            continue
        if first.strip() in _TENURE_SECTIONS:
            tenure, header = _TENURE_SECTIONS[first.strip()], None
            sections[tenure] = {}
        elif first.strip() == "SPM Component":
            header = [None if v is None else str(v) for v in row[1:]]
        elif tenure is not None and header is not None:
            key = _ROWS.get(_normal_label(first))
            if key is not None:
                sections[tenure][key] = {
                    h: v for h, v in zip(header, row[1:]) if h is not None
                }
    shares: dict[int, dict[str, dict[str, float]]] = {}
    for year in years:
        column = "2019 Revised" if year == 2019 else str(year)
        shares[year] = {}
        for name in TENURES:
            section = sections.get(name, {})
            missing = sorted(set(_ROWS.values()) - set(section))
            if missing:
                raise ValueError(
                    f"BLS shares workbook has no rows {missing} for {name}"
                )
            shares[year][name] = {}
            for key, cells in section.items():
                if column not in cells:
                    raise ValueError(f"BLS shares lack column {column!r}")
                value = cells[column]
                shares[year][name][key] = (
                    float(value) if isinstance(value, (int, float)) else 0.0
                )
    return shares


def band_mask(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Rows in the 47th-53rd percentile band of ``estimate_thresholds``.

    ``ce_threshold.py`` stays byte-identical because the canonical forecast
    seals its code identity, so this repeats the selection, and a
    differential test holds the two together. That covers the estimator's
    fallback to the row nearest the median when the band is empty.

    Raises:
        ValueError: On the inputs the estimator rejects: no rows, a
            nonfinite value or weight, or a weight that is not positive.
    """
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if values.size == 0 or values.shape != weights.shape:
        raise ValueError("Band selection needs one weight per value")
    if not (np.isfinite(values) & np.isfinite(weights) & (weights > 0)).all():
        raise ValueError(
            "Estimation values must be finite with positive weights"
        )
    order = np.argsort(values, kind="stable")
    cumulative = np.cumsum(weights[order])
    cdf = (cumulative - weights[order] / 2) / cumulative[-1]
    in_range = (cdf >= 0.47) & (cdf <= 0.53)
    if not in_range.any():
        in_range[np.argmin(np.abs(cdf - 0.5))] = True
    mask = np.zeros(len(values), dtype=bool)
    mask[order[in_range]] = True
    return mask


def _quarterly_factor(frame: pd.DataFrame) -> np.ndarray:
    """Carry a PQ + CQ pair to annual threshold-year 2A2C dollars."""
    return (
        4.0
        * frame["inflation_factor"].to_numpy(dtype=float)
        * (REFERENCE_RAW_SCALE / frame["equiv_scale"]).to_numpy(dtype=float)
    )


def unit_components(frame: pd.DataFrame) -> pd.DataFrame:
    """Each unit's threshold components in threshold-year 2A2C dollars.

    Args:
        frame: Normalized expenditures from
            :func:`spm_calculator.ce_inkind_stage.prepare_out_of_pocket`,
            built with its default principal and annualization options, or
            that frame after
            :func:`spm_calculator.ce_inkind_stage.add_in_kind`.

    Raises:
        ValueError: If a component, ``fcsuti_2a2c`` or ``su_2a2c`` is not
            finite, or the components do not sum to the last two.
    """
    quarterly = _quarterly_factor(frame)
    telephone = _sum_pair(frame, "TELEPHPQ", "TELEPHCQ").to_numpy(dtype=float)
    shelter = _sum_pair(frame, "SHELTPQ", "SHELTCQ").to_numpy(dtype=float)
    for pq, cq in (("EMRTPNOP", "EMRTPNOC"), ("MRTPRNOP", "MRTPRNOC")):
        if pq in frame or cq in frame:
            shelter = shelter + _sum_pair(frame, pq, cq).to_numpy(dtype=float)
    utilities = _sum_pair(frame, "UTILPQ", "UTILCQ").to_numpy(dtype=float)
    out = pd.DataFrame(
        {
            "food": _food_expenditure(frame).to_numpy(dtype=float) * quarterly,
            "clothing": _sum_pair(frame, "APPARPQ", "APPARCQ").to_numpy(
                dtype=float
            )
            * quarterly,
            "telephone": telephone * quarterly,
            "internet": 0.0,
            "shelter": shelter * quarterly,
            "utilities": (utilities - telephone) * quarterly,
        },
        index=frame.index,
    )
    annual = quarterly / 4.0
    for component in IMPUTED:
        column = f"in_kind_{component}"
        out[component] = (
            frame[column].to_numpy(dtype=float) * annual
            if column in frame
            else 0.0
        )
    fcsuti = frame["fcsuti_2a2c"].to_numpy(dtype=float)
    su = frame["su_2a2c"].to_numpy(dtype=float)
    values = out[list(COMPONENTS)].to_numpy(dtype=float)
    if not (
        np.isfinite(values).all()
        and np.isfinite(fcsuti).all()
        and np.isfinite(su).all()
    ):
        raise ValueError("Unit components, FCSUti and SU must be finite")
    fcsuti_error = np.abs(
        out[list(COMPONENTS)].sum(axis=1).to_numpy() - fcsuti
    )
    su_error = np.abs(out[list(SHELTER_UTILITIES)].sum(axis=1).to_numpy() - su)
    if max(fcsuti_error.max(), su_error.max()) > 1e-6:
        raise ValueError(
            "Unit components do not sum to the frame's FCSUti and SU; "
            "was the frame built with default annualization and principal?"
        )
    return out


@dataclass(frozen=True)
class BandComponents:
    """Band means of threshold components, in threshold-year 2A2C dollars.

    Attributes:
        pooled: Every component's mean over the whole band.
        by_tenure: :data:`TENURE_COMPONENTS` means within each tenure.
        tenure_mix: Each tenure's weighted share of the band.
        median_share: The share of the band mean a threshold uses.
    """

    pooled: Mapping[str, float]
    by_tenure: Mapping[str, Mapping[str, float]]
    tenure_mix: Mapping[str, float]
    median_share: float = MEDIAN_SHARE

    @property
    def fcsuti(self) -> float:
        return float(sum(self.pooled[c] for c in COMPONENTS))

    @property
    def imputed_total(self) -> float:
        """Mean imputed benefits per consumer unit in the band."""
        return float(sum(self.pooled[c] for c in IMPUTED))

    def threshold_terms(
        self, tenure: str, accounting: str = "other_spread"
    ) -> dict[str, float]:
        """Each component's dollars in the tenure's threshold.

        Under ``"other_separate"`` the terms also hold :data:`OTHER`, and
        broadband takes the tenure's own mean, as BLS's workbook rows do.
        Home internet takes the rest of the two's shared total, so the
        terms still sum to the threshold.
        """
        share = self.median_share
        _check_accounting(accounting)
        if accounting == "other_separate":
            terms = {c: share * self.pooled[c] for c in COMMODITIES}
            for component in SHELTER_UTILITIES:
                terms[component] = share * self.by_tenure[tenure][component]
            own = self.by_tenure[tenure]["broadband"]
            terms["internet"] += share * (self.pooled["broadband"] - own)
            terms["broadband"] = share * own
            terms[OTHER] = share * 0.2 * self.fcsuti
            return terms
        terms = {c: share * 1.2 * self.pooled[c] for c in COMMODITIES}
        for component in SHELTER_UTILITIES:
            terms[component] = share * (
                self.by_tenure[tenure][component]
                + 0.2 * self.pooled[component]
            )
        return terms

    def threshold(self, tenure: str) -> float:
        return float(sum(self.threshold_terms(tenure).values()))

    def imputed_term(
        self, tenure: str, accounting: str = "other_spread"
    ) -> float:
        """The imputed benefits' dollars in the tenure's threshold."""
        terms = self.threshold_terms(tenure, accounting)
        return float(sum(terms[c] for c in IMPUTED))

    def to_dict(self) -> dict:
        return {
            "pooled": dict(self.pooled),
            "by_tenure": {t: dict(self.by_tenure[t]) for t in TENURES},
            "tenure_mix": dict(self.tenure_mix),
        }


def band_components(
    frame: pd.DataFrame, median_share: float = MEDIAN_SHARE
) -> BandComponents:
    """The replication's in-band components, for one frame.

    Means in a tenure with no band rows take the pooled mean, as
    ``estimate_thresholds`` does for SU.
    """
    units = unit_components(frame)
    weights = frame["ce_weight"].to_numpy(dtype=float)
    mask = band_mask(frame["fcsuti_2a2c"].to_numpy(dtype=float), weights)
    tenure = frame["tenure_type"].to_numpy(dtype=object)
    band_weight = weights[mask]
    pooled = {
        c: float(np.average(units[c].to_numpy()[mask], weights=band_weight))
        for c in COMPONENTS
    }
    by_tenure, mix = {}, {}
    for name in TENURES:
        use = mask & (tenure == name)
        mix[name] = float(weights[use].sum() / band_weight.sum())
        by_tenure[name] = {
            c: (
                float(
                    np.average(units[c].to_numpy()[use], weights=weights[use])
                )
                if use.any()
                else pooled[c]
            )
            for c in TENURE_COMPONENTS
        }
    return BandComponents(pooled, by_tenure, mix, median_share)


def mean_components(items: Sequence[BandComponents]) -> BandComponents:
    """The mean of each field, for averaging over implicates.

    Thresholds are linear in these fields, so the mean's threshold equals
    the mean threshold.
    """
    if not items:
        raise ValueError("mean_components needs at least one item")
    return BandComponents(
        {c: float(np.mean([i.pooled[c] for i in items])) for c in COMPONENTS},
        {
            t: {
                c: float(np.mean([i.by_tenure[t][c] for i in items]))
                for c in TENURE_COMPONENTS
            }
            for t in TENURES
        },
        {t: float(np.mean([i.tenure_mix[t] for i in items])) for t in TENURES},
        items[0].median_share,
    )


def bls_band_components(
    shares: Mapping[str, Mapping[str, float]],
    thresholds: Mapping[str, float],
    tenure_mix: Mapping[str, float],
    median_share: float = MEDIAN_SHARE,
    tolerance: float = PUBLISHED_TOLERANCE,
) -> tuple[BandComponents, dict]:
    """BLS's in-band components for one year, and the checks they pass.

    Args:
        shares: :func:`read_threshold_shares` output for the year.
        thresholds: BLS's thresholds, unrounded.
        tenure_mix: BLS's published tenure distribution for the year.

    Raises:
        ValueError: If components every tenure shares differ by more than
            ``tolerance`` dollars across tenures, either identity in this
            module's docstring misses by more than that, or the
            ``"other_separate"`` terms miss a published share by more than
            that many dollars of in-band value.
    """

    def dollars(tenure: str, row: str) -> float:
        return shares[tenure][row] * thresholds[tenure] / median_share

    def shared(row: str) -> tuple[float, float]:
        values = [dollars(t, row) for t in TENURES]
        return float(np.mean(values)), float(max(values) - min(values))

    spreads, pooled = {}, {}
    for component in ("food", "clothing", "telephone", "nslp", "wic"):
        pooled[component], spreads[component] = shared(component)
    other, spreads["other"] = shared("other")
    fcsuti = other / 0.2
    candidates = {
        row: shared(row) for row in ("internet_oop_row", "internet_total_row")
    }
    internet_row = min(candidates, key=lambda row: candidates[row][1])
    internet_total, spreads["internet"] = candidates[internet_row]
    worst = max(spreads, key=spreads.get)
    if spreads[worst] > tolerance:
        raise ValueError(
            f"BLS's {worst} share gives dollars that differ across tenures "
            f"by {spreads[worst]:.4f}"
        )
    by_tenure = {
        t: {c: dollars(t, c) for c in TENURE_COMPONENTS} for t in TENURES
    }
    for component in SHELTER_UTILITIES + ("broadband",):
        pooled[component] = float(
            sum(tenure_mix[t] * by_tenure[t][component] for t in TENURES)
        )
    pooled["internet"] = internet_total - pooled["broadband"]
    band = BandComponents(pooled, by_tenure, dict(tenure_mix), median_share)
    threshold_errors = {t: band.threshold(t) - thresholds[t] for t in TENURES}
    fcsuti_error = band.fcsuti - fcsuti
    if (
        max(abs(fcsuti_error), *(abs(v) for v in threshold_errors.values()))
        > tolerance
    ):
        raise ValueError(
            "BLS's components miss a published identity: "
            f"FCSUti by {fcsuti_error:.4f}, thresholds by {threshold_errors}"
        )
    share_errors = separate_share_errors(
        band, shares, thresholds, internet_row
    )
    if (
        max(share_errors.values()) * max(thresholds.values()) / median_share
        > tolerance
    ):
        raise ValueError(
            f"BLS's other_separate terms miss its shares by {share_errors}"
        )
    leaf_rows = (
        "food",
        "nslp",
        "wic",
        "clothing",
        "shelter",
        "rental_assistance",
        "utilities",
        "liheap",
        "telephone",
        "internet_oop_row",
        "broadband",
        "other",
    )
    return band, {
        "internet_row": internet_row,
        "shared_component_spread_dollars": spreads,
        "threshold_error_dollars": threshold_errors,
        "fcsuti_error_dollars": fcsuti_error,
        "fcsuti_from_other_share": fcsuti,
        "other_separate_share_error": share_errors,
        "leaf_rows_above_threshold_dollars": {
            t: (sum(shares[t][row] for row in leaf_rows) - 1.0)
            * thresholds[t]
            / median_share
            for t in TENURES
        },
        "total_internet_row_less_shared_dollars": {
            t: dollars(t, "internet_total_row") - internet_total
            for t in TENURES
        },
    }


def _check_accounting(accounting: str) -> None:
    if accounting not in ACCOUNTINGS:
        raise ValueError(
            f"accounting must be one of {ACCOUNTINGS}, not {accounting!r}"
        )


def level_gap(
    ours: BandComponents,
    theirs: BandComponents,
    tenure: str,
    accounting: str = "other_spread",
) -> dict[str, float]:
    """Each term's dollars in ours less theirs, for one threshold."""
    a = ours.threshold_terms(tenure, accounting)
    b = theirs.threshold_terms(tenure, accounting)
    return {c: a[c] - b[c] for c in a}


def separate_share_errors(
    band: BandComponents,
    shares: Mapping[str, Mapping[str, float]],
    thresholds: Mapping[str, float],
    internet_row: str,
) -> dict[str, float]:
    """The largest gap between each published share and its
    ``"other_separate"`` term over the threshold, across tenures.

    Home internet counts against the internet row
    :func:`bls_band_components` chose, which holds equal dollars in every
    tenure and includes broadband, less the tenure's broadband row.
    """
    rows = (
        "food",
        "clothing",
        "telephone",
        "nslp",
        "wic",
        "broadband",
        *SHELTER_UTILITIES,
        OTHER,
    )
    worst = {row: 0.0 for row in (*rows, "internet")}
    for tenure in TENURES:
        terms = band.threshold_terms(tenure, "other_separate")
        total = thresholds[tenure]
        published = dict(shares[tenure])
        published["internet"] = (
            published[internet_row] - published["broadband"]
        )
        for row in worst:
            worst[row] = max(
                worst[row], abs(published[row] - terms[row] / total)
            )
    return worst


def growth_percent(base: float, target: float) -> float:
    return 100.0 * (target / base - 1.0)


def growth_without_imputed(
    base: BandComponents, target: BandComponents, tenure: str
) -> float:
    """Growth of a threshold after removing its imputed terms.

    This holds each band as it stands, so it leaves out any effect of the
    benefits on which units fall in the band. Removing a benefit also
    removes its part of ``0.2 F``, so this uses ``"other_spread"`` terms.
    """
    return growth_percent(
        base.threshold(tenure) - base.imputed_term(tenure),
        target.threshold(tenure) - target.imputed_term(tenure),
    )


def band_fixed_growth_effect(
    base: BandComponents, target: BandComponents, tenure: str
) -> float:
    """Points of a threshold's growth its imputed terms supply, bands held."""
    total = growth_percent(base.threshold(tenure), target.threshold(tenure))
    return total - growth_without_imputed(base, target, tenure)


def imputed_share_beyond_inflation(
    base: BandComponents,
    target: BandComponents,
    tenure: str,
    price_ratio: float,
    accounting: str = "other_spread",
) -> float:
    """The imputed terms' share of threshold growth beyond a price index.

    Growth beyond inflation is ``T_b - price_ratio * T_a``, and the imputed
    terms' part of it is ``C_b - price_ratio * C_a``. It can fall outside
    zero and one.
    """
    return (
        target.imputed_term(tenure, accounting)
        - price_ratio * base.imputed_term(tenure, accounting)
    ) / (target.threshold(tenure) - price_ratio * base.threshold(tenure))


def _number(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _require_definition_inputs(frame: pd.DataFrame) -> None:
    missing = [column for column in _DEFINITION_INPUTS if column not in frame]
    if missing:
        raise ValueError(f"The definition needs FMLI columns {missing}")


def _owner(frame: pd.DataFrame) -> pd.Series:
    """Whether each unit owns its home, by ``CUTENURE``."""
    return pd.to_numeric(frame["CUTENURE"], errors="coerce").isin(OWNER_CODES)


def _vacation_utilities(frame: pd.DataFrame, column: str) -> pd.Series:
    """The vacation-home utilities BLS's papers leave out of ``column``.

    Owners keep utilities for the primary residence only, so they lose
    both vacation summaries. Renters keep any utilities they pay except
    those for rented vacation homes, so they lose that summary alone.
    """
    owned, rented = _VACATION_UTILITIES[column]
    return _number(frame, rented) + _number(frame, owned).where(
        _owner(frame), 0.0
    )


def removed_by_bls_paper_definition(frame: pd.DataFrame) -> pd.DataFrame:
    """The quarterly dollars each unit holds beyond BLS's written definition."""
    _require_definition_inputs(frame)
    removed = pd.DataFrame(
        {
            name: _number(frame, pq) + _number(frame, cq)
            for name, (pq, cq) in _REMOVED_PAIRS.items()
        },
        index=frame.index,
    )
    removed["vacation_utilities"] = sum(
        _vacation_utilities(frame, column) for column in _VACATION_UTILITIES
    )
    return removed


def apply_bls_paper_definition(frame: pd.DataFrame) -> pd.DataFrame:
    """Restrict raw FMLI columns to the definitions in BLS's SPM papers.

    Garner and Munoz (2021,
    https://www.bls.gov/pir/spm/garner_spm_choices_03_15_21.pdf) restrict
    shelter to the primary residence and leave out rent as pay and meals as
    pay. They restrict owners' utilities to the primary residence and count
    renters' utilities for any property but a rented vacation home. Other
    lodging holds vacation homes, school housing and lodging on trips, per
    the CE hierarchy and glossary (https://www.bls.gov/cex/csxgloss.htm).
    The FMLI summary of each amount is:

    - ``OTHLOD``, which ``SHELT`` adds;
    - ``RNTAPY``, which ``RENDWE`` and so ``SHELT`` add;
    - ``MRTPRNO``, the vacation-home principal the replication adds to
      shelter;
    - ``FDMAP``, which ``FDAWAY`` and so ``FOOD`` add;
    - ``UTILOWN`` and ``UTILRNT``, utilities for owned and rented vacation
      homes, which ``UTIL`` adds through its electricity, natural gas,
      fuel oil, other fuels, and water and public services summaries
      (https://www.bls.gov/cex/pumd/ce-pumd-interview-diary-dictionary.xlsx).
      Neither holds telephone service.

    ``CUTENURE`` codes 1-3 count as owners and every other code as a
    renter.

    Returns:
        A copy of ``frame`` with those amounts removed and their columns
        set to zero, except a renter's ``UTILOWN``, which stays, so a
        second application changes nothing. Missing values stay missing in
        the food columns, where the replication reads them row by row.
    """
    _require_definition_inputs(frame)
    out = frame.copy()
    for suffix in ("PQ", "CQ"):
        out[f"SHELT{suffix}"] = (
            _number(out, f"SHELT{suffix}")
            - _number(out, f"OTHLOD{suffix}")
            - _number(out, f"RNTAPY{suffix}")
        )
        meals = _number(out, f"FDMAP{suffix}")
        for stem in ("FOOD", "FDAWAY"):
            column = f"{stem}{suffix}"
            if column in out:
                out[column] = (_number(out, column) - meals).where(
                    pd.to_numeric(out[column], errors="coerce").notna()
                )
    for column in _VACATION_UTILITIES:
        out[column] = _number(out, column) - _vacation_utilities(out, column)
    for pair in _REMOVED_PAIRS.values():
        for column in pair:
            out[column] = 0.0
    owner = _owner(out)
    for owned, rented in _VACATION_UTILITIES.values():
        out[rented] = 0.0
        out[owned] = _number(out, owned).where(~owner, 0.0)
    return out


def shelter_pieces(frame: pd.DataFrame) -> pd.DataFrame:
    """A unit's shelter by FMLI summary, in threshold-year 2A2C dollars.

    Raises:
        ValueError: If the pieces do not sum to the unit's shelter.
    """
    quarterly = _quarterly_factor(frame)
    pieces = pd.DataFrame(
        {
            "owned_home": _sum_pair(frame, "OWNDWEPQ", "OWNDWECQ").to_numpy(
                dtype=float
            )
            * quarterly,
            "owned_home_principal": _sum_pair(
                frame, "EMRTPNOP", "EMRTPNOC"
            ).to_numpy(dtype=float)
            * quarterly,
            "rent_and_rental_costs": _sum_pair(
                frame, "RNTXRPPQ", "RNTXRPCQ"
            ).to_numpy(dtype=float)
            * quarterly,
            "rent_as_pay": _sum_pair(frame, "RNTAPYPQ", "RNTAPYCQ").to_numpy(
                dtype=float
            )
            * quarterly,
            "other_lodging": _sum_pair(frame, "OTHLODPQ", "OTHLODCQ").to_numpy(
                dtype=float
            )
            * quarterly,
            "vacation_home_principal": _sum_pair(
                frame, "MRTPRNOP", "MRTPRNOC"
            ).to_numpy(dtype=float)
            * quarterly,
        },
        index=frame.index,
    )
    shelter = unit_components(frame)["shelter"].to_numpy()
    if np.abs(pieces.sum(axis=1).to_numpy() - shelter).max() > 1e-6:
        raise ValueError(
            "FMLI shelter pieces do not sum to the unit's shelter"
        )
    return pieces


def band_definition_pieces(frame: pd.DataFrame) -> dict[str, dict[str, float]]:
    """In-band means of :func:`shelter_pieces`, meals as pay, and the
    vacation-home utilities BLS's papers leave out.

    Returns:
        ``pooled`` and one entry per tenure, each mapping a piece to its
        mean in threshold-year 2A2C dollars. ``vacation_utilities`` holds
        owners' utilities for owned and rented vacation homes and renters'
        for rented ones.
    """
    pieces = shelter_pieces(frame)
    quarterly = _quarterly_factor(frame)
    pieces["meals_as_pay"] = (
        _sum_pair(frame, "FDMAPPQ", "FDMAPCQ").to_numpy(dtype=float)
        * quarterly
    )
    pieces["vacation_utilities"] = (
        sum(
            _vacation_utilities(frame, column)
            for column in _VACATION_UTILITIES
        ).to_numpy(dtype=float)
        * quarterly
    )
    weights = frame["ce_weight"].to_numpy(dtype=float)
    mask = band_mask(frame["fcsuti_2a2c"].to_numpy(dtype=float), weights)
    tenure = frame["tenure_type"].to_numpy(dtype=object)

    def means(use: np.ndarray) -> dict[str, float]:
        return {
            name: float(
                np.average(pieces[name].to_numpy()[use], weights=weights[use])
            )
            for name in pieces
        }

    pooled = means(mask)
    out = {"pooled": pooled}
    for name in TENURES:
        use = mask & (tenure == name)
        out[name] = means(use) if use.any() else dict(pooled)
    return out
