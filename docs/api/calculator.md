# SPMCalculator

The main calculator class for SPM thresholds.

## Class: SPMCalculator

```python
from spm_calculator import SPMCalculator
```

### Constructor

```python
SPMCalculator(year: int, use_published_thresholds: bool = True)
```

**Parameters:**

- `year`: Target year for threshold calculation
- `use_published_thresholds`: If `True`, use published or forecast thresholds from `forecast.py`. If `False`, reconstruct the thresholds from CE Survey data with the FCSUti CPI adjustment.

**Example:**

```python
calc = SPMCalculator(year=2024)
```

### Methods

#### get_base_thresholds

```python
get_base_thresholds() -> dict[str, float]
```

Get reference-family SPM thresholds by tenure type before geographic adjustment.

**Returns:** Dict with keys `'renter'`, `'owner_with_mortgage'`, `'owner_without_mortgage'`

**Example:**

```python
calc = SPMCalculator(year=2024)
base = calc.get_base_thresholds()
# {'renter': 39430, 'owner_with_mortgage': 39068, 'owner_without_mortgage': 32586}
```

#### get_geoadj

```python
get_geoadj(
    geography_type: str,
    geography_id: str,
    tenure: str = "renter"
) -> float
```

Get a tenure-specific geographic adjustment factor for a location.

**Parameters:**

- `geography_type`: One of `nation`, `state`, `county`, `congressional_district`, `metro_area`, `puma`, `tract`
- `geography_id`: FIPS code or other identifier
- `tenure`: One of `'renter'`, `'owner_with_mortgage'`, `'owner_without_mortgage'`

**Returns:** Tenure-specific GEOADJ value

**Example:**

```python
calc = SPMCalculator(year=2024)
geoadj = calc.get_geoadj("metro_area", "35620", tenure="renter")
# 1.159928988080142
```

#### calculate_threshold

```python
calculate_threshold(
    num_adults: int,
    num_children: int,
    tenure: str,
    geography_type: str,
    geography_id: str
) -> float
```

Calculate SPM threshold for a specific SPM unit and location.

**Parameters:**

- `num_adults`: Number of adults (18+) in the SPM unit
- `num_children`: Number of children (under 18) in the SPM unit
- `tenure`: One of `'renter'`, `'owner_with_mortgage'`, `'owner_without_mortgage'`
- `geography_type`: Type of geography
- `geography_id`: Geography identifier

**Returns:** SPM threshold in dollars

**Example:**

```python
calc = SPMCalculator(year=2024)
threshold = calc.calculate_threshold(
    num_adults=2,
    num_children=2,
    tenure="renter",
    geography_type="metro_area",
    geography_id="35620"
)
# 45736.0
```

#### calculate_thresholds

```python
calculate_thresholds(
    num_adults: Union[int, np.ndarray],
    num_children: Union[int, np.ndarray],
    tenure: Union[str, Sequence[str]],
    geography_type: str,
    geography_ids: Union[str, Sequence[str]]
) -> np.ndarray
```

Calculate SPM thresholds for multiple SPM units (vectorized).

**Parameters:**

- `num_adults`: Number of adults for each unit (scalar or array)
- `num_children`: Number of children for each unit (scalar or array)
- `tenure`: Tenure type(s), either a single broadcast value or one per unit
- `geography_type`: Type of geography, shared by all units
- `geography_ids`: Geography ID(s), either a single broadcast value or one per unit

**Returns:** NumPy array of SPM thresholds

**Example:**

```python
import numpy as np
from spm_calculator import SPMCalculator

calc = SPMCalculator(year=2024)
thresholds = calc.calculate_thresholds(
    num_adults=np.array([1, 2, 2]),
    num_children=np.array([0, 0, 2]),
    tenure=["renter", "renter", "owner_with_mortgage"],
    geography_type="metro_area",
    geography_ids=["1002", "35620", "41940"]
)
```

### Properties

#### supported_geographies

```python
supported_geographies: list[str]
```

List of supported geography types.

**Example:**

```python
calc = SPMCalculator(year=2024)
print(calc.supported_geographies)
# ['nation', 'state', 'county', 'metro_area', 'congressional_district', 'puma', 'tract']
```

## Notes

- `metro_area` uses the bundled official Census metro workbook.
- Other subnational geographies use ACS median rents and require the Census API path.
- Forecast years preserve the latest bundled metro adjustments and forecast only the national base thresholds.
