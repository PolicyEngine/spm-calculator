"""
Calculate SPM base thresholds from Consumer Expenditure Survey.

Independent replication of the BLS revised-methodology thresholds
(approved by the SPM ITWG September 2020, corrected 2026-07-17):

1. Use 5 years of CE Interview Survey quarters lagged by one year: the
   target year T uses collection quarters (T-5)Q2 through (T)Q1.
2. Filter to consumer units with children.
3. Calculate FCSUti (Food, Clothing, Shelter, Utilities, telephone,
   internet).
4. Adjust for inflation using the FCSUti CPI-U composite index.
5. Convert to the reference family (2A2C) using the Betson equivalence
   scale.
6. Apply the BLS formula ``0.82 * (1.2 * FCSUti_E - SU_E + SU_Eh)``
   over the 47th-53rd percentile estimation range E, swapping the
   pooled shelter-utilities average for the tenure-specific one. BLS
   used 83% before the 2026-07-17 correction; pass
   ``median_share=MEDIAN_SHARE_PRE_CORRECTION`` to reproduce the
   pre-correction anchor.

Known approximations (documented, not silently ignored):

- Inflation adjustment uses annual-average FCSUti CPI keyed to each
  interview's collection year. BLS applies quarterly treatment to the
  interview quarters, including the terminal Q1, so this shortcut can
  move replicated nominal levels.
- For post-redesign rows, the code applies the 80% food allocation to
  the combined FMLI ``GROCER`` summary. BLS applies 80% to UCC 790210
  alone, so these constructions are not identical.
- Home-internet expenditures are omitted because FMLI has no matching
  summary variable.
- BLS adds imputed in-kind benefits (broadband, LIHEAP, NSLP, WIC,
  rental assistance) to consumer-unit FCSUti; this module does not
  impute them, which biases replicated levels downward.

See docs/bls-2026-correction.md for measured fidelity by year.

Reference:
- Corrected thresholds: https://www.bls.gov/pir/spm/spm_thresholds_2024_correction.htm
- Methodology: https://www.bls.gov/pir/spmhome.htm
- CE Survey PUMD: https://www.bls.gov/cex/pumd.htm
- Garner et al. methodology paper: https://www.bls.gov/pir/spm/garner_spm_choices_03_15_21.pdf
"""

from __future__ import annotations

import hashlib
import json
import os
import warnings
import zipfile
from pathlib import Path
from typing import Mapping, Optional, Sequence

import numpy as np
import pandas as pd
import requests

from .equivalence_scale import REFERENCE_RAW_SCALE, spm_equivalence_scale
from .fcsuti_cpi import (
    compute_fcsuti_weights_from_ce,
    get_fcsuti_inflation_factor,
)

# BLS CE Survey PUMD base URL. Year bundles live under a per-format
# subdirectory: ``comma/`` through 2021, ``csv/`` from 2022 on.
CE_PUMD_BASE_URL = "https://www.bls.gov/cex/pumd/data"

# First bundle year published under the ``csv/`` subdirectory.
_CSV_SUBDIR_FROM = 2022

#: Share of the median-range FCSUti average that defines the threshold
#: under the corrected methodology published 2026-07-17.
MEDIAN_SHARE = 0.82

#: Anchor used from September 2021 until the 2026-07-17 correction.
MEDIAN_SHARE_PRE_CORRECTION = 0.83

_PRINCIPAL_MODES = ("exclude", "include")
_ANNUALIZATION_MODES = ("quarter4", "pqcq2")

# Share allocated to food at home for CE vintages after the April 2023
# food-question redesign. BLS's FMLI Food at Home errata (September
# 2024) applies 80% to UCC 790210 alone. This FMLI-summary replication
# instead applies it to the combined ``GROCER`` summary, a documented
# approximation to (not an exact implementation of) the BLS treatment.
FOOD_AT_HOME_GROCERY_SHARE = 0.80

# FMLI mortgage-principal outlay columns (owned home + owned vacation
# home). CE's expenditure-concept SHELT summary excludes principal;
# these memo columns let us add it back for the SPM outlays concept.
_PRINCIPAL_COLUMNS = (
    ("EMRTPNOP", "EMRTPNOC"),
    ("MRTPRNOP", "MRTPRNOC"),
)


def _default_cache_dir() -> Path:
    env = os.environ.get("SPM_CALCULATOR_CE_CACHE")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".cache" / "spm-calculator" / "ce-pumd"


def _get_bls_published_thresholds_2024() -> dict[str, float]:
    """Return the 2024 published BLS thresholds from the single source
    of truth (``published_thresholds.HISTORICAL_THRESHOLDS``)."""
    from .published_thresholds import HISTORICAL_THRESHOLDS

    return HISTORICAL_THRESHOLDS[2024].copy()


# Kept for backwards compatibility with callers that imported the
# module-level constant. The canonical source is
# ``spm_calculator.published_thresholds.HISTORICAL_THRESHOLDS[2024]``; mirroring
# it as a dict here avoids the drift risk of two copies.
BLS_PUBLISHED_THRESHOLDS_2024 = _get_bls_published_thresholds_2024()


def bundle_url(bundle_year: int) -> str:
    """URL of the CE Interview PUMD year bundle for ``bundle_year``.

    BLS moved CSV bundles from ``data/comma/`` to ``data/csv/``
    starting with the 2022 release; both layouts remain live for their
    respective years.
    """
    subdir = "csv" if bundle_year >= _CSV_SUBDIR_FROM else "comma"
    yy = f"{bundle_year % 100:02d}"
    return f"{CE_PUMD_BASE_URL}/{subdir}/intrvw{yy}.zip"


def _fetch_bytes(url: str, timeout: int = 300) -> bytes:
    """Fetch a BLS file, falling back to browser-impersonating TLS.

    bls.gov fronts its site with TLS-fingerprint bot detection that
    rejects default ``requests`` clients regardless of headers. When
    that happens we retry with ``curl_cffi`` (an optional dependency,
    installed via ``spm-calculator[ce]``) which impersonates a Chrome
    TLS handshake.
    """
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200 and not response.content[
            :256
        ].lstrip().startswith(b"<"):
            return response.content
        status = response.status_code
    except requests.RequestException as e:
        status = repr(e)

    try:
        from curl_cffi import requests as curl_requests
    except ImportError:
        raise RuntimeError(
            f"Download of {url} was rejected (status {status}); bls.gov "
            "blocks default Python TLS clients. Install the optional "
            "dependency to enable browser-impersonating downloads: "
            "`uv pip install 'spm-calculator[ce]'`."
        ) from None

    response = curl_requests.get(url, impersonate="chrome", timeout=timeout)
    if response.status_code != 200:
        raise RuntimeError(
            f"Download of {url} failed with status {response.status_code}."
        )
    return response.content


def download_ce_bundle(
    bundle_year: int,
    cache_dir: Optional[Path] = None,
    *,
    allow_download: bool = True,
) -> Path:
    """Download (or reuse) the CE Interview year bundle zip.

    Bundles are ~50-90MB, so they are cached on disk
    (``~/.cache/spm-calculator/ce-pumd`` by default, override with
    ``$SPM_CALCULATOR_CE_CACHE``) rather than re-downloaded.

    Returns:
        Path to the cached zip.
    """
    cache = Path(cache_dir) if cache_dir else _default_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / f"intrvw{bundle_year % 100:02d}.zip"
    if dest.exists() and zipfile.is_zipfile(dest):
        return dest
    if not allow_download:
        raise FileNotFoundError(
            f"Required cached CE bundle unavailable: {dest}"
        )
    content = _fetch_bytes(bundle_url(bundle_year))
    if content[:2] != b"PK":
        raise ValueError(
            f"Downloaded {bundle_url(bundle_year)} is not a zip archive."
        )
    dest.write_bytes(content)
    return dest


def _read_bundle_member(bundle: Path, basename: str) -> pd.DataFrame:
    """Read ``basename`` (e.g. ``fmli241.csv``) from a bundle zip.

    Bundle internal layout varies (some vintages nest a second
    directory level), so members are matched on basename.
    """
    with zipfile.ZipFile(bundle) as z:
        matches = [
            n for n in z.namelist() if n.lower().endswith(basename.lower())
        ]
        if not matches:
            raise FileNotFoundError(
                f"{basename} not found in {bundle.name} "
                f"(members: {sorted(z.namelist())[:8]}...)"
            )
        with z.open(matches[0]) as f:
            frame = pd.read_csv(f, low_memory=False)
        frame.attrs["source"] = {
            "bundle_path": str(bundle.resolve()),
            "member": matches[0],
        }
        return frame


def load_ce_quarter(
    year: int,
    quarter: int,
    cache_dir: Optional[Path] = None,
    *,
    allow_download: bool = True,
) -> pd.DataFrame:
    """Load one CE Interview collection quarter as a DataFrame.

    CE publishes collection year Y as bundle ``intrvwYY.zip``
    containing ``fmliYY2``-``fmliYY4`` plus Q1 of the following year
    (``fmli(YY+1)1``); Q1 of year Y therefore ships in bundle Y-1.
    Some vintages additionally carry an overlap file ``fmliYY1x``,
    used here as a fallback when the Y-1 bundle is unavailable.

    Args:
        year: Collection calendar year of the quarter.
        quarter: Collection quarter, 1-4.
        cache_dir: Bundle cache directory override.

    Returns:
        DataFrame with ``ce_year``/``ce_quarter`` annotation columns
        (collection year and quarter).
    """
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"quarter must be 1-4, got {quarter}")
    yy = f"{year % 100:02d}"
    if quarter == 1:
        candidates = [
            (year - 1, f"fmli{yy}1.csv"),
            (year, f"fmli{yy}1x.csv"),
        ]
    else:
        candidates = [(year, f"fmli{yy}{quarter}.csv")]

    last_error: Optional[Exception] = None
    for bundle_year, basename in candidates:
        try:
            options = {} if allow_download else {"allow_download": False}
            bundle = download_ce_bundle(
                bundle_year, cache_dir=cache_dir, **options
            )
            df = _read_bundle_member(bundle, basename)
            break
        except (FileNotFoundError, RuntimeError, ValueError) as e:
            last_error = e
    else:
        raise FileNotFoundError(
            f"Could not load CE quarter {year}Q{quarter}: {last_error}"
        )

    df["ce_year"] = year
    df["ce_quarter"] = quarter
    df.attrs["source"].update(
        {"url": bundle_url(bundle_year), "bundle_year": bundle_year}
    )
    return df


def bls_quarter_window(target_year: int) -> list[tuple[int, int]]:
    """Collection quarters BLS uses for ``target_year`` thresholds.

    The revised methodology lags CE data by one year: target year T is
    based on collection quarters (T-5)Q2 through (T)Q1 (workbook
    footnote: "2019 Revised thresholds are based on CE data from
    2014Q2-2019Q1").

    Returns:
        List of 20 ``(year, quarter)`` tuples in chronological order.
    """
    quarters: list[tuple[int, int]] = []
    for year in range(target_year - 5, target_year + 1):
        for quarter in (1, 2, 3, 4):
            if year == target_year - 5 and quarter < 2:
                continue
            if year == target_year and quarter > 1:
                continue
            quarters.append((year, quarter))
    return quarters


def load_ce_quarters(
    quarters: Sequence[tuple[int, int]],
    cache_dir: Optional[Path] = None,
    *,
    allow_partial: bool = False,
) -> pd.DataFrame:
    """Load and concatenate a set of CE collection quarters.

    Every requested quarter is required by default: silently continuing
    with a shorter window changes both the expenditure distribution and
    its CPI weights. ``allow_partial=True`` is an explicit diagnostic
    mode that warns and returns the quarters that could be loaded; its
    output must not be treated as a threshold replication.

    Args:
        quarters: Collection-year and quarter pairs to load.
        cache_dir: Bundle cache directory override.
        allow_partial: Continue after an individual quarter fails. This
            is intended only for diagnosing download/data availability.

    Raises:
        RuntimeError: If a requested quarter cannot be loaded in the
            default strict mode.
        ValueError: If diagnostic partial mode loads no quarters.
    """
    frames = []
    for year, quarter in quarters:
        try:
            frames.append(load_ce_quarter(year, quarter, cache_dir=cache_dir))
        except Exception as error:  # noqa: BLE001 - add quarter context
            if not allow_partial:
                raise RuntimeError(
                    f"Could not load required CE quarter {year}Q{quarter}"
                ) from error
            warnings.warn(
                f"Diagnostic partial load skipped CE {year}Q{quarter}: "
                f"{error}",
                RuntimeWarning,
                stacklevel=2,
            )
    if not frames:
        raise ValueError("No CE data could be loaded")
    return pd.concat(frames, ignore_index=True)


def download_ce_fmli(year: int, quarter: int) -> pd.DataFrame:
    """
    Download CE Survey Family-level Interview data for a specific quarter.

    Retained for backwards compatibility; loads from the year-bundle
    cache (the per-quarter ``intrvwYY/fmliYYQ.zip`` files this function
    originally fetched no longer exist on bls.gov).

    Args:
        year: Calendar year (e.g., 2023)
        quarter: Quarter (1-4) or 5 for Q1 of following year

    Returns:
        DataFrame with family-level interview data
    """
    if quarter == 5:
        return load_ce_quarter(year + 1, 1)
    return load_ce_quarter(year, quarter)


def download_ce_pumd_years(years: list[int]) -> pd.DataFrame:
    """
    Download CE Survey PUMD for multiple years.

    Each year includes 4 quarters of data from the Interview survey.

    Args:
        years: List of calendar years to download

    Returns:
        Combined DataFrame with all quarters
    """
    quarters = [(year, quarter) for year in years for quarter in (1, 2, 3, 4)]
    return load_ce_quarters(quarters)


def _sum_pair(df: pd.DataFrame, pq: str, cq: str) -> pd.Series:
    """Sum a required PQ/CQ expenditure pair.

    A missing column raises because replacing an absent pair member with
    zero understates expenditures. Row-level missing values remain zero:
    those are respondent/item values inside an otherwise valid CE schema,
    rather than evidence that the requested variable was not loaded.
    """
    missing = [column for column in (pq, cq) if column not in df.columns]
    if missing:
        raise ValueError(
            f"CE data is missing required expenditure column(s) {missing} "
            f"from the {pq}/{cq} pair"
        )
    return df[pq].fillna(0) + df[cq].fillna(0)


def _sum_pair_if_present(
    df: pd.DataFrame, pq: str, cq: str
) -> Optional[pd.Series]:
    """Sum an optional pair, while still rejecting a partial pair."""
    if pq not in df.columns and cq not in df.columns:
        return None
    return _sum_pair(df, pq, cq)


def _food_expenditure(df: pd.DataFrame) -> pd.Series:
    """Quarterly food expenditure per CU, robust to mixed CE vintages.

    The April 2023 CE food redesign replaced the ``FOOD``/``FDHOME``
    summaries with ``GROCER`` (all grocery purchases, food and nonfood
    combined) starting with the 2024Q2 files, so a pooled multi-year
    window mixes schemas row by row. Construction, per row:

    - rows carrying ``GROCER`` data (redesign vintages): food =
      :data:`FOOD_AT_HOME_GROCERY_SHARE` x GROCER + FDAWAY. This applies
      the 80% factor to the combined FMLI summary, whereas BLS applies
      it to UCC 790210 alone; it is therefore an approximation;
    - otherwise, the legacy ``FOOD`` summary when its columns exist,
      falling back to ``FDHOME + FDAWAY``.

    A frame-wide column check would zero food for whichever vintage
    lacks the checked columns — exactly the artifact this per-row
    construction exists to prevent.
    """
    food = _sum_pair_if_present(df, "FOODPQ", "FOODCQ")
    food_at_home = _sum_pair_if_present(df, "FDHOMEPQ", "FDHOMECQ")
    food_away = _sum_pair_if_present(df, "FDAWAYPQ", "FDAWAYCQ")
    groceries = _sum_pair_if_present(df, "GROCERPQ", "GROCERCQ")

    legacy_available = food is not None or (
        food_at_home is not None and food_away is not None
    )
    if food is not None:
        legacy = food
    elif food_at_home is not None and food_away is not None:
        legacy = food_at_home + food_away
    else:
        # A redesign-only frame needs no legacy columns when every row
        # has GROCER data. The row-level check below rejects any row
        # that would otherwise receive this placeholder.
        legacy = pd.Series(0.0, index=df.index)

    if groceries is None:
        if not legacy_available:
            raise ValueError(
                "CE data has no complete food expenditure schema; expected "
                "FOODPQ/FOODCQ, FDHOMEPQ/FDHOMECQ plus "
                "FDAWAYPQ/FDAWAYCQ, or GROCERPQ/GROCERCQ plus "
                "FDAWAYPQ/FDAWAYCQ"
            )
        return legacy

    if food_away is None:
        raise ValueError(
            "GROCER-based CE data requires the complete FDAWAYPQ/FDAWAYCQ pair"
        )
    has_grocer = df[["GROCERPQ", "GROCERCQ"]].notna().any(axis=1)
    if not legacy_available and (~has_grocer).any():
        raise ValueError(
            "CE data has rows without GROCER values and no complete legacy "
            "food expenditure pair"
        )
    redesign = FOOD_AT_HOME_GROCERY_SHARE * groceries + food_away
    return redesign.where(has_grocer, legacy)


def calculate_fcsuti(
    df: pd.DataFrame,
    mortgage_principal: str = "include",
    annualization: str = "quarter4",
) -> pd.Series:
    """Calculate annualized FCSUti (Food, Clothing, Shelter, Utilities,
    telephone, internet) consumption from a CE FMLI DataFrame.

    Component construction against the FMLI summary-variable hierarchy
    (CE PUMD interview dictionary):

    - ``FOOD`` (falling back to ``FDHOME + FDAWAY`` for vintages after
      the 2023 CE food-question redesign that drop the ``FOOD``
      summary). For ``GROCER`` rows, see :func:`_food_expenditure` for
      the documented approximation to BLS's UCC 790210 allocation.
    - ``APPAR`` apparel and services.
    - ``SHELT`` shelter. CE's expenditure concept excludes owner
      mortgage principal; ``mortgage_principal="include"`` (default)
      adds the ``EMRTPNO*``/``MRTPRNO*`` principal-outlay columns,
      matching the SPM threshold concept of owners' out-of-pocket
      shelter cost.
    - ``UTIL`` utilities, fuels, and public services. NOTE: ``UTIL``
      already includes telephone (``UTIL = NTLGAS + ELCTRC + ALLFUL +
      TELEPH + WATRPS``), so telephone must NOT be added separately —
      doing so double-counts it. (The revised BLS methodology moves
      telephone out of the geographically-adjusted utilities group,
      but the FCSUti *sum* is unchanged.)

    Home internet ("computer information services") has no FMLI
    summary variable and is omitted. Imputed in-kind benefits are also
    added by BLS downstream but are not constructed in this module.
    Both omissions lower replicated FCSUti levels.

    Args:
        df: CE Survey FMLI DataFrame (one row per CU-interview)
        mortgage_principal: ``"include"`` (default) adds owner
            mortgage-principal outlays to shelter per the SPM concept;
            ``"exclude"`` uses CE's expenditure-concept shelter
            unchanged.
        annualization: ``"quarter4"`` (default) sums the ``*PQ``/``*CQ``
            pair — one three-month recall window split across calendar
            quarters — and multiplies by 4, matching the BLS convention
            of annualizing each quarterly interview. ``"pqcq2"``
            reproduces the pre-0.4 behavior of multiplying by 2, which
            treated the pair as six months of spending and understated
            annual FCSUti by half.

    Returns:
        Series with annualized FCSUti values in the CU's interview-year
        dollars (inflation adjustment happens downstream).
    """
    if mortgage_principal not in _PRINCIPAL_MODES:
        raise ValueError(
            f"mortgage_principal must be one of {_PRINCIPAL_MODES}, "
            f"got {mortgage_principal!r}"
        )
    if annualization not in _ANNUALIZATION_MODES:
        raise ValueError(
            f"annualization must be one of {_ANNUALIZATION_MODES}, "
            f"got {annualization!r}"
        )

    factor = 4.0 if annualization == "quarter4" else 2.0

    food = _food_expenditure(df)
    apparel = _sum_pair(df, "APPARPQ", "APPARCQ")
    shelter = _sum_pair(df, "SHELTPQ", "SHELTCQ")
    utilities = _sum_pair(df, "UTILPQ", "UTILCQ")

    if mortgage_principal == "include":
        for pq, cq in _PRINCIPAL_COLUMNS:
            principal = _sum_pair_if_present(df, pq, cq)
            if principal is not None:
                shelter = shelter + principal

    total = food + apparel + shelter + utilities
    return total * factor


def get_tenure_type(df: pd.DataFrame) -> pd.Series:
    """Determine housing tenure type (renter, owner_with_mortgage,
    owner_without_mortgage) from CE FMLI data.

    The BLS CE Interview PUMD dictionary defines one six-code schema
    throughout the years used here (and documents the same schema as
    early as 1999):

    1. owned with mortgage;
    2. owned without mortgage;
    3. owned, mortgage status not reported;
    4. rented;
    5. occupied without payment of cash rent; and
    6. student housing.

    Source: BLS, *Dictionary for Interview and Diary Surveys*,
    https://www.bls.gov/cex/pumd/ce-pumd-interview-diary-dictionary.xlsx
    (the archived 1999 dictionary carries the same codes at
    https://www.bls.gov/cex/1999/cex/csxintvw.pdf).

    The dictionary establishes that code 3 is an owner but does not say
    which of the two SPM owner groups receives an owner whose mortgage
    status is unknown. We assign code 3 to ``owner_with_mortgage``: an
    affirmative no-mortgage report is required for the lower-cost
    ``owner_without_mortgage`` group. Codes 5 and 6 are excluded (NA),
    because neither identifies one of the three published SPM tenure
    groups; in particular, code 5 is not evidence of ownership and code
    6 identifies student housing rather than a renter CU. Unknown codes
    raise rather than silently defaulting to renter.

    Level sensitivity: moving code 3 to the no-mortgage group changes
    the tenure-specific shelter/utilities mean for both owner thresholds.
    Including codes 5 or 6 changes the pooled percentile band as well as
    the affected tenure mean, so it can change all three replicated
    threshold levels. These choices therefore belong in replication
    provenance, not an implicit fallback.

    Args:
        df: CE Survey FMLI DataFrame. Must contain ``CUTENURE``.

    Returns:
        Series of tenure strings aligned with ``df.index``. Codes 5 and
        6 are represented by missing values so callers can exclude them.

    Raises:
        ValueError: If ``CUTENURE`` is missing or contains a value
            outside the documented six-code schema.
    """
    if "CUTENURE" not in df.columns:
        raise ValueError("CE data is missing the required 'CUTENURE' column")

    try:
        cutenure = pd.to_numeric(df["CUTENURE"], errors="raise")
    except (TypeError, ValueError) as error:
        raise ValueError(
            "CUTENURE must contain only BLS housing-tenure codes 1-6"
        ) from error

    valid = cutenure.isin(range(1, 7))
    if not valid.all():
        invalid = sorted({repr(value) for value in df.loc[~valid, "CUTENURE"]})
        raise ValueError(
            "CUTENURE contains values outside the BLS six-code schema: "
            f"{invalid}"
        )

    mapping = {
        1: "owner_with_mortgage",
        2: "owner_without_mortgage",
        3: "owner_with_mortgage",
        4: "renter",
    }
    return cutenure.map(mapping).astype(object)


def _weighted_percentile(
    values: np.ndarray,
    weights: np.ndarray,
    percentile: float,
) -> float:
    """Compute a weighted percentile without external deps.

    Uses the midpoint-CDF convention: each observation is placed at
    ``(cum_weight - w_i/2) / total_weight`` and the requested
    percentile is linearly interpolated between surrounding
    observations. For odd-length uniform-weight arrays this agrees
    with ``numpy.percentile`` at the median but not at other
    percentiles (numpy's default ``linear`` interpolation places
    observations at ``i / (n - 1)``, which is a different convention).

    This is this package's interpolation convention. Its exact agreement
    with the unpublished BLS percentile implementation is unverified.

    Empty input returns NaN rather than indexing into `cumulative[-1]`
    on a zero-length array; this path is reachable when a tenure bucket
    drops to zero rows after `dropna` *and* the pooled fallback also
    drops to empty.
    """
    values = np.asarray(values)
    weights = np.asarray(weights, dtype=float)
    if values.size == 0 or weights.size == 0:
        return float("nan")
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]
    cumulative = np.cumsum(weights)
    total = cumulative[-1]
    if total <= 0:
        return float("nan")
    # Shift to the "midpoint" convention so that p=50 returns the
    # weighted median.
    cdf = (cumulative - weights / 2) / total
    target = percentile / 100.0
    return float(np.interp(target, cdf, values))


YOUTH_POLICIES = ("error", "exclude_unresolved", "legacy_recode")
TENURE_POLICIES = (
    "exclude_5_6_code3_mortgage",
    "exclude_5_6_code3_no_mortgage",
    "include_5_6_as_renter",
)
TENURES = ("renter", "owner_with_mortgage", "owner_without_mortgage")


def _mass(frame: pd.DataFrame) -> dict:
    return {
        "rows": len(frame),
        "weight_sum": float(frame["FINLWT21"].sum()),
    }


def normalize_ce_sample(
    ce: pd.DataFrame,
    *,
    youth_policy: str = "error",
    tenure_policy: str = "exclude_5_6_code3_mortgage",
) -> tuple[pd.DataFrame, dict]:
    """Validate counts, select the research sample, and expose exclusions.

    ``FAM_SIZE == PERSLT18`` is a legitimate minor-only consumer unit,
    not malformed data. BLS's CE definition permits independent minors,
    but an exact BLS SPM A=0 classification could not be established.
    Default execution therefore raises. ``exclude_unresolved`` explicitly
    excludes such units; ``legacy_recode`` is a nonofficial sensitivity
    that imposes one adult while retaining the reported child count. It
    deliberately reproduces an assumption, not a plausible classification.
    Original counts remain intact in both modes.

    Tenure 3's assignment and exclusions of 5/6 are methodological choices,
    not an established BLS sample rule. The named alternatives measure
    their sensitivity. Returned row labels are fresh positional indexes.
    """
    if youth_policy not in YOUTH_POLICIES:
        raise ValueError(f"youth_policy must be one of {YOUTH_POLICIES}")
    if tenure_policy not in TENURE_POLICIES:
        raise ValueError(f"tenure_policy must be one of {TENURE_POLICIES}")
    required = ("PERSLT18", "FAM_SIZE", "FINLWT21", "CUTENURE", "ce_year")
    missing = [column for column in required if column not in ce]
    if missing:
        raise ValueError(f"CE data is missing required columns {missing}")
    frame = ce.copy().reset_index(drop=True)
    for column in ("FAM_SIZE", "PERSLT18", "FINLWT21", "ce_year", "CUTENURE"):
        try:
            frame[column] = pd.to_numeric(frame[column], errors="raise")
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{column} must contain numeric values"
            ) from error
    family = frame["FAM_SIZE"]
    children = frame["PERSLT18"]
    valid = (
        np.isfinite(family)
        & np.isfinite(children)
        & (family >= 1)
        & (children >= 0)
        & (family >= children)
        & (family == np.floor(family))
        & (children == np.floor(children))
    )
    if not valid.all():
        raise ValueError(
            "Malformed CE family composition: FAM_SIZE/PERSLT18 must be "
            "finite integer counts, 0 <= PERSLT18 <= FAM_SIZE and "
            "FAM_SIZE >= 1; supported adult-containing units have "
            "FAM_SIZE at least PERSLT18 + 1. "
            f"Invalid row positions: {np.flatnonzero(~valid)[:10].tolist()}"
        )
    weights = frame["FINLWT21"].to_numpy(dtype=float)
    if not (np.isfinite(weights) & (weights > 0)).all():
        raise ValueError(
            "CE survey weights must be finite and strictly positive"
        )
    years = frame["ce_year"].to_numpy(dtype=float)
    if not (np.isfinite(years) & (years == np.floor(years))).all():
        raise ValueError("ce_year must contain finite integer years")
    frame["num_adults"] = family - children
    frame["num_children"] = children
    diagnostics = {
        "youth_policy": youth_policy,
        "tenure_policy": tenure_policy,
        "raw": _mass(frame),
        "weight_semantics": "CE FINLWT21 survey weight summed over CU interviews; not unique population counts",
        "exclusions": {"no_children": _mass(frame.loc[children == 0])},
        "approximations": [
            "PERSLT18 used as child count; dependent/nondependent teen classification unresolved",
            "Tenure 3/5/6 treatment is an explicit research sample policy",
        ],
    }
    frame = frame.loc[children > 0].copy()
    if frame.empty:
        raise ValueError("No consumer units with children found")
    diagnostics["with_children"] = _mass(frame)
    frame["tenure_type"] = get_tenure_type(frame)
    if tenure_policy == "exclude_5_6_code3_no_mortgage":
        frame.loc[frame["CUTENURE"] == 3, "tenure_type"] = (
            "owner_without_mortgage"
        )
    if tenure_policy == "include_5_6_as_renter":
        frame.loc[frame["CUTENURE"].isin([5, 6]), "tenure_type"] = "renter"
    for code in (3, 5, 6):
        diagnostics[f"tenure_{code}"] = _mass(
            frame.loc[frame["CUTENURE"] == code]
        )
    for code in (5, 6):
        diagnostics["exclusions"][f"tenure_{code}"] = _mass(
            frame.loc[
                (frame["CUTENURE"] == code) & frame["tenure_type"].isna()
            ]
        )
    frame = frame.loc[frame["tenure_type"].notna()].copy()
    unresolved = frame["num_adults"] == 0
    detail_columns = [
        column
        for column in (
            "NEWID",
            "AGE_REF",
            "FAM_SIZE",
            "PERSLT18",
            "FINLWT21",
            "CUTENURE",
            "ce_year",
            "ce_quarter",
        )
        if column in frame
    ]
    # JSON-safe records preserve the observed evidence without manufacturing
    # dates, missing reference ages, or record identifiers.
    import json

    diagnostics["unresolved_youth"] = {
        **_mass(frame.loc[unresolved]),
        "records": json.loads(
            frame.loc[unresolved, detail_columns].to_json(orient="records")
        ),
    }
    diagnostics["exclusions"]["unresolved_youth"] = {
        "rows": 0,
        "weight_sum": 0.0,
    }
    if unresolved.any():
        if youth_policy == "error":
            raise ValueError(
                "CE minor-only units have unresolved BLS SPM adult/child "
                f"classification ({int(unresolved.sum())} rows); exact "
                "normalization requires FAM_SIZE at least PERSLT18 + 1. "
                "Choose youth_policy='exclude_unresolved' explicitly for "
                "a documented research approximation, or 'legacy_recode' "
                "only as a nonofficial sensitivity."
            )
        if youth_policy == "exclude_unresolved":
            diagnostics["exclusions"]["unresolved_youth"] = _mass(
                frame.loc[unresolved]
            )
            frame = frame.loc[~unresolved].copy()
        else:
            frame.loc[unresolved, "num_adults"] = 1
        diagnostics["approximations"].append(
            f"minor-only units: {youth_policy}"
        )
    if frame.empty:
        raise ValueError(
            "No consumer units in the selected SPM research sample"
        )
    diagnostics["included"] = _mass(frame)
    return frame.reset_index(drop=True), diagnostics


def construct_normalized_expenditures(
    ce: pd.DataFrame,
    target_year: int,
    *,
    mortgage_principal: str = "include",
    annualization: str = "quarter4",
    cpi_series: Optional[Mapping[str, pd.Series]] = None,
) -> tuple[pd.DataFrame, dict]:
    """Construct expenditure, price and reference-family stages explicitly.

    ``ce`` is the result of :func:`normalize_ce_sample`. Supplying CPI
    series by BLS id pins every annual input and disables CPI transport.
    """
    frame = ce.copy()
    frame["fcsuti"] = calculate_fcsuti(
        frame, mortgage_principal, annualization
    )
    weights = compute_fcsuti_weights_from_ce(
        frame, include_mortgage_principal=mortgage_principal == "include"
    )
    # Zero expenditure components have zero contribution, so need no CPI
    # series. Keep negative weights visible for the CPI validator to reject.
    weights = {
        component: value for component, value in weights.items() if value != 0
    }
    options = {} if cpi_series is None else {"cpi_series": cpi_series}
    inflation = {
        int(year): get_fcsuti_inflation_factor(
            int(year), target_year, weights=weights, **options
        )
        for year in sorted(frame["ce_year"].unique())
    }
    frame["inflation_factor"] = frame["ce_year"].map(inflation)
    frame["equiv_scale"] = spm_equivalence_scale(
        frame["num_adults"], frame["num_children"], normalize=False
    )
    scale = REFERENCE_RAW_SCALE / frame["equiv_scale"]
    frame["fcsuti_threshold_year"] = (
        frame["fcsuti"] * frame["inflation_factor"]
    )
    frame["fcsuti_2a2c"] = frame["fcsuti_threshold_year"] * scale
    su = (
        _sum_pair(frame, "SHELTPQ", "SHELTCQ")
        + _sum_pair(frame, "UTILPQ", "UTILCQ")
        - _sum_pair(frame, "TELEPHPQ", "TELEPHCQ")
    )
    if mortgage_principal == "include":
        for pq, cq in _PRINCIPAL_COLUMNS:
            principal = _sum_pair_if_present(frame, pq, cq)
            if principal is not None:
                su = su + principal
    frame["su_2a2c"] = (
        su
        * (4.0 if annualization == "quarter4" else 2.0)
        * frame["inflation_factor"]
        * scale
    )
    frame["ce_weight"] = frame["FINLWT21"].astype(float)
    if not np.isfinite(frame[["fcsuti_2a2c", "su_2a2c"]].to_numpy()).all():
        raise ValueError("Normalized CE expenditures contain nonfinite values")
    return frame, {
        "cpi_component_weights": weights,
        "inflation_factors": inflation,
        "cpi_input_mode": (
            "explicit_pinned_series"
            if cpi_series is not None
            else "live_with_packaged_fallback"
        ),
        "mortgage_principal": mortgage_principal,
        "annualization": annualization,
        "reference_family": {"adults": 2, "children": 2},
        "approximations": [
            "annual CPI by collection year instead of BLS quarterly treatment",
            "80 percent allocation to combined GROCER summary for redesigned rows",
            "home internet and BLS in-kind benefit imputations omitted",
        ],
    }


def estimate_thresholds(
    ce: pd.DataFrame, median_share: float = MEDIAN_SHARE
) -> tuple[dict[str, float], dict]:
    """Apply the 47–53 midpoint-CDF band with strictly positional selection.

    Tiny samples retain the historical nearest-median/pooled-tenure
    fallback, but its use is surfaced in diagnostics. The convention is
    explicit; equivalence to BLS's unpublished percentile code is unverified.
    """
    if not np.isfinite(median_share) or not 0 < median_share <= 1:
        raise ValueError("median_share must be finite and in (0, 1]")
    if ce.empty:
        raise ValueError("No usable consumer units for weighted estimation")
    values = ce["fcsuti_2a2c"].to_numpy(dtype=float)
    weights = ce["ce_weight"].to_numpy(dtype=float)
    if not (np.isfinite(values) & np.isfinite(weights) & (weights > 0)).all():
        raise ValueError(
            "Estimation values must be finite with positive weights"
        )
    order = np.argsort(values, kind="stable")
    cumulative = np.cumsum(weights[order])
    cdf = (cumulative - weights[order] / 2) / cumulative[-1]
    in_range = (cdf >= 0.47) & (cdf <= 0.53)
    fallback = not bool(in_range.any())
    if fallback:
        in_range[np.argmin(np.abs(cdf - 0.5))] = True
    estimation = ce.iloc[order[in_range]]
    est_weights = estimation["ce_weight"].to_numpy()
    fcsuti_e = float(
        np.average(estimation["fcsuti_2a2c"], weights=est_weights)
    )
    su_e = float(np.average(estimation["su_2a2c"], weights=est_weights))
    thresholds, tenure_diagnostics = {}, {}
    for tenure in TENURES:
        subset = estimation.loc[estimation["tenure_type"] == tenure]
        su_eh = (
            su_e
            if subset.empty
            else float(
                np.average(subset["su_2a2c"], weights=subset["ce_weight"])
            )
        )
        thresholds[tenure] = median_share * (1.2 * fcsuti_e - su_e + su_eh)
        tenure_diagnostics[tenure] = {
            "rows": len(subset),
            "weight_sum": float(subset["ce_weight"].sum()),
            "su_mean": su_eh,
            "pooled_fallback": subset.empty,
        }
    if not all(
        np.isfinite(value) and value > 0 for value in thresholds.values()
    ):
        raise ValueError("Estimated thresholds must be finite and positive")
    return thresholds, {
        "percentile_convention": "midpoint_cdf_inclusive_47_53",
        "bls_percentile_code_parity": "unverified",
        "band_rows": len(estimation),
        "band_weight_sum": float(est_weights.sum()),
        "band_fallback": fallback,
        "fcsuti_mean": fcsuti_e,
        "su_mean": su_e,
        "band_fcsuti_min": float(estimation["fcsuti_2a2c"].min()),
        "band_fcsuti_max": float(estimation["fcsuti_2a2c"].max()),
        "median_share": median_share,
        "tenures": tenure_diagnostics,
    }


def replicate_thresholds(
    ce: pd.DataFrame,
    target_year: int,
    *,
    youth_policy: str = "error",
    tenure_policy: str = "exclude_5_6_code3_mortgage",
    mortgage_principal: str = "include",
    annualization: str = "quarter4",
    median_share: float = MEDIAN_SHARE,
    cpi_series: Optional[Mapping[str, pd.Series]] = None,
) -> dict:
    """Run source-independent scientific stages and return all diagnostics."""
    normalized, sample = normalize_ce_sample(
        ce, youth_policy=youth_policy, tenure_policy=tenure_policy
    )
    expenditures, construction = construct_normalized_expenditures(
        normalized,
        target_year,
        mortgage_principal=mortgage_principal,
        annualization=annualization,
        cpi_series=cpi_series,
    )
    thresholds, estimation = estimate_thresholds(expenditures, median_share)
    methodology_config = {
        "implementation": "ce-fmli-annual-cpi-research-v1",
        "youth_policy": youth_policy,
        "tenure_policy": tenure_policy,
        "mortgage_principal": mortgage_principal,
        "annualization": annualization,
        "median_share": float(median_share),
        "percentile_convention": estimation["percentile_convention"],
        "cpi_input_mode": construction["cpi_input_mode"],
    }
    method_digest = hashlib.sha256(
        json.dumps(
            methodology_config,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "target_year": target_year,
        "methodology_id": f"ce-fmli-research-v1:{method_digest}",
        "methodology_config": methodology_config,
        "classification": "research_replication_with_approximations",
        "thresholds": thresholds,
        "sample": sample,
        "construction": construction,
        "estimation": estimation,
        "uncertainty": {
            "status": "unavailable",
            "reason": "Sampling and imputation uncertainty not estimated",
        },
    }


def calculate_base_thresholds(
    years: Optional[list[int]] = None,
    target_year: int = 2024,
    use_published_fallback: bool = False,
    quarters: Optional[Sequence[tuple[int, int]]] = None,
    median_share: Optional[float] = None,
    mortgage_principal: str = "include",
    annualization: str = "quarter4",
    cache_dir: Optional[Path] = None,
    ce: Optional[pd.DataFrame] = None,
    *,
    youth_policy: str = "error",
    tenure_policy: str = "exclude_5_6_code3_mortgage",
    cpi_series: Optional[Mapping[str, pd.Series]] = None,
) -> dict[str, float]:
    """Calculate SPM base thresholds by tenure from CE Survey PUMD.

    Implements the BLS revised methodology (corrected 2026-07-17):

    1. CE Interview quarters (T-5)Q2 through (T)Q1 for target year T
       (the BLS one-year-lagged five-year window).
    2. Restrict to consumer units with at least one child under 18.
    3. Compute FCSUti per CU (see :func:`calculate_fcsuti` for the
       mortgage-principal and annualization options).
    4. Inflate each CU's FCSUti to the target year using annual-average
       FCSUti CPI keyed to its collection year. This is an approximation
       to BLS's quarterly treatment, notably for the terminal Q1.
    5. Normalize to the 2-adult, 2-child reference family via the
       Betson three-parameter equivalence scale.
    6. Apply the BLS threshold formula over the estimation subsample E
       (CUs inside the 47th-53rd percentile range of equivalized
       FCSUti): ``median_share * (1.2 * FCSUti_E - SU_E + SU_Eh)``,
       where SU is shelter + utilities excluding telephone and h
       indexes housing tenure. ``median_share`` defaults to 82%, the
       corrected anchor.

    Survey weights (``FINLWT21``) are applied throughout. Loading and
    calculation failures raise by default so a failed replication can
    never look like an exact result. For legacy callers that explicitly
    set ``use_published_fallback=True``, a failure returns published BLS
    values for the target year when available and emits a warning.

    Args:
        years: Specific CE collection years to use (Q1-Q4 each).
            Overrides the default BLS quarter window; retained for
            backwards compatibility.
        target_year: The year these thresholds represent.
        use_published_fallback: Explicit legacy opt-in to fall back to
            the BLS published-thresholds series when CE computation
            fails and the target year has a published value. Defaults
            to False so replication failures remain visible.
        quarters: Explicit ``(year, quarter)`` collection quarters.
            Overrides both ``years`` and the default window.
        median_share: Share of the median-range average defining the
            threshold. Defaults to :data:`MEDIAN_SHARE` (0.82); pass
            :data:`MEDIAN_SHARE_PRE_CORRECTION` (0.83) to reproduce
            pre-correction thresholds.
        mortgage_principal: See :func:`calculate_fcsuti`.
        annualization: See :func:`calculate_fcsuti`.
        cache_dir: CE bundle cache directory override.
        ce: Pre-loaded CE FMLI DataFrame (with ``ce_year`` column).
            Skips downloading; used by the replication benchmark to
            reuse one loaded window across variants.
        youth_policy: Default "error" refuses unresolved minor-only units.
            Research runs may select "exclude_unresolved" explicitly;
            "legacy_recode" is a nonofficial sensitivity only. See
            :func:`normalize_ce_sample` and use :func:`replicate_thresholds`
            to retain exclusion counts, weights and estimation diagnostics.
        tenure_policy: Named treatment of ambiguous/unrepresented tenures;
            see :func:`normalize_ce_sample`.
        cpi_series: Explicit annual CPI Series by BLS id; no CPI network
            calls occur when supplied. Source identity belongs in the
            calling release/replication manifest.

    Returns:
        Dict with ``renter``, ``owner_with_mortgage``,
        ``owner_without_mortgage`` threshold values for a 2A2C
        reference family in ``target_year`` dollars.
    """
    if median_share is None:
        median_share = MEDIAN_SHARE

    try:
        if ce is None:
            if quarters is not None:
                ce = load_ce_quarters(quarters, cache_dir=cache_dir)
            elif years is not None:
                ce = download_ce_pumd_years(years)
            else:
                ce = load_ce_quarters(
                    bls_quarter_window(target_year), cache_dir=cache_dir
                )
        result = replicate_thresholds(
            ce,
            target_year,
            youth_policy=youth_policy,
            tenure_policy=tenure_policy,
            median_share=median_share,
            mortgage_principal=mortgage_principal,
            annualization=annualization,
            cpi_series=cpi_series,
        )
        return result["thresholds"]

    except Exception as e:
        if use_published_fallback:
            try:
                from .published_thresholds import get_published_thresholds

                fallback = get_published_thresholds(target_year)
                warnings.warn(
                    f"CE calculation failed ({e}); using published BLS "
                    f"thresholds for {target_year}.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                return fallback
            except ValueError:
                pass
        raise


def get_published_thresholds(year: int) -> dict[str, float]:
    """
    Get published BLS SPM thresholds for a given year.

    Sources from ``published_thresholds.HISTORICAL_THRESHOLDS`` so the
    available years match the bundled published source record.

    Args:
        year: Calendar year

    Returns:
        Dict with threshold values by tenure type

    Raises:
        ValueError: If published thresholds not available for the year
    """
    from .published_thresholds import HISTORICAL_THRESHOLDS

    if year in HISTORICAL_THRESHOLDS:
        return HISTORICAL_THRESHOLDS[year].copy()

    available = sorted(HISTORICAL_THRESHOLDS.keys())
    raise ValueError(
        f"Published thresholds not available for {year}. "
        f"Available years: {available}"
    )
