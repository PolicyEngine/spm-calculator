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

Known replication gaps (documented, not silently ignored): BLS adds
imputed in-kind benefits (broadband, LIHEAP, NSLP, WIC, rental
assistance) to consumer-unit FCSUti before estimating the thresholds;
this module does not impute them, which biases replicated levels
downward. See docs/bls-2026-correction.md for measured fidelity by
year.

Reference:
- Corrected thresholds: https://www.bls.gov/pir/spm/spm_thresholds_2024_correction.htm
- Methodology: https://www.bls.gov/pir/spmhome.htm
- CE Survey PUMD: https://www.bls.gov/cex/pumd.htm
- Garner et al. methodology paper: https://www.bls.gov/pir/spm/garner_spm_choices_03_15_21.pdf
"""

import os
import warnings
import zipfile
from pathlib import Path
from typing import Optional, Sequence

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

# Share of "all grocery purchases" (UCC 790210, food and nonfood
# combined) allocated to food at home for CE vintages after the April
# 2023 food-question redesign. BLS's FMLI Food at Home errata
# (September 2024) sets this to 80%, "using the 2022 proportion of the
# total expense of grocery store purchases to food purchased at grocery
# stores"; BLS applies the same allocation in producing the official
# 2024+ SPM thresholds.
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
    of truth (``forecast.HISTORICAL_THRESHOLDS``)."""
    from .forecast import HISTORICAL_THRESHOLDS

    return HISTORICAL_THRESHOLDS[2024].copy()


# Kept for backwards compatibility with callers that imported the
# module-level constant. The canonical source is
# ``spm_calculator.forecast.HISTORICAL_THRESHOLDS[2024]``; mirroring
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
    bundle_year: int, cache_dir: Optional[Path] = None
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
            return pd.read_csv(f, low_memory=False)


def load_ce_quarter(
    year: int, quarter: int, cache_dir: Optional[Path] = None
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
            bundle = download_ce_bundle(bundle_year, cache_dir=cache_dir)
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
) -> pd.DataFrame:
    """Load and concatenate a set of CE collection quarters."""
    frames = []
    for year, quarter in quarters:
        try:
            frames.append(load_ce_quarter(year, quarter, cache_dir=cache_dir))
        except Exception as e:  # noqa: BLE001 - surface but continue
            warnings.warn(
                f"Could not load CE {year}Q{quarter}: {e}",
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
    """Sum a PQ/CQ expenditure pair, returning zeros if either is missing."""
    if pq in df.columns and cq in df.columns:
        return df[pq].fillna(0) + df[cq].fillna(0)
    return pd.Series(0.0, index=df.index)


def _single(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        return df[col].fillna(0)
    return pd.Series(0.0, index=df.index)


def _food_expenditure(df: pd.DataFrame) -> pd.Series:
    """Quarterly food expenditure per CU, robust to mixed CE vintages.

    The April 2023 CE food redesign replaced the ``FOOD``/``FDHOME``
    summaries with ``GROCER`` (all grocery purchases, food and nonfood
    combined) starting with the 2024Q2 files, so a pooled multi-year
    window mixes schemas row by row. Construction, per row:

    - rows carrying ``GROCER`` data (redesign vintages): food =
      :data:`FOOD_AT_HOME_GROCERY_SHARE` x GROCER + FDAWAY, the BLS
      errata allocation used for the official 2024+ thresholds;
    - otherwise, the legacy ``FOOD`` summary when its columns exist,
      falling back to ``FDHOME + FDAWAY``.

    A frame-wide column check would zero food for whichever vintage
    lacks the checked columns — exactly the artifact this per-row
    construction exists to prevent.
    """
    legacy = _sum_pair(df, "FOODPQ", "FOODCQ")
    if "FOODPQ" not in df.columns or "FOODCQ" not in df.columns:
        home_away = _sum_pair(df, "FDHOMEPQ", "FDHOMECQ") + _sum_pair(
            df, "FDAWAYPQ", "FDAWAYCQ"
        )
        legacy = legacy.where(legacy > 0, home_away)

    if "GROCERPQ" not in df.columns and "GROCERCQ" not in df.columns:
        return legacy

    has_grocer = pd.Series(False, index=df.index)
    for col in ("GROCERPQ", "GROCERCQ"):
        if col in df.columns:
            has_grocer |= df[col].notna()
    redesign = FOOD_AT_HOME_GROCERY_SHARE * _sum_pair(
        df, "GROCERPQ", "GROCERCQ"
    ) + _sum_pair(df, "FDAWAYPQ", "FDAWAYCQ")
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
      summary).
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
    summary variable and is not included; this is a known replication
    gap of roughly 1-2% of FCSUti.

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
            shelter = shelter + _sum_pair(df, pq, cq)

    total = food + apparel + shelter + utilities
    return total * factor


MODERN_CUTENURE_YEAR = 2013


def get_tenure_type(df: pd.DataFrame) -> pd.Series:
    """Determine housing tenure type (renter, owner_with_mortgage,
    owner_without_mortgage) from CE FMLI data.

    CUTENURE codes (post-2013):
        1 = Owned with mortgage
        2 = Owned without mortgage
        3 = Rented
        4 = Occupied without payment
        5 = Student housing

    BLS expanded the CUTENURE codes in 2013 to split owners by mortgage
    status. Schema is detected from ``ce_year`` — previously we looked
    at observed codes (``(cutenure >= 3).any()``), which silently fell
    into the legacy branch whenever a caller happened to filter to an
    owners-only subset and re-labelled `CUTENURE == 2` rows as renters
    even though the modern schema calls them owners-without-mortgage.

    For legacy (pre-2013) vintages, owner-vs-owner-with-mortgage is
    derived from mortgage interest/principal expenditure.

    Args:
        df: CE Survey FMLI DataFrame. Must contain ``CUTENURE``; for
            ambiguous vintages (pre-2013) it must also contain
            ``ce_year`` so the schema can be resolved at load time
            rather than from observed codes.

    Returns:
        Series of tenure strings aligned with ``df.index``.
    """
    tenure = pd.Series("renter", index=df.index, dtype=object)
    cutenure = df["CUTENURE"]

    if "ce_year" in df.columns and len(df) > 0:
        ce_year = df["ce_year"]
        is_modern_schema = (ce_year.astype(int) >= MODERN_CUTENURE_YEAR).all()
        if (
            not is_modern_schema
            and not (ce_year.astype(int) < MODERN_CUTENURE_YEAR).all()
        ):
            raise ValueError(
                "Dataset mixes pre-2013 and post-2013 CE vintages "
                "(CUTENURE schema changed in 2013). Split by `ce_year` "
                "before calling `get_tenure_type`."
            )
    elif len(df) == 0:
        # Empty frame: schema is irrelevant, return the empty series.
        return tenure
    else:
        # No `ce_year` column: fall back to the legacy observed-code
        # heuristic with an explicit warning, since that's the only
        # signal left. This path is only for ad-hoc callers passing
        # bare CE frames; the PUMD download path always annotates
        # `ce_year`.
        warnings.warn(
            "get_tenure_type called without `ce_year` column; falling "
            "back to observed-code schema detection, which misclassifies "
            "owners-only subsets on the modern schema. Pass a `ce_year` "
            "column to disambiguate.",
            RuntimeWarning,
            stacklevel=2,
        )
        is_modern_schema = (cutenure >= 3).any()

    if is_modern_schema:
        # 1 = owner w/ mortgage, 2 = owner w/o, 3 = renter.
        tenure[cutenure == 1] = "owner_with_mortgage"
        tenure[cutenure == 2] = "owner_without_mortgage"
        tenure[cutenure == 3] = "renter"
    else:
        # Legacy CUTENURE where only owners (1) and renters (2) are split.
        # Detect mortgage status from expenditure presence.
        is_owner = cutenure == 1
        is_renter = cutenure == 2
        mortgage_activity = _sum_pair(df, "EMRTPNOP", "EMRTPNOC") + _sum_pair(
            df, "MRTINTPQ", "MRTINTCQ"
        )
        has_mortgage = is_owner & (mortgage_activity > 0)
        tenure[is_renter] = "renter"
        tenure[is_owner & has_mortgage] = "owner_with_mortgage"
        tenure[is_owner & ~has_mortgage] = "owner_without_mortgage"

    return tenure


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

    This matches the weighted-median convention used in survey
    statistics packages (e.g., R's ``Hmisc::wtd.quantile`` with
    ``type='i/n'``) and is the sensible extension of BLS's
    percentile-range threshold approach to weighted CU data.

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


def calculate_base_thresholds(
    years: Optional[list[int]] = None,
    target_year: int = 2024,
    use_published_fallback: bool = True,
    quarters: Optional[Sequence[tuple[int, int]]] = None,
    median_share: Optional[float] = None,
    mortgage_principal: str = "include",
    annualization: str = "quarter4",
    cache_dir: Optional[Path] = None,
    ce: Optional[pd.DataFrame] = None,
) -> dict[str, float]:
    """Calculate SPM base thresholds by tenure from CE Survey PUMD.

    Implements the BLS revised methodology (corrected 2026-07-17):

    1. CE Interview quarters (T-5)Q2 through (T)Q1 for target year T
       (the BLS one-year-lagged five-year window).
    2. Restrict to consumer units with at least one child under 18.
    3. Compute FCSUti per CU (see :func:`calculate_fcsuti` for the
       mortgage-principal and annualization options).
    4. Inflate each CU's FCSUti to the target year using the FCSUti
       composite CPI index.
    5. Normalize to the 2-adult, 2-child reference family via the
       Betson three-parameter equivalence scale.
    6. Apply the BLS threshold formula over the estimation subsample E
       (CUs inside the 47th-53rd percentile range of equivalized
       FCSUti): ``median_share * (1.2 * FCSUti_E - SU_E + SU_Eh)``,
       where SU is shelter + utilities excluding telephone and h
       indexes housing tenure. ``median_share`` defaults to 82%, the
       corrected anchor.

    Survey weights (``FINLWT21``) are applied throughout. If loading
    or any downstream step fails and ``use_published_fallback`` is
    set, returns published BLS values for the target year when
    available (2005-2024).

    Args:
        years: Specific CE collection years to use (Q1-Q4 each).
            Overrides the default BLS quarter window; retained for
            backwards compatibility.
        target_year: The year these thresholds represent.
        use_published_fallback: If True, fall back to the BLS
            published-thresholds series when CE computation fails and
            the target year has a published value.
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
        ce = ce.copy()

        # The BLS methodology requires consumer units with at least one
        # child under 18. FMLI publishes `PERSLT18` for every vintage we
        # care about (2013+); if it's missing we refuse rather than
        # using the old `FAM_SIZE > PERSOT64` heuristic, which silently
        # matches any non-elderly CU — including two-adult / zero-child
        # units — and therefore miscalibrates the threshold.
        if "PERSLT18" not in ce.columns:
            raise ValueError(
                "CE data is missing the 'PERSLT18' column required to "
                "restrict to consumer units with children. The previous "
                "fallback (FAM_SIZE > PERSOT64) is a methodology error "
                "because it matches any CU with at least one non-elderly "
                "member, not a CU with a child under 18."
            )
        ce = ce[ce["PERSLT18"] > 0].copy()

        if len(ce) == 0:
            raise ValueError("No consumer units with children found")

        ce["fcsuti"] = calculate_fcsuti(
            ce,
            mortgage_principal=mortgage_principal,
            annualization=annualization,
        )

        # Derive FCSUti composite weights from this CE sample itself,
        # matching BLS Garner (2021): the weights roll with the 5-year
        # window rather than being held static across years. Fall back
        # to the package default (with its own RuntimeWarning) only if
        # the CE sample has no usable expenditure columns.
        try:
            fcsuti_weights = compute_fcsuti_weights_from_ce(ce)
        except ValueError as e:
            warnings.warn(
                f"Could not derive FCSUti weights from CE ({e}); "
                "using static defaults.",
                RuntimeWarning,
                stacklevel=2,
            )
            fcsuti_weights = None

        # Inflate each CU's FCSUti to target-year dollars using the
        # FCSUti composite CPI built from the derived (or default)
        # weights.
        inflation_factors = {
            year: get_fcsuti_inflation_factor(
                year, target_year, weights=fcsuti_weights
            )
            for year in ce["ce_year"].dropna().astype(int).unique()
        }
        ce["inflation_factor"] = (
            ce["ce_year"].astype(int).map(inflation_factors).astype(float)
        )
        ce["fcsuti_threshold_year"] = ce["fcsuti"] * ce["inflation_factor"]

        # Normalize to the 2A2C reference family via the Betson scale.
        # FMLI has no adult-count summary column; derive it as family
        # size minus children. (The previous ``ce.get("ADULT", 2)``
        # read a nonexistent column and silently treated every CU as
        # two-adult, understating equivalized spending for
        # single-parent CUs.)
        num_children = ce.get("PERSLT18", 0)
        if "FAM_SIZE" in ce.columns:
            num_adults = (
                ce["FAM_SIZE"].fillna(0) - ce["PERSLT18"].fillna(0)
            ).clip(lower=1)
        else:
            num_adults = 2
        ce["equiv_scale"] = spm_equivalence_scale(
            num_adults, num_children, normalize=False
        )
        ce["fcsuti_2a2c"] = ce["fcsuti_threshold_year"] * (
            REFERENCE_RAW_SCALE / ce["equiv_scale"]
        )

        # Shelter + utilities excluding telephone, the tenure-swapped
        # term of the BLS formula. UTIL contains TELEPH, so SU without
        # telephone is SHELT (+ principal under the outlays concept)
        # + UTIL - TELEPH.
        su = (
            _sum_pair(ce, "SHELTPQ", "SHELTCQ")
            + _sum_pair(ce, "UTILPQ", "UTILCQ")
            - _sum_pair(ce, "TELEPHPQ", "TELEPHCQ")
        )
        if mortgage_principal == "include":
            for pq, cq in _PRINCIPAL_COLUMNS:
                su = su + _sum_pair(ce, pq, cq)
        annual_factor = 4.0 if annualization == "quarter4" else 2.0
        ce["su_2a2c"] = (
            su
            * annual_factor
            * ce["inflation_factor"]
            * (REFERENCE_RAW_SCALE / ce["equiv_scale"])
        )

        ce["tenure_type"] = get_tenure_type(ce)

        # CE survey weights. FMLI publishes FINLWT21 as the calibrated
        # CU weight. If a vintage is missing it, fall back to uniform.
        if "FINLWT21" in ce.columns:
            ce["ce_weight"] = ce["FINLWT21"].astype(float)
        else:
            ce["ce_weight"] = 1.0

        ce = ce.dropna(subset=["fcsuti_2a2c", "su_2a2c"])
        if len(ce) == 0:
            raise ValueError("No usable consumer units after cleaning")

        # BLS formula (methodology page, corrected 2026-07-17):
        #   SPM_h = share * (1.2 * FCSUti_E - SU_E + SU_Eh)
        # where E is the estimation subsample inside the 47th-53rd
        # percentile range of equivalized FCSUti, SU is shelter +
        # utilities excluding telephone, and h indexes housing tenure.
        # The 1.2 multiplier accounts for other basic goods and
        # services (household supplies, personal care, non-work
        # transportation).
        values = ce["fcsuti_2a2c"].to_numpy()
        weights = ce["ce_weight"].to_numpy()
        order = np.argsort(values)
        cumulative = np.cumsum(weights[order])
        cdf = (cumulative - weights[order] / 2) / cumulative[-1]
        in_range_sorted = (cdf >= 0.47) & (cdf <= 0.53)
        if not in_range_sorted.any():
            # Degenerate samples (tiny test fixtures) can leave the
            # 47th-53rd band empty under the midpoint-CDF convention;
            # fall back to the observation closest to the median.
            in_range_sorted = np.zeros_like(in_range_sorted, dtype=bool)
            in_range_sorted[np.argmin(np.abs(cdf - 0.5))] = True
        range_index = ce.index.to_numpy()[order][in_range_sorted]
        estimation = ce.loc[range_index]

        est_weights = estimation["ce_weight"].to_numpy()
        fcsuti_e = float(
            np.average(estimation["fcsuti_2a2c"], weights=est_weights)
        )
        su_e = float(np.average(estimation["su_2a2c"], weights=est_weights))

        base_thresholds: dict[str, float] = {}
        for tenure in (
            "renter",
            "owner_with_mortgage",
            "owner_without_mortgage",
        ):
            subset = estimation[estimation["tenure_type"] == tenure]
            if len(subset) == 0:
                # Degenerate estimation range (tiny test fixtures):
                # fall back to the pooled shelter-utilities average.
                su_eh = su_e
            else:
                su_eh = float(
                    np.average(
                        subset["su_2a2c"],
                        weights=subset["ce_weight"].to_numpy(),
                    )
                )
            base_thresholds[tenure] = median_share * (
                1.2 * fcsuti_e - su_e + su_eh
            )

        return base_thresholds

    except Exception as e:
        if use_published_fallback:
            try:
                # Lazy import avoids a circular import at module load.
                from .forecast import get_thresholds

                fallback = get_thresholds(target_year, allow_forecast=False)
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

    Sources from ``forecast.HISTORICAL_THRESHOLDS`` so the available
    range stays in lockstep with the forecast path. Previously this
    function hard-coded 2022–2024 while the forecast module had 2015–2024,
    so `get_published_thresholds(2020)` raised even though the published
    value existed.

    Args:
        year: Calendar year

    Returns:
        Dict with threshold values by tenure type

    Raises:
        ValueError: If published thresholds not available for the year
    """
    # Lazy import avoids a circular import at module load.
    from .forecast import HISTORICAL_THRESHOLDS

    if year in HISTORICAL_THRESHOLDS:
        return HISTORICAL_THRESHOLDS[year].copy()

    available = sorted(HISTORICAL_THRESHOLDS.keys())
    raise ValueError(
        f"Published thresholds not available for {year}. "
        f"Available years: {available}"
    )
