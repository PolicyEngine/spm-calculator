# Quickstart

## Installation

```bash
pip install spm-calculator
```

You'll need a Census API key for custom ACS-based geographies like states,
counties, congressional districts, PUMAs, and tracts. Official Census metro
thresholds are bundled and work without any API key.

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
    ("metro_area", "1002", "Alabama Nonmetro"),
    ("metro_area", "35620", "New York metro"),
    ("metro_area", "41940", "San Jose metro"),
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

Get the tenure-specific GEOADJ factor for any geography:

```python
calc = SPMCalculator(year=2024)

# National is always 1.0
print(calc.get_geoadj("nation", "US", tenure="renter"))  # 1.0

# Official metro adjustment from bundled Census data
print(calc.get_geoadj("metro_area", "35620", tenure="renter"))  # ~1.160 (New York)

# Low-cost official metro area
print(calc.get_geoadj("metro_area", "1002", tenure="renter"))  # ~0.802 (Alabama Nonmetro)
```

For ACS-derived custom geographies:

```python
import os
from spm_calculator import SPMCalculator

os.environ["CENSUS_API_KEY"] = "your_key_here"

calc = SPMCalculator(year=2024)
print(calc.get_geoadj("state", "06", tenure="renter"))  # California
```

### Equivalence Scale

Calculate the equivalence scale directly:

```python
from spm_calculator import spm_equivalence_scale

# Reference family (2A2C) = 1.0
print(spm_equivalence_scale(2, 2))  # 1.0

# Single adult
print(spm_equivalence_scale(1, 0))  # ~0.463

# Large family
print(spm_equivalence_scale(3, 4))  # ~1.430
```

## Next Steps

- See [methodology](methodology.md) for details on how thresholds are calculated
- See [API documentation](api/calculator.md) for full API documentation
- See [validation](validation.md) for validation against published values
