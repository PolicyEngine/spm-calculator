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
import zipfile
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests

from .equivalence_scale import spm_equivalence_scale

# BLS CE Survey PUMD base URL
CE_PUMD_BASE_URL = "https://www.bls.gov/cex/pumd/data/comma"

# Published BLS thresholds for validation (2024)
BLS_PUBLISHED_THRESHOLDS_2024 = {
    "renter": 39430,
    "owner_with_mortgage": 39068,
    "owner_without_mortgage": 32586,
}


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


def calculate_fcsuti(df: pd.DataFrame) -> pd.Series:
    """
    Calculate FCSUti (Food, Clothing, Shelter, Utilities, telephone, internet).

    These are the expenditure categories used in the SPM threshold.

    Args:
        df: CE Survey FMLI DataFrame

    Returns:
        Series with FCSUti values (annual)
    """
    # CE variable names for expenditure categories
    # Note: Variable names may vary slightly by year
    # These are quarterly values, multiply by 4 for annual

    # Food (at home + away)
    food_cols = ["FOODPQ", "FOODCQ"]  # Previous quarter, current quarter
    food = df[food_cols].sum(axis=1) if all(c in df for c in food_cols) else 0

    # Clothing/Apparel
    apparel_cols = ["APPARPQ", "APPARCQ"]
    apparel = (
        df[apparel_cols].sum(axis=1)
        if all(c in df for c in apparel_cols)
        else 0
    )

    # Shelter (rent or mortgage + property taxes + insurance)
    shelter_cols = ["SHELTPQ", "SHELTCQ"]
    shelter = (
        df[shelter_cols].sum(axis=1)
        if all(c in df for c in shelter_cols)
        else 0
    )

    # Utilities (electricity, gas, water, etc.)
    util_cols = ["UTILPQ", "UTILCQ"]
    utilities = (
        df[util_cols].sum(axis=1) if all(c in df for c in util_cols) else 0
    )

    # Telephone
    phone_cols = ["TELEPHPQ", "TELEPHCQ"]
    telephone = (
        df[phone_cols].sum(axis=1) if all(c in df for c in phone_cols) else 0
    )

    # Internet (may be included in utilities or telephone in some years)
    # Starting ~2019, there's a separate internet category
    internet = 0

    # Sum components - these are already quarterly averages in FMLI
    # Multiply by 4 to annualize
    fcsuti = (food + apparel + shelter + utilities + telephone + internet) * 4

    return fcsuti


def get_tenure_type(df: pd.DataFrame) -> pd.Series:
    """
    Determine housing tenure type from CE data.

    Args:
        df: CE Survey FMLI DataFrame

    Returns:
        Series with tenure type: 'renter', 'owner_with_mortgage',
        'owner_without_mortgage'
    """
    # CUTENURE: 1=Owned, 2=Rented, 3=Occupied without payment, 4=Student housing
    # For owners, check mortgage status via QOWNED or property values

    tenure = pd.Series(index=df.index, dtype=str)

    is_renter = df["CUTENURE"] == 2
    is_owner = df["CUTENURE"] == 1

    # Check for mortgage - various indicators
    # OWNYRSTW: Years owned (0 if renting)
    # QOWNED: Quarter first owned
    # Look at shelter costs composition for mortgage indicator
    has_mortgage = is_owner & (
        df.get("OWNYRTHH", 0) < 30
    )  # Proxy: owned < 30 years

    tenure[is_renter] = "renter"
    tenure[is_owner & has_mortgage] = "owner_with_mortgage"
    tenure[is_owner & ~has_mortgage] = "owner_without_mortgage"
    tenure[tenure == ""] = "renter"  # Default fallback

    return tenure


def calculate_base_thresholds(
    years: Optional[list[int]] = None,
    target_year: int = 2024,
    use_published_fallback: bool = True,
) -> dict[str, float]:
    """
    Calculate SPM base thresholds by tenure type from CE Survey.

    Following BLS methodology:
    - Use 5 years of data, lagged by 1 year
    - Filter to consumer units with children
    - Calculate 33rd percentile of FCSUti by tenure

    Args:
        years: Specific years to use. If None, uses 5 years lagged by 1.
        target_year: The year for which thresholds are being calculated.
        use_published_fallback: If True, return published BLS values when
                               CE data is unavailable or calculation fails.

    Returns:
        Dict with keys 'renter', 'owner_with_mortgage', 'owner_without_mortgage'
        and threshold values in dollars.
    """
    if years is None:
        # Standard BLS methodology: 5 years lagged by 1
        # For 2024 thresholds, use 2018-2022 data
        years = list(range(target_year - 6, target_year - 1))

    try:
        ce = download_ce_pumd_years(years)

        # Filter to consumer units with children
        # PERSLT18: Number of persons under 18
        if "PERSLT18" in ce.columns:
            ce = ce[ce["PERSLT18"] > 0]
        elif "FAM_SIZE" in ce.columns and "PERSOT64" in ce.columns:
            # Alternative: infer from family composition
            ce = ce[ce["FAM_SIZE"] > ce.get("PERSOT64", 0)]

        if len(ce) == 0:
            raise ValueError("No consumer units with children found")

        # Calculate FCSUti
        ce["fcsuti"] = calculate_fcsuti(ce)

        # Get equivalence scale
        num_adults = ce.get("ADULT", 2)
        num_children = ce.get("PERSLT18", 0)
        ce["equiv_scale"] = spm_equivalence_scale(
            num_adults, num_children, normalize=False
        )

        # Convert to reference family (2A2C)
        reference_scale = 2.1  # 1.0 + 0.5 + 0.6 for 2A2C
        ce["fcsuti_2a2c"] = ce["fcsuti"] * (
            reference_scale / ce["equiv_scale"]
        )

        # Get tenure type
        ce["tenure_type"] = get_tenure_type(ce)

        # Calculate 83% of median (47th-53rd percentile average) by tenure
        # This is the methodology used since September 2021
        # Previously used 33rd percentile (30th-36th range)
        base_thresholds = {}
        for tenure in [
            "renter",
            "owner_with_mortgage",
            "owner_without_mortgage",
        ]:
            subset = ce[ce["tenure_type"] == tenure]["fcsuti_2a2c"].dropna()
            if len(subset) > 0:
                # 83% of median approximation: average of 47th-53rd percentiles
                p47 = np.percentile(subset, 47)
                p53 = np.percentile(subset, 53)
                median_range = (p47 + p53) / 2
                base_thresholds[tenure] = 0.83 * median_range
            else:
                # Fallback to overall if specific tenure not available
                subset = ce["fcsuti_2a2c"].dropna()
                p47 = np.percentile(subset, 47)
                p53 = np.percentile(subset, 53)
                median_range = (p47 + p53) / 2
                base_thresholds[tenure] = 0.83 * median_range

        return base_thresholds

    except Exception as e:
        if use_published_fallback and target_year == 2024:
            print(
                f"Warning: CE calculation failed ({e}), "
                "using published BLS thresholds"
            )
            return BLS_PUBLISHED_THRESHOLDS_2024.copy()
        else:
            raise


def get_published_thresholds(year: int) -> dict[str, float]:
    """
    Get published BLS SPM thresholds for a given year.

    Args:
        year: Calendar year

    Returns:
        Dict with threshold values by tenure type

    Raises:
        ValueError: If published thresholds not available for the year
    """
    published = {
        2024: {
            "renter": 39430,
            "owner_with_mortgage": 39068,
            "owner_without_mortgage": 32586,
        },
        2023: {
            "renter": 36606,
            "owner_with_mortgage": 36192,
            "owner_without_mortgage": 30347,
        },
        2022: {
            "renter": 33402,
            "owner_with_mortgage": 32949,
            "owner_without_mortgage": 27679,
        },
    }

    if year in published:
        return published[year].copy()
    else:
        raise ValueError(
            f"Published thresholds not available for {year}. "
            f"Available years: {list(published.keys())}"
        )
