"""
Geographic adjustment (GEOADJ) calculation for SPM thresholds.

GEOADJ adjusts poverty thresholds for local housing costs using the formula:
    GEOADJ = (local_median_rent / national_median_rent) × 0.492 + 0.508

Where 0.492 is the housing portion of the SPM threshold for renters.

Data source: ACS Table B25031 (Median Gross Rent by Bedrooms)

Supported geographies:
- nation: National average (always 1.0)
- state: 50 states + DC
- county: ~3,200 counties
- metro_area: Metropolitan statistical areas
- congressional_district: 435 congressional districts
- puma: Public Use Microdata Areas
- tract: Census tracts (limited availability)
"""

import os
from functools import lru_cache
from typing import Union, Optional

import numpy as np
import pandas as pd

# Housing portion of SPM threshold (for renters)
HOUSING_SHARE = 0.492

# Supported geography types and their Census API geography strings
SUPPORTED_GEOGRAPHIES = {
    "nation": "us",
    "state": "state",
    "county": "county",
    "metro_area": "metropolitan statistical area/micropolitan statistical area",
    "congressional_district": "congressional district",
    "puma": "public use microdata area",
    "tract": "tract",
}

# Cache for lookup tables
_geoadj_cache: dict[tuple[str, int], pd.DataFrame] = {}


def calculate_geoadj_from_rent(
    local_rent: Union[float, np.ndarray],
    national_rent: float,
) -> Union[float, np.ndarray]:
    """
    Calculate GEOADJ from local and national median rents.

    Formula: GEOADJ = (local_rent / national_rent) × 0.492 + 0.508

    Args:
        local_rent: Local area median rent (scalar or array)
        national_rent: National median rent

    Returns:
        GEOADJ value(s)
    """
    rent_ratio = np.asarray(local_rent) / national_rent
    return rent_ratio * HOUSING_SHARE + (1 - HOUSING_SHARE)


def _get_census_api_key() -> str:
    """Get Census API key from environment."""
    key = os.environ.get("CENSUS_API_KEY")
    if not key:
        raise ValueError(
            "CENSUS_API_KEY environment variable not set. "
            "Get a free key at https://api.census.gov/data/key_signup.html"
        )
    return key


def _fetch_acs_median_rent(
    geography_type: str,
    year: int,
    state_fips: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch median 2-bedroom rent from ACS for a geography type.

    Uses ACS 5-year estimates, Table B25031.

    Args:
        geography_type: Type of geography (state, county, etc.)
        year: End year of ACS 5-year estimates
        state_fips: State FIPS code (required for sub-state geographies)

    Returns:
        DataFrame with geography_id and median_rent columns
    """
    try:
        from census import Census
    except ImportError:
        raise ImportError(
            "census package required. Install with: pip install census"
        )

    api_key = _get_census_api_key()
    c = Census(api_key)

    # B25031_004E = Median gross rent, 2 bedrooms
    variable = "B25031_004E"

    census_geo = SUPPORTED_GEOGRAPHIES[geography_type]

    if geography_type == "nation":
        data = c.acs5.get([variable], {"for": "us:*"}, year=year)
        df = pd.DataFrame(data)
        df["geography_id"] = "US"

    elif geography_type == "state":
        data = c.acs5.get([variable], {"for": "state:*"}, year=year)
        df = pd.DataFrame(data)
        df["geography_id"] = df["state"].str.zfill(2)

    elif geography_type == "county":
        if state_fips:
            data = c.acs5.get(
                [variable],
                {"for": "county:*", "in": f"state:{state_fips}"},
                year=year,
            )
        else:
            # Get all counties (may need to iterate by state)
            all_data = []
            for st in range(1, 57):  # State FIPS codes
                try:
                    data = c.acs5.get(
                        [variable],
                        {"for": "county:*", "in": f"state:{st:02d}"},
                        year=year,
                    )
                    all_data.extend(data)
                except Exception:
                    pass
            data = all_data
        df = pd.DataFrame(data)
        df["geography_id"] = df["state"].str.zfill(2) + df["county"].str.zfill(
            3
        )

    elif geography_type == "congressional_district":
        all_data = []
        for st in range(1, 57):
            try:
                data = c.acs5.get(
                    [variable],
                    {
                        "for": "congressional district:*",
                        "in": f"state:{st:02d}",
                    },
                    year=year,
                )
                all_data.extend(data)
            except Exception:
                pass
        df = pd.DataFrame(all_data)
        df["geography_id"] = df["state"].str.zfill(2) + df[
            "congressional district"
        ].str.zfill(2)

    elif geography_type == "puma":
        all_data = []
        for st in range(1, 57):
            try:
                data = c.acs5.get(
                    [variable],
                    {
                        "for": "public use microdata area:*",
                        "in": f"state:{st:02d}",
                    },
                    year=year,
                )
                all_data.extend(data)
            except Exception:
                pass
        df = pd.DataFrame(all_data)
        df["geography_id"] = df["state"].str.zfill(2) + df[
            "public use microdata area"
        ].str.zfill(5)

    elif geography_type == "tract":
        if not state_fips:
            raise ValueError("state_fips required for tract-level data")
        all_data = []
        # Get counties in state first, then tracts by county
        counties = c.acs5.get(
            ["NAME"],
            {"for": "county:*", "in": f"state:{state_fips}"},
            year=year,
        )
        for county in counties:
            try:
                data = c.acs5.get(
                    [variable],
                    {
                        "for": "tract:*",
                        "in": f"state:{state_fips} county:{county['county']}",
                    },
                    year=year,
                )
                all_data.extend(data)
            except Exception:
                pass
        df = pd.DataFrame(all_data)
        df["geography_id"] = (
            df["state"].str.zfill(2)
            + df["county"].str.zfill(3)
            + df["tract"].str.zfill(6)
        )

    elif geography_type == "metro_area":
        data = c.acs5.get(
            [variable],
            {
                "for": "metropolitan statistical area/micropolitan "
                "statistical area:*"
            },
            year=year,
        )
        df = pd.DataFrame(data)
        # MSA codes are 5 digits
        msa_col = [
            c
            for c in df.columns
            if "metropolitan" in c.lower() or "micropolitan" in c.lower()
        ]
        if msa_col:
            df["geography_id"] = df[msa_col[0]].str.zfill(5)
        else:
            df["geography_id"] = df.iloc[:, -1].str.zfill(5)

    else:
        raise ValueError(f"Unsupported geography type: {geography_type}")

    df["median_rent"] = pd.to_numeric(df[variable], errors="coerce")
    return df[["geography_id", "median_rent"]].dropna()


@lru_cache(maxsize=32)
def _get_national_median_rent(year: int) -> float:
    """Get national median 2-bedroom rent for a year (cached)."""
    df = _fetch_acs_median_rent("nation", year)
    return df["median_rent"].iloc[0]


def create_geoadj_lookup(
    geography_type: str,
    year: int,
    state_fips: Optional[str] = None,
) -> pd.DataFrame:
    """
    Create a GEOADJ lookup table for a geography type.

    Args:
        geography_type: Type of geography
        year: ACS 5-year end year
        state_fips: State FIPS code (required for some sub-state geos)

    Returns:
        DataFrame with geography_id, median_rent, and geoadj columns
    """
    cache_key = (geography_type, year, state_fips)

    # Check cache
    if cache_key in _geoadj_cache:
        return _geoadj_cache[cache_key]

    if geography_type not in SUPPORTED_GEOGRAPHIES:
        raise ValueError(
            f"Unsupported geography type: {geography_type}. "
            f"Supported: {list(SUPPORTED_GEOGRAPHIES.keys())}"
        )

    # Get local rents
    df = _fetch_acs_median_rent(geography_type, year, state_fips)

    # Get national rent
    national_rent = _get_national_median_rent(year)

    # Calculate GEOADJ
    df["geoadj"] = calculate_geoadj_from_rent(df["median_rent"], national_rent)

    # Clamp to reasonable range
    df["geoadj"] = df["geoadj"].clip(0.70, 1.50)

    # Cache the result
    _geoadj_cache[cache_key] = df

    return df


def get_geoadj(
    geography_type: str,
    geography_id: str,
    year: int,
) -> float:
    """
    Get GEOADJ for a specific geography.

    Args:
        geography_type: Type of geography (nation, state, county, etc.)
        geography_id: Geography identifier (FIPS code, etc.)
        year: Year for ACS data

    Returns:
        GEOADJ value

    Raises:
        ValueError: If geography type not supported or ID not found
    """
    if geography_type not in SUPPORTED_GEOGRAPHIES:
        raise ValueError(
            f"Unsupported geography type: {geography_type}. "
            f"Supported: {list(SUPPORTED_GEOGRAPHIES.keys())}"
        )

    # Check if data available for this year
    # ACS 5-year typically available 2009-present
    current_year = 2024  # TODO: Get dynamically
    if year > current_year:
        raise ValueError(
            f"ACS data not available for {year}. "
            f"Latest available: {current_year - 1}"
        )

    # Nation is always 1.0
    if geography_type == "nation":
        return 1.0

    # Get lookup table
    lookup = create_geoadj_lookup(geography_type, year)

    # Find the geography
    match = lookup[lookup["geography_id"] == geography_id]

    if len(match) == 0:
        raise ValueError(
            f"Geography ID '{geography_id}' not found for {geography_type}"
        )

    return match["geoadj"].iloc[0]


def clear_cache():
    """Clear the GEOADJ cache."""
    _geoadj_cache.clear()
    _get_national_median_rent.cache_clear()
