"""
FCSUti CPI-U Composite Index calculation.

The FCSUti (Food, Clothing, Shelter, Utilities, telephone, internet) price
index is used to adjust CE expenditure data to threshold-year dollars.

This replaces the All Items CPI-U that was used in earlier SPM methodology.

Components and approximate weights (based on CE expenditure shares):
- Food (at home + away): ~30%
- Apparel: ~5%
- Shelter: ~45%
- Utilities (fuel and utilities): ~12%
- Telephone and internet services: ~8%

Reference:
- BLS SPM Thresholds methodology
- https://www.bls.gov/pir/spm/spm_thresholds_2024.htm
"""

from functools import lru_cache
from typing import Optional

import pandas as pd

# BLS CPI series IDs for FCSUti components
# Source: https://www.bls.gov/cpi/data.htm
CPI_SERIES = {
    "food": "CUUR0000SAF",  # Food
    "food_at_home": "CUUR0000SAF11",  # Food at home
    "food_away": "CUUR0000SEFV",  # Food away from home
    "apparel": "CUUR0000SAA",  # Apparel
    "shelter": "CUUR0000SAH1",  # Shelter
    "utilities": "CUUR0000SAH2",  # Fuels and utilities
    "telephone": "CUUR0000SEED",  # Telephone services
    "internet": "CUUR0000SEEE",  # Internet services and electronic info
    "all_items": "CUUR0000SA0",  # All items (for reference)
}

# Approximate expenditure weights for FCSUti composite
# These are based on CE Survey expenditure shares for consumer units with children
# Weights should sum to 1.0
FCSUTI_WEIGHTS = {
    "food": 0.30,
    "apparel": 0.05,
    "shelter": 0.45,
    "utilities": 0.12,
    "telephone": 0.04,
    "internet": 0.04,
}


def fetch_bls_cpi_series(
    series_id: str,
    start_year: int = 2010,
    end_year: int = 2024,
) -> pd.Series:
    """
    Fetch CPI series data from BLS API.

    Args:
        series_id: BLS series ID (e.g., "CUUR0000SA0")
        start_year: Start year for data
        end_year: End year for data

    Returns:
        Series with annual average CPI values indexed by year
    """
    import requests

    # BLS Public Data API (no registration required for small requests)
    url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

    payload = {
        "seriesid": [series_id],
        "startyear": str(start_year),
        "endyear": str(end_year),
        "annualaverage": True,
    }

    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()

    data = response.json()

    if data["status"] != "REQUEST_SUCCEEDED":
        raise ValueError(f"BLS API error: {data.get('message', 'Unknown error')}")

    # Extract annual averages
    series_data = data["Results"]["series"][0]["data"]

    # Filter to annual averages (period = "M13")
    annual = [d for d in series_data if d["period"] == "M13"]

    result = pd.Series(
        {int(d["year"]): float(d["value"]) for d in annual},
        name=series_id,
    ).sort_index()

    return result


@lru_cache(maxsize=8)
def get_fcsuti_cpi(
    start_year: int = 2010,
    end_year: int = 2024,
    base_year: int = 2024,
) -> pd.Series:
    """
    Calculate the FCSUti composite CPI index.

    Args:
        start_year: Start year for index
        end_year: End year for index
        base_year: Year to set index = 100

    Returns:
        Series with FCSUti CPI values indexed by year
    """
    components = {}

    # Fetch each component series
    for component, series_id in CPI_SERIES.items():
        if component in FCSUTI_WEIGHTS:
            try:
                components[component] = fetch_bls_cpi_series(
                    series_id, start_year, end_year
                )
            except Exception as e:
                print(f"Warning: Could not fetch {component} CPI: {e}")

    if not components:
        raise ValueError("Could not fetch any CPI component data")

    # Combine into DataFrame
    df = pd.DataFrame(components)

    # Calculate weighted composite
    fcsuti = pd.Series(0.0, index=df.index)
    total_weight = 0.0

    for component, weight in FCSUTI_WEIGHTS.items():
        if component in df.columns:
            fcsuti += df[component] * weight
            total_weight += weight

    # Normalize if we didn't get all components
    if total_weight < 1.0:
        fcsuti = fcsuti / total_weight

    # Rebase to base_year = 100
    if base_year in fcsuti.index:
        fcsuti = fcsuti / fcsuti[base_year] * 100

    fcsuti.name = "FCSUti CPI-U"
    return fcsuti


def get_fcsuti_inflation_factor(
    from_year: int,
    to_year: int,
) -> float:
    """
    Get inflation adjustment factor between two years using FCSUti CPI.

    Args:
        from_year: Base year
        to_year: Target year

    Returns:
        Inflation factor (multiply from_year values by this to get to_year values)
    """
    try:
        fcsuti = get_fcsuti_cpi(
            start_year=min(from_year, to_year) - 1,
            end_year=max(from_year, to_year) + 1,
            base_year=from_year,
        )
        return fcsuti[to_year] / 100.0
    except Exception as e:
        # Fallback to simple estimate if BLS API unavailable
        print(f"Warning: Could not get FCSUti CPI ({e}), using estimate")
        # Use ~4% annual inflation as fallback (recent FCSUti average)
        years_diff = to_year - from_year
        return 1.04**years_diff


# Pre-computed FCSUti inflation factors for common year pairs
# These can be used when BLS API is unavailable
PRECOMPUTED_FCSUTI_FACTORS = {
    # (from_year, to_year): factor
    (2018, 2024): 1.26,  # ~4.0% annual
    (2019, 2024): 1.22,  # ~4.1% annual
    (2020, 2024): 1.19,  # ~4.5% annual (pandemic effects)
    (2021, 2024): 1.15,  # ~4.8% annual
    (2022, 2024): 1.08,  # ~3.9% annual
    (2023, 2024): 1.04,  # 4.0% (published)
}


def get_precomputed_fcsuti_factor(
    from_year: int,
    to_year: int,
) -> Optional[float]:
    """
    Get pre-computed FCSUti inflation factor if available.

    Returns None if not pre-computed.
    """
    return PRECOMPUTED_FCSUTI_FACTORS.get((from_year, to_year))
