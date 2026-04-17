"""
Calculate SPM base thresholds from Consumer Expenditure Survey.

Follows BLS methodology (updated September 2021):
1. Use 5 years of CE Survey PUMD (Public Use Microdata), lagged by 1 year
2. Filter to consumer units with children
3. Calculate FCSUti (Food, Clothing, Shelter, Utilities, telephone, internet)
4. Adjust for inflation using FCSUti CPI-U composite index
5. Convert to reference family (2A2C) using equivalence scale
6. Calculate 83% of median (47th-53rd percentile average) by tenure type

Note: Pre-2021 methodology used 33rd percentile (30th-36th range).
The 2021+ methodology uses 83% of median which is approximately equivalent.

Reference:
- BLS SPM Thresholds: https://www.bls.gov/pir/spm/spm_thresholds_2024.htm
- CE Survey PUMD: https://www.bls.gov/cex/pumd.htm
- Methodology: https://www.bls.gov/pir/spm/garner_spm_choices_03_15_21.pdf
"""

import io
import warnings
import zipfile
from typing import Optional

import numpy as np
import pandas as pd
import requests

from .equivalence_scale import REFERENCE_RAW_SCALE, spm_equivalence_scale
from .fcsuti_cpi import get_fcsuti_inflation_factor

# BLS CE Survey PUMD base URL
CE_PUMD_BASE_URL = "https://www.bls.gov/cex/pumd/data/comma"


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


def download_ce_fmli(year: int, quarter: int) -> pd.DataFrame:
    """
    Download CE Survey Family-level Interview data for a specific quarter.

    Args:
        year: Calendar year (e.g., 2023)
        quarter: Quarter (1-4) or 5 for Q1 of following year

    Returns:
        DataFrame with family-level interview data
    """
    # CE files use 2-digit year
    yy = str(year)[-2:]

    # Quarter mapping: Q1-Q4 of year Y, plus Q1 of Y+1 (coded as Q5)
    if quarter == 5:
        qtr_code = "1"
        yy = str(year + 1)[-2:]
    else:
        qtr_code = str(quarter)

    # File naming: fmli{yy}{q}.zip contains fmli{yy}{q}.csv
    filename = f"fmli{yy}{qtr_code}"
    url = f"{CE_PUMD_BASE_URL}/intrvw{yy}/{filename}.zip"

    response = requests.get(url, timeout=60)
    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        # Find the CSV file in the zip
        csv_files = [f for f in z.namelist() if f.endswith(".csv")]
        if not csv_files:
            raise ValueError(f"No CSV file found in {url}")

        with z.open(csv_files[0]) as f:
            df = pd.read_csv(f)

    df["ce_year"] = year
    df["ce_quarter"] = quarter
    return df


def download_ce_pumd_years(years: list[int]) -> pd.DataFrame:
    """
    Download CE Survey PUMD for multiple years.

    Each year includes 4 quarters of data from the Interview survey.

    Args:
        years: List of calendar years to download

    Returns:
        Combined DataFrame with all quarters
    """
    dfs = []

    for year in years:
        for quarter in range(1, 5):
            try:
                df = download_ce_fmli(year, quarter)
                dfs.append(df)
            except Exception as e:
                print(f"Warning: Could not download {year} Q{quarter}: {e}")

    if not dfs:
        raise ValueError("No CE data could be downloaded")

    return pd.concat(dfs, ignore_index=True)


def _sum_pair(df: pd.DataFrame, pq: str, cq: str) -> pd.Series:
    """Sum a PQ/CQ expenditure pair, returning zeros if either is missing."""
    if pq in df.columns and cq in df.columns:
        return df[pq].fillna(0) + df[cq].fillna(0)
    return pd.Series(0.0, index=df.index)


def calculate_fcsuti(df: pd.DataFrame) -> pd.Series:
    """Calculate annualized FCSUti (Food, Clothing, Shelter, Utilities,
    telephone, internet) consumption from a CE FMLI DataFrame.

    Each FMLI record reports previous-quarter (``*PQ``) and
    current-quarter (``*CQ``) expenditures, so the pair sums to six
    months of spending. Multiplying by 2 annualizes.

    For owner CUs, mortgage principal is subtracted from shelter because
    BLS SPM treats principal as investment, not consumption. The
    principal variables (``MRTPRINPQ``/``MRTPRINCQ``) exist only in
    vintages that split them out; we fall back to zero if missing.

    Post-2019 CE vintages separate "information technology" spending
    (``INFOTECHPQ``/``INFOTECHCQ``) covering internet services, which
    BLS includes alongside telephone in FCSUti.

    Args:
        df: CE Survey FMLI DataFrame (one row per CU-interview)

    Returns:
        Series with annualized FCSUti values in the CU's interview-year
        dollars (inflation adjustment happens downstream).
    """
    food = _sum_pair(df, "FOODPQ", "FOODCQ")
    apparel = _sum_pair(df, "APPARPQ", "APPARCQ")
    shelter = _sum_pair(df, "SHELTPQ", "SHELTCQ")
    utilities = _sum_pair(df, "UTILPQ", "UTILCQ")
    telephone = _sum_pair(df, "TELEPHPQ", "TELEPHCQ")
    # "Information technology" includes internet services (post-2018).
    info_tech = _sum_pair(df, "INFOTECHPQ", "INFOTECHCQ")

    # Exclude mortgage principal from owner shelter: it's investment,
    # not consumption. Variable names vary across vintages.
    mortgage_principal = _sum_pair(df, "MRTPRINPQ", "MRTPRINCQ")
    shelter = (shelter - mortgage_principal).clip(lower=0)

    # PQ + CQ covers two quarters; multiply by 2 to annualize.
    return (food + apparel + shelter + utilities + telephone + info_tech) * 2


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
        if not is_modern_schema and not (
            ce_year.astype(int) < MODERN_CUTENURE_YEAR
        ).all():
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
        mortgage_activity = _sum_pair(
            df, "MRTPRINPQ", "MRTPRINCQ"
        ) + _sum_pair(df, "MRTINTPQ", "MRTINTCQ")
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
) -> dict[str, float]:
    """Calculate SPM base thresholds by tenure from CE Survey PUMD.

    Implements the BLS methodology documented in Garner (2021):

    1. 5 years of CE Interview Survey data, lagged by 1 year (for a
       target year of 2024, use 2018–2022 CE microdata).
    2. Restrict to consumer units with at least one child under 18.
    3. Compute FCSUti (Food, Clothing, Shelter, Utilities, telephone,
       internet) per CU, annualized from the ``*PQ``/``*CQ`` quarterly
       pair and excluding mortgage principal from owner shelter.
    4. Inflate each CU's FCSUti to the target year using the FCSUti
       composite CPI index.
    5. Normalize to the 2-adult, 2-child reference family by dividing
       by the Betson three-parameter equivalence scale.
    6. Compute 83% of the CE weight-weighted median (approximated by
       the mean of the 47th and 53rd percentiles) separately by
       tenure.

    Survey weights (``FINLWT21``) are applied throughout. If the
    download or any downstream step fails and
    ``use_published_fallback`` is set, returns published BLS values
    for the target year when available (2015–2024).

    Args:
        years: Specific CE years to use. Defaults to the 5-year BLS
            lagged window.
        target_year: The year these thresholds represent.
        use_published_fallback: If True, fall back to the BLS
            published-thresholds dict (``HISTORICAL_THRESHOLDS`` via
            ``forecast.get_thresholds``) when CE computation fails and
            the target year has a published value.

    Returns:
        Dict with ``renter``, ``owner_with_mortgage``,
        ``owner_without_mortgage`` threshold values for a 2A2C
        reference family in ``target_year`` dollars.
    """
    if years is None:
        years = list(range(target_year - 6, target_year - 1))

    try:
        ce = download_ce_pumd_years(years)

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

        ce["fcsuti"] = calculate_fcsuti(ce)

        # Inflate each CU's FCSUti to target-year dollars using the
        # FCSUti composite CPI.
        inflation_factors = {
            year: get_fcsuti_inflation_factor(year, target_year)
            for year in ce["ce_year"].dropna().astype(int).unique()
        }
        ce["inflation_factor"] = (
            ce["ce_year"].astype(int).map(inflation_factors).astype(float)
        )
        ce["fcsuti_threshold_year"] = ce["fcsuti"] * ce["inflation_factor"]

        # Normalize to the 2A2C reference family via the Betson scale.
        num_adults = ce.get("ADULT", 2)
        num_children = ce.get("PERSLT18", 0)
        ce["equiv_scale"] = spm_equivalence_scale(
            num_adults, num_children, normalize=False
        )
        ce["fcsuti_2a2c"] = ce["fcsuti_threshold_year"] * (
            REFERENCE_RAW_SCALE / ce["equiv_scale"]
        )

        ce["tenure_type"] = get_tenure_type(ce)

        # CE survey weights. FMLI publishes FINLWT21 as the calibrated
        # CU weight. If a vintage is missing it, fall back to uniform.
        if "FINLWT21" in ce.columns:
            ce["ce_weight"] = ce["FINLWT21"].astype(float)
        else:
            ce["ce_weight"] = 1.0

        base_thresholds: dict[str, float] = {}
        for tenure in (
            "renter",
            "owner_with_mortgage",
            "owner_without_mortgage",
        ):
            subset = ce[ce["tenure_type"] == tenure]
            subset = subset.dropna(subset=["fcsuti_2a2c"])
            if len(subset) == 0:
                # Fall back to pooled distribution if a tenure bucket is
                # empty in this vintage.
                subset = ce.dropna(subset=["fcsuti_2a2c"])

            values = subset["fcsuti_2a2c"].to_numpy()
            weights = subset["ce_weight"].to_numpy()
            p47 = _weighted_percentile(values, weights, 47.0)
            p53 = _weighted_percentile(values, weights, 53.0)
            base_thresholds[tenure] = 0.83 * (p47 + p53) / 2

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
