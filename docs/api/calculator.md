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
- `use_published_thresholds`: If True, use published BLS thresholds when available. If False, calculate from CE Survey data.

**Example:**

```python
calc = SPMCalculator(year=2024)
```

### Methods

#### get_base_thresholds

```python
get_base_thresholds() -> dict[str, float]
```

Get base SPM thresholds by tenure type for the reference family (2 adults, 2 children) before geographic adjustment.

**Returns:** Dict with keys `'renter'`, `'owner_with_mortgage'`, `'owner_without_mortgage'`

**Example:**

```python
calc = SPMCalculator(year=2024)
base = calc.get_base_thresholds()
# {'renter': 39430, 'owner_with_mortgage': 39068, 'owner_without_mortgage': 32586}
```

#### get_geoadj

```python
get_geoadj(geography_type: str, geography_id: str) -> float
```

Get geographic adjustment factor for a specific location.

**Parameters:**

- `geography_type`: One of `nation`, `state`, `county`, `congressional_district`, `metro_area`, `puma`, `tract`
- `geography_id`: FIPS code or other identifier

**Returns:** GEOADJ value (typically 0.84 to 1.27)

**Example:**

```python
calc = SPMCalculator(year=2024)
geoadj = calc.get_geoadj("state", "06")  # California
# ~1.15
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
    geography_type="congressional_district",
    geography_id="0611"
)
# ~$45,000 (varies by actual rent data)
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
- `tenure`: Tenure type(s) - single value broadcast to all, or per-unit
- `geography_type`: Type of geography (same for all units)
- `geography_ids`: Geography ID(s) - single value broadcast to all, or per-unit

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
    geography_type="state",
    geography_ids=["06", "54", "06"]
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
