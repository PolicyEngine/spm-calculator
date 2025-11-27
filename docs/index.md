# SPM Calculator

Calculate [Supplemental Poverty Measure (SPM)](https://www.census.gov/topics/income-poverty/supplemental-poverty-measure.html) thresholds for any US geography and year.

## Overview

The SPM is an alternative poverty measure developed by the Census Bureau that accounts for:

- **Geographic housing costs** - Thresholds vary by ~50% from lowest (West Virginia, ~0.84) to highest (Hawaii, ~1.27) cost areas
- **Housing tenure** - Different thresholds for renters, owners with mortgages, and owners without mortgages
- **Family composition** - Thresholds scale with family size using a three-parameter equivalence scale

This package provides tools to calculate SPM thresholds at any geographic level supported by the American Community Survey.

## The SPM Threshold Formula

```
threshold = base_threshold[tenure] × equivalence_scale × geoadj
```

Where:
- **base_threshold** comes from the BLS Consumer Expenditure Survey (5-year rolling)
- **equivalence_scale** adjusts for family composition
- **geoadj** adjusts for local housing costs based on ACS median rents

## Installation

```bash
pip install spm-calculator
```

## Quick Example

```python
from spm_calculator import SPMCalculator

# Initialize for a specific year
calc = SPMCalculator(year=2024)

# Calculate threshold for a family in San Francisco
threshold = calc.calculate_threshold(
    num_adults=2,
    num_children=2,
    tenure="renter",
    geography_type="congressional_district",
    geography_id="0611"  # CA-11 (SF area)
)
print(f"SPM threshold: ${threshold:,.0f}")
# SPM threshold: ~$48,893
```

## Supported Geographies

| Geography Type | Description | Example ID |
|---------------|-------------|------------|
| `nation` | National average | `"US"` |
| `state` | 50 states + DC | `"06"` (California) |
| `county` | ~3,200 counties | `"06075"` (San Francisco) |
| `congressional_district` | 435 districts | `"0611"` (CA-11) |
| `metro_area` | Metropolitan areas | `"41860"` (SF-Oakland) |
| `puma` | Public Use Microdata Areas | `"0600101"` |
| `tract` | Census tracts | `"06075010100"` |

## Contents

```{tableofcontents}
```
