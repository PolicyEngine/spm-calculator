# Geographic Adjustment (GEOADJ)

Functions for calculating geographic housing cost adjustments.

Metro areas and nonmetro areas use the bundled official Census 2024 workbook.
Other geographies are built from ACS median rents and tenure-specific housing
shares.

## Functions

### calculate_geoadj_from_rent

```python
from spm_calculator.geoadj import calculate_geoadj_from_rent

calculate_geoadj_from_rent(
    local_rent: Union[float, np.ndarray],
    national_rent: float,
    tenure: str = "renter"
) -> Union[float, np.ndarray]
```

Calculate GEOADJ from local and national median rents.

**Formula:** `GEOADJ_t = (local_rent / national_rent) × housing_share_t + (1 - housing_share_t)`

2024 housing shares:
- `0.443` for renters
- `0.434` for owners with a mortgage
- `0.323` for owners without a mortgage

**Parameters:**

- `local_rent`: Local area median 2-bedroom rent (scalar or array)
- `national_rent`: National median 2-bedroom rent
- `tenure`: One of `renter`, `owner_with_mortgage`, `owner_without_mortgage`

**Returns:** GEOADJ value(s)

**Example:**

```python
from spm_calculator.geoadj import calculate_geoadj_from_rent

# National average
geoadj = calculate_geoadj_from_rent(1500, 1500, tenure="renter")
# 1.0

# High-cost area for renters
geoadj = calculate_geoadj_from_rent(3000, 1500, tenure="renter")
# 1.443

# Same rents, lower housing share for owners without a mortgage
geoadj = calculate_geoadj_from_rent(3000, 1500, tenure="owner_without_mortgage")
# 1.323
```

### get_geoadj

```python
from spm_calculator.geoadj import get_geoadj

get_geoadj(
    geography_type: str,
    geography_id: str,
    year: int,
    tenure: str = "renter"
) -> float
```

Get GEOADJ for a specific geography.

**Parameters:**

- `geography_type`: One of the supported geography types
- `geography_id`: FIPS code or other identifier
- `year`: ACS 5-year end year for custom geographies, or bundled metro year
- `tenure`: One of `renter`, `owner_with_mortgage`, `owner_without_mortgage`

**Returns:** GEOADJ value

**Raises:**

- `ValueError`: If geography type is unsupported, the ID is not found, or ACS data is not available for that year

**Example:**

```python
from spm_calculator.geoadj import get_geoadj

# Official New York metro adjustment from bundled Census data
nyc_geoadj = get_geoadj("metro_area", "35620", year=2024, tenure="renter")
# 1.159928988080142

# National reference is always 1.0
us_geoadj = get_geoadj("nation", "US", year=2024, tenure="renter")
# 1.0
```

### create_geoadj_lookup

```python
from spm_calculator.geoadj import create_geoadj_lookup

create_geoadj_lookup(
    geography_type: str,
    year: int,
    state_fips: Optional[str] = None,
    tenure: str = "renter"
) -> pd.DataFrame
```

Create a lookup table of GEOADJ values for all geographies of a type.

**Parameters:**

- `geography_type`: Type of geography
- `year`: ACS 5-year end year or bundled metro year
- `state_fips`: State FIPS code, required for tract-level ACS data
- `tenure`: Tenure used for the adjustment calculation

**Returns:**

- Metro areas: DataFrame with columns `geography_id`, `rent_index`, `geoadj`
- Other geographies: DataFrame with columns `geography_id`, `median_rent`, `geoadj`

**Example:**

```python
from spm_calculator.geoadj import create_geoadj_lookup

# Official metro adjustments
metros = create_geoadj_lookup("metro_area", year=2024, tenure="renter")
print(metros.head())

# Custom ACS geographies
states = create_geoadj_lookup("state", year=2023, tenure="renter")
print(states.head())
```

## Constants

### VALID_TENURE_TYPES

```python
("owner_with_mortgage", "owner_without_mortgage", "renter")
```

### TENURE_HOUSING_SHARES

```python
{
    "owner_with_mortgage": 0.434,
    "owner_without_mortgage": 0.323,
    "renter": 0.443,
}
```

These are the 2024 housing shares used in the ACS-based GEOADJ formula and to
reproduce the official bundled metro thresholds.

## Related Functions

- `get_metro_rent_index(metro_code, year=2024)` returns the raw Census rent index.
- `get_metro_geoadj(metro_code, tenure="renter", year=2024)` returns the tenure-specific official metro adjustment.
- `list_metro_areas(year=2024)` returns bundled metro names, codes, rent indexes, and reference thresholds.

## Caching

GEOADJ lookup tables are cached in memory after first retrieval. To clear the cache:

```python
from spm_calculator.geoadj import clear_cache

clear_cache()
```
