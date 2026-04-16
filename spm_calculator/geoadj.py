"""
Geographic adjustments for SPM thresholds.

For non-metro custom geographies, adjustments are built from ACS median rents
and the tenure-specific housing share of the SPM threshold.

For metro areas, the bundled 2024 Census workbook is authoritative.
"""

from __future__ import annotations

import json
import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence, Union

import numpy as np
import pandas as pd

VALID_TENURE_TYPES = (
    "owner_with_mortgage",
    "owner_without_mortgage",
    "renter",
)

# These 2024 tenure-specific housing shares exactly reproduce the official
# 2024 Census metro thresholds when combined with the published national BLS
# thresholds and the published metro rent index.
TENURE_HOUSING_SHARES = {
    "owner_with_mortgage": 0.434,
    "owner_without_mortgage": 0.323,
    "renter": 0.443,
}

SUPPORTED_GEOGRAPHIES = {
    "nation": "us",
    "state": "state",
    "county": "county",
    "metro_area": "metropolitan statistical area/micropolitan statistical area",
    "congressional_district": "congressional district",
    "puma": "public use microdata area",
    "tract": "tract",
}

_DATA_DIR = Path(__file__).parent / "data"
_geoadj_cache: dict[tuple[str, int, Optional[str], str], pd.DataFrame] = {}


def _validate_tenure(tenure: str) -> None:
    if tenure not in VALID_TENURE_TYPES:
        raise ValueError(
            f"Invalid tenure type: {tenure}. "
            f"Must be one of: {list(VALID_TENURE_TYPES)}"
        )


def _maybe_scalar(value: np.ndarray) -> Union[float, np.ndarray]:
    if value.ndim == 0:
        return float(value)
    return value


def get_housing_share(tenure: str) -> float:
    """Get the tenure-specific housing share used in geographic adjustment."""
    _validate_tenure(tenure)
    return TENURE_HOUSING_SHARES[tenure]


def calculate_geoadj_from_rent(
    local_rent: Union[float, np.ndarray],
    national_rent: float,
    tenure: str = "renter",
) -> Union[float, np.ndarray]:
    """
    Calculate a tenure-specific SPM geographic adjustment from rents.
    """
    share = get_housing_share(tenure)
    rent_ratio = np.asarray(local_rent, dtype=float) / float(national_rent)
    geoadj = rent_ratio * share + (1.0 - share)
    return _maybe_scalar(geoadj)


def get_latest_available_acs_year(today: Optional[date] = None) -> int:
    """
    Return the latest ACS 5-year end-year that should be publicly available.
    """
    today = today or date.today()
    return today.year - 1 if today.month == 12 else today.year - 2


def _available_bundled_metro_years() -> list[int]:
    years = []
    for path in _DATA_DIR.glob("metro_geoadj_*.json"):
        try:
            years.append(int(path.stem.rsplit("_", 1)[-1]))
        except ValueError:
            pass
    return sorted(years)


def _resolve_bundled_metro_year(year: int) -> int:
    available = _available_bundled_metro_years()
    if not available:
        raise ValueError("No bundled metro data available.")
    if year in available:
        return year
    if year > available[-1]:
        return available[-1]
    raise ValueError(
        f"No bundled metro data for year {year}. "
        f"Available: {available or 'none'}"
    )


@lru_cache(maxsize=8)
def _load_bundled_cd_data(year: int = 2023) -> dict:
    data_file = _DATA_DIR / f"cd_geoadj_{year}.json"
    if not data_file.exists():
        available = [f.stem for f in _DATA_DIR.glob("cd_geoadj_*.json")]
        raise ValueError(
            f"No bundled CD data for year {year}. "
            f"Available: {available or 'none'}"
        )
    with open(data_file) as f:
        return json.load(f)


def _normalize_cd_geoid(cd_geoid: Union[str, int], cds: dict) -> str:
    cd_str = str(int(cd_geoid))
    if cd_str in cds:
        return cd_str
    cd_str_padded = cd_str.zfill(4)
    if cd_str_padded in cds:
        return cd_str_padded
    raise ValueError(
        f"Congressional district '{cd_geoid}' not found in bundled data. "
        f"Use format like '612' for CA-12 or '3601' for NY-01."
    )


def get_cd_geoadj(
    cd_geoid: Union[str, int],
    year: int = 2023,
    tenure: str = "renter",
) -> float:
    """
    Get a tenure-specific congressional-district adjustment from bundled rents.
    """
    _validate_tenure(tenure)
    data = _load_bundled_cd_data(year)
    cds = data["congressional_districts"]
    cd_str = _normalize_cd_geoid(cd_geoid, cds)
    entry = cds[cd_str]

    if "median_2br_rent" in entry:
        return calculate_geoadj_from_rent(
            entry["median_2br_rent"],
            data["national_median_2br_rent"],
            tenure=tenure,
        )

    # Backward-compatible fallback for older bundled files.
    return entry["geoadj"]


def get_cd_geoadj_batch(
    cd_geoids: Sequence[Union[str, int]],
    year: int = 2023,
    tenure: str = "renter",
) -> np.ndarray:
    _validate_tenure(tenure)
    return np.array(
        [
            get_cd_geoadj(cd_geoid, year=year, tenure=tenure)
            for cd_geoid in cd_geoids
        ],
        dtype=np.float64,
    )


def get_bundled_cd_data(year: int = 2023) -> dict:
    # Return a shallow copy so callers can't mutate the lru_cached dict.
    return dict(_load_bundled_cd_data(year))


@lru_cache(maxsize=8)
def _load_bundled_metro_data(year: int = 2024) -> dict:
    resolved_year = _resolve_bundled_metro_year(year)
    data_file = _DATA_DIR / f"metro_geoadj_{resolved_year}.json"
    with open(data_file) as f:
        data = json.load(f)

    if "nationalThresholds" not in data:
        from .forecast import get_thresholds

        national_thresholds = get_thresholds(resolved_year)
        data["nationalThresholds"] = national_thresholds
        data["housingShares"] = TENURE_HOUSING_SHARES.copy()
        for info in data["metroAreas"].values():
            rent_index = info.get("rentIndex", info.get("geoadj"))
            info["rentIndex"] = rent_index
            info["referenceThresholds"] = {
                tenure: round(
                    national_thresholds[tenure]
                    * (rent_index * share + (1.0 - share))
                )
                for tenure, share in TENURE_HOUSING_SHARES.items()
            }
            info["adjustments"] = {
                tenure: (
                    info["referenceThresholds"][tenure]
                    / national_thresholds[tenure]
                )
                for tenure in VALID_TENURE_TYPES
            }

    return data


def _metro_info(metro_code: str, year: int = 2024) -> dict:
    data = _load_bundled_metro_data(year)
    metros = data["metroAreas"]
    if metro_code not in metros:
        raise ValueError(
            f"Metro area '{metro_code}' not found in bundled data. "
            f"Use CBSA codes like '35620' for NYC or state codes like '1002' for Alabama Nonmetro."
        )
    return metros[metro_code]


def get_metro_rent_index(
    metro_code: Union[str, Sequence[str]],
    year: int = 2024,
) -> Union[float, np.ndarray]:
    """
    Get the raw Census median-rent index for metro areas.
    """
    data = _load_bundled_metro_data(year)
    metros = data["metroAreas"]

    if isinstance(metro_code, str):
        if metro_code not in metros:
            raise ValueError(
                f"Metro area '{metro_code}' not found in bundled data."
            )
        info = metros[metro_code]
        return info.get("rentIndex", info.get("geoadj"))

    results = np.zeros(len(metro_code), dtype=np.float64)
    for i, code in enumerate(metro_code):
        if code not in metros:
            raise ValueError(f"Metro area '{code}' not found in bundled data.")
        info = metros[code]
        results[i] = info.get("rentIndex", info.get("geoadj"))
    return results


def _broadcast_scalar_or_sequence(
    values: Union[str, Sequence[str]],
    length: int,
) -> list[str]:
    if isinstance(values, str):
        return [values] * length
    values = list(values)
    if len(values) != length:
        raise ValueError("Input sequences must have matching lengths.")
    return values


def get_metro_geoadj(
    metro_code: Union[str, Sequence[str]],
    tenure: Union[str, Sequence[str]] = "renter",
    year: int = 2024,
) -> Union[float, np.ndarray]:
    """
    Get the tenure-specific official metro adjustment factor.
    """
    data = _load_bundled_metro_data(year)
    metros = data["metroAreas"]

    if isinstance(metro_code, str):
        tenure_str = tenure if isinstance(tenure, str) else list(tenure)[0]
        _validate_tenure(tenure_str)
        if metro_code not in metros:
            raise ValueError(
                f"Metro area '{metro_code}' not found in bundled data."
            )
        info = metros[metro_code]
        if "adjustments" in info:
            return info["adjustments"][tenure_str]
        rent_index = info.get("rentIndex", info.get("geoadj"))
        return calculate_geoadj_from_rent(rent_index, 1.0, tenure=tenure_str)

    tenure_list = _broadcast_scalar_or_sequence(tenure, len(metro_code))
    results = np.zeros(len(metro_code), dtype=np.float64)
    for i, (code, tenure_value) in enumerate(zip(metro_code, tenure_list)):
        _validate_tenure(tenure_value)
        if code not in metros:
            raise ValueError(f"Metro area '{code}' not found in bundled data.")
        info = metros[code]
        if "adjustments" in info:
            results[i] = info["adjustments"][tenure_value]
        else:
            rent_index = info.get("rentIndex", info.get("geoadj"))
            results[i] = calculate_geoadj_from_rent(
                rent_index, 1.0, tenure=tenure_value
            )
    return results


def get_bundled_metro_data(year: int = 2024) -> dict:
    # Return a shallow copy so callers can't mutate the lru_cached dict.
    return dict(_load_bundled_metro_data(year))


def list_metro_areas(year: int = 2024) -> list[dict]:
    data = _load_bundled_metro_data(year)
    metros = data["metroAreas"]
    result = []
    for code, info in metros.items():
        result.append(
            {
                "code": code,
                "name": info["name"],
                "rentIndex": info.get("rentIndex", info.get("geoadj")),
                "adjustments": info.get("adjustments"),
                "referenceThresholds": info.get("referenceThresholds"),
            }
        )
    return sorted(result, key=lambda x: x["name"])


def _get_census_api_key() -> str:
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
    try:
        from census import Census
    except ImportError:
        raise ImportError(
            "census package required. Install with: pip install census"
        )

    api_key = _get_census_api_key()
    c = Census(api_key)
    variable = "B25031_004E"

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
            all_data = []
            for st in range(1, 57):
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
    df = _fetch_acs_median_rent("nation", year)
    return float(df["median_rent"].iloc[0])


def _create_bundled_metro_lookup(year: int, tenure: str) -> pd.DataFrame:
    data = _load_bundled_metro_data(year)
    rows = []
    for code, info in data["metroAreas"].items():
        rows.append(
            {
                "geography_id": code,
                "rent_index": info.get("rentIndex", info.get("geoadj")),
                "geoadj": get_metro_geoadj(code, tenure=tenure, year=year),
            }
        )
    return pd.DataFrame(rows)


def create_geoadj_lookup(
    geography_type: str,
    year: int,
    state_fips: Optional[str] = None,
    tenure: str = "renter",
) -> pd.DataFrame:
    """
    Create a tenure-specific lookup table of geographic adjustments.
    """
    _validate_tenure(tenure)

    if geography_type not in SUPPORTED_GEOGRAPHIES:
        raise ValueError(
            f"Unsupported geography type: {geography_type}. "
            f"Supported: {list(SUPPORTED_GEOGRAPHIES.keys())}"
        )

    cache_key = (geography_type, year, state_fips, tenure)
    if cache_key in _geoadj_cache:
        return _geoadj_cache[cache_key]

    if geography_type == "metro_area":
        df = _create_bundled_metro_lookup(year, tenure)
        _geoadj_cache[cache_key] = df
        return df

    df = _fetch_acs_median_rent(geography_type, year, state_fips)
    national_rent = _get_national_median_rent(year)
    df["geoadj"] = calculate_geoadj_from_rent(
        df["median_rent"], national_rent, tenure=tenure
    )
    _geoadj_cache[cache_key] = df
    return df


def get_geoadj(
    geography_type: str,
    geography_id: str,
    year: int,
    tenure: str = "renter",
) -> float:
    """
    Get a tenure-specific geographic adjustment for a single geography.
    """
    _validate_tenure(tenure)

    if geography_type not in SUPPORTED_GEOGRAPHIES:
        raise ValueError(
            f"Unsupported geography type: {geography_type}. "
            f"Supported: {list(SUPPORTED_GEOGRAPHIES.keys())}"
        )

    if geography_type == "nation":
        return 1.0

    if geography_type != "metro_area":
        latest_available = get_latest_available_acs_year()
        if year > latest_available:
            raise ValueError(
                f"ACS data not available for {year}. "
                f"Latest available: {latest_available}"
            )

    lookup = create_geoadj_lookup(
        geography_type, year, state_fips=None, tenure=tenure
    )
    match = lookup[lookup["geography_id"] == geography_id]
    if len(match) == 0:
        raise ValueError(
            f"Geography ID '{geography_id}' not found for {geography_type}"
        )
    return float(match["geoadj"].iloc[0])


def clear_cache() -> None:
    _geoadj_cache.clear()
    _get_national_median_rent.cache_clear()
