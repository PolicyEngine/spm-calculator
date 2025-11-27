# Quickstart

## Installation

```bash
pip install spm-calculator
```

You'll also need a Census API key for geographic data:

1. Get a free key at [https://api.census.gov/data/key_signup.html](https://api.census.gov/data/key_signup.html)
2. Set it as an environment variable:

```bash
export CENSUS_API_KEY="your_key_here"
```

## Basic Usage

### Single Threshold Calculation

```python
from spm_calculator import SPMCalculator

# Initialize calculator for 2024
calc = SPMCalculator(year=2024)

# Calculate threshold for reference family (2 adults, 2 children)
# as a renter at the national level
threshold = calc.calculate_threshold(
    num_adults=2,
    num_children=2,
    tenure="renter",
    geography_type="nation",
    geography_id="US"
)
print(f"National renter threshold: ${threshold:,.0f}")
# National renter threshold: $39,430
```

### Different Tenure Types

Thresholds vary significantly by housing tenure:

```python
calc = SPMCalculator(year=2024)

for tenure in ["renter", "owner_with_mortgage", "owner_without_mortgage"]:
    threshold = calc.calculate_threshold(
        num_adults=2,
        num_children=2,
        tenure=tenure,
        geography_type="nation",
        geography_id="US"
    )
    print(f"{tenure}: ${threshold:,.0f}")

# renter: $39,430
# owner_with_mortgage: $39,068
# owner_without_mortgage: $32,586
```

### Geographic Variation

The same family has different thresholds in different locations:

```python
calc = SPMCalculator(year=2024)

locations = [
    ("nation", "US", "National"),
    ("state", "06", "California"),
    ("state", "54", "West Virginia"),
    ("congressional_district", "0611", "CA-11 (SF)"),
    ("congressional_district", "5401", "WV-01"),
]

for geo_type, geo_id, name in locations:
    threshold = calc.calculate_threshold(
        num_adults=2,
        num_children=2,
        tenure="renter",
        geography_type=geo_type,
        geography_id=geo_id
    )
    print(f"{name}: ${threshold:,.0f}")
```

### Batch Calculation

Calculate thresholds for multiple SPM units at once:

```python
import numpy as np
from spm_calculator import SPMCalculator

calc = SPMCalculator(year=2024)

# Multiple families in different locations
thresholds = calc.calculate_thresholds(
    num_adults=np.array([1, 2, 2, 3]),
    num_children=np.array([0, 0, 2, 4]),
    tenure=["renter", "renter", "owner_with_mortgage", "renter"],
    geography_type="state",
    geography_ids=["06", "54", "06", "15"]  # CA, WV, CA, HI
)

print(thresholds)
```

## Understanding the Components

### Base Thresholds

Get the underlying base thresholds (before geographic adjustment):

```python
calc = SPMCalculator(year=2024)
base = calc.get_base_thresholds()
print(base)
# {'renter': 39430, 'owner_with_mortgage': 39068, 'owner_without_mortgage': 32586}
```

### Geographic Adjustment (GEOADJ)

Get the GEOADJ factor for any geography:

```python
calc = SPMCalculator(year=2024)

# National is always 1.0
print(calc.get_geoadj("nation", "US"))  # 1.0

# High-cost area
print(calc.get_geoadj("state", "06"))  # ~1.15 (California)

# Low-cost area
print(calc.get_geoadj("state", "54"))  # ~0.85 (West Virginia)
```

### Equivalence Scale

Calculate the equivalence scale directly:

```python
from spm_calculator import spm_equivalence_scale

# Reference family (2A2C) = 1.0
print(spm_equivalence_scale(2, 2))  # 1.0

# Single adult
print(spm_equivalence_scale(1, 0))  # ~0.48

# Large family
print(spm_equivalence_scale(3, 4))  # ~1.52
```

## Next Steps

- See {doc}`methodology` for details on how thresholds are calculated
- See {doc}`api/calculator` for full API documentation
- See {doc}`validation` for validation against published values
