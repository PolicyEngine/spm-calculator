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

For congressional districts, bundled data is available via get_cd_geoadj()
which works without a Census API key.
"""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence, Union

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


# =============================================================================
# Bundled data for offline lookups (no Census API key required)
# =============================================================================

_DATA_DIR = Path(__file__).parent / "data"
_bundled_cd_data: dict[int, dict] = {}


@lru_cache(maxsize=8)
def _load_bundled_cd_data(year: int = 2023) -> dict:
    """
    Load bundled congressional district GEOADJ data.

    Args:
        year: Data year (currently only 2023 available)

    Returns:
        Dict with 'congressional_districts' mapping CD GEOIDs to geoadj data
    """
    data_file = _DATA_DIR / f"cd_geoadj_{year}.json"
    if not data_file.exists():
        available = [f.stem for f in _DATA_DIR.glob("cd_geoadj_*.json")]
        raise ValueError(
            f"No bundled CD data for year {year}. "
            f"Available: {available or 'none'}"
        )

    with open(data_file) as f:
        return json.load(f)


def get_cd_geoadj(
    cd_geoid: Union[str, int],
    year: int = 2023,
) -> float:
    """
    Get GEOADJ for a congressional district using bundled data.

    This function uses pre-computed data bundled with the package,
    so it works without a Census API key.

    Args:
        cd_geoid: Congressional district GEOID (e.g., "612" or "0612" for CA-12,
            "3601" for NY-01). Can be string or int.
        year: Data year (default 2023)

    Returns:
        GEOADJ value for the congressional district

    Raises:
        ValueError: If CD GEOID not found in bundled data

    Example:
        >>> get_cd_geoadj("612")  # CA-12 (San Francisco)
        1.3497
        >>> get_cd_geoadj(3612)   # NY-12 (Manhattan)
        1.5
        >>> get_cd_geoadj("101")  # AL-01
        0.8757
    """
    data = _load_bundled_cd_data(year)
    cds = data["congressional_districts"]

    # Normalize to string without leading zeros
    cd_str = str(int(cd_geoid))

    if cd_str not in cds:
        # Try with leading zeros (4-digit format)
        cd_str_padded = cd_str.zfill(4)
        if cd_str_padded not in cds:
            raise ValueError(
                f"Congressional district '{cd_geoid}' not found in bundled data. "
                f"Use format like '612' for CA-12 or '3601' for NY-01."
            )
        cd_str = cd_str_padded

    return cds[cd_str]["geoadj"]


def get_cd_geoadj_batch(
    cd_geoids: Sequence[Union[str, int]],
    year: int = 2023,
) -> np.ndarray:
    """
    Get GEOADJ values for multiple congressional districts (vectorized).

    Args:
        cd_geoids: Sequence of CD GEOIDs
        year: Data year (default 2023)

    Returns:
        Array of GEOADJ values

    Example:
        >>> get_cd_geoadj_batch(["612", "3612", "101"])
        array([1.3497, 1.5   , 0.8757])
    """
    data = _load_bundled_cd_data(year)
    cds = data["congressional_districts"]

    results = np.zeros(len(cd_geoids), dtype=np.float64)

    for i, cd_geoid in enumerate(cd_geoids):
        cd_str = str(int(cd_geoid))
        if cd_str in cds:
            results[i] = cds[cd_str]["geoadj"]
        elif cd_str.zfill(4) in cds:
            results[i] = cds[cd_str.zfill(4)]["geoadj"]
        else:
            raise ValueError(
                f"Congressional district '{cd_geoid}' not found in bundled data."
            )

    return results


def get_bundled_cd_data(year: int = 2023) -> dict:
    """
    Get the full bundled congressional district data.

    Useful for inspecting available CDs or getting rent data.

    Args:
        year: Data year (default 2023)

    Returns:
        Dict with keys:
        - 'year': Data year
        - 'national_median_2br_rent': National median rent
        - 'housing_share': Housing share used in GEOADJ formula
        - 'congressional_districts': Dict mapping CD GEOIDs to
          {geoadj, name, median_2br_rent}

    Example:
        >>> data = get_bundled_cd_data()
        >>> data["national_median_2br_rent"]
        1338.0
        >>> data["congressional_districts"]["612"]["name"]
        'Congressional District 12 (118th Congress), California'
    """
    return _load_bundled_cd_data(year)


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

    SUPPORTED_GEOGRAPHIES[geography_type]

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
