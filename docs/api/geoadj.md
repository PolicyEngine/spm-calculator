# Geographic Adjustment (GEOADJ)

Functions for calculating geographic housing cost adjustments.

## Functions

### calculate_geoadj_from_rent

```python
from spm_calculator.geoadj import calculate_geoadj_from_rent

calculate_geoadj_from_rent(
    local_rent: Union[float, np.ndarray],
    national_rent: float
) -> Union[float, np.ndarray]
```

Calculate GEOADJ from local and national median rents.

**Formula:** `GEOADJ = (local_rent / national_rent) × 0.492 + 0.508`

**Parameters:**

- `local_rent`: Local area median 2-bedroom rent (scalar or array)
- `national_rent`: National median 2-bedroom rent

**Returns:** GEOADJ value(s)

**Example:**

```python
from spm_calculator.geoadj import calculate_geoadj_from_rent

# National average
geoadj = calculate_geoadj_from_rent(1500, 1500)
# 1.0

# High-cost area (double national rent)
geoadj = calculate_geoadj_from_rent(3000, 1500)
# 1.492
```

### get_geoadj

```python
from spm_calculator.geoadj import get_geoadj

get_geoadj(
    geography_type: str,
    geography_id: str,
    year: int
) -> float
```

Get GEOADJ for a specific geography from ACS data.

**Parameters:**

- `geography_type`: One of the supported geography types
- `geography_id`: FIPS code or other identifier
- `year`: ACS 5-year end year

**Returns:** GEOADJ value

**Raises:**

- `ValueError`: If geography type not supported or ID not found

**Example:**

```python
from spm_calculator.geoadj import get_geoadj

# California
ca_geoadj = get_geoadj("state", "06", year=2022)
# ~1.15

# West Virginia
wv_geoadj = get_geoadj("state", "54", year=2022)
# ~0.85
```

### create_geoadj_lookup

```python
from spm_calculator.geoadj import create_geoadj_lookup

create_geoadj_lookup(
    geography_type: str,
    year: int,
    state_fips: Optional[str] = None
) -> pd.DataFrame
```

Create a lookup table of GEOADJ values for all geographies of a type.

**Parameters:**

- `geography_type`: Type of geography
- `year`: ACS 5-year end year
- `state_fips`: State FIPS code (required for tract-level)

**Returns:** DataFrame with columns `geography_id`, `median_rent`, `geoadj`

**Example:**

```python
from spm_calculator.geoadj import create_geoadj_lookup

# All states
states = create_geoadj_lookup("state", year=2022)
print(states.head())
#   geography_id  median_rent  geoadj
# 0           01       1050.0   0.852
# 1           02       1450.0   0.984
# ...

# All congressional districts
districts = create_geoadj_lookup("congressional_district", year=2022)
print(len(districts))
# 435+
```

## Constants

### SUPPORTED_GEOGRAPHIES

```python
SUPPORTED_GEOGRAPHIES = {
    "nation": "us",
    "state": "state",
    "county": "county",
    "metro_area": "metropolitan statistical area/micropolitan statistical area",
    "congressional_district": "congressional district",
    "puma": "public use microdata area",
    "tract": "tract",
}
```

### HOUSING_SHARE

```python
HOUSING_SHARE = 0.492
```

The housing portion of the SPM threshold for renters, used in the GEOADJ formula.

## Caching

GEOADJ lookup tables are cached in memory after first retrieval. To clear the cache:

```python
from spm_calculator.geoadj import clear_cache

clear_cache()
```
