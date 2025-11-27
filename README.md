# spm-calculator

Calculate [Supplemental Poverty Measure (SPM)](https://www.census.gov/topics/income-poverty/supplemental-poverty-measure.html) thresholds for any US geography and year.

[![Try the Calculator](https://img.shields.io/badge/Try-Calculator-teal)](https://policyengine.github.io/spm-calculator)
[![Documentation](https://img.shields.io/badge/docs-online-green)](https://policyengine.github.io/spm-calculator)

## Interactive Calculator

**[Try the SPM Threshold Calculator](https://policyengine.github.io/spm-calculator)** - A static web app that walks you through calculating your SPM threshold based on your household characteristics.

The calculator runs entirely in your browser with no server required - all data is pre-computed and bundled.

### Run Locally

**Static React App (recommended):**
```bash
cd web
npm install
npm run dev
```

**Streamlit App (alternative):**
```bash
pip install spm-calculator[app]
streamlit run app/streamlit_app.py
```

## Overview

The SPM threshold is calculated as:

```
threshold = base_threshold[tenure] × equivalence_scale × geoadj
```

Where:
- **base_threshold** varies by housing tenure (renter, owner with mortgage, owner without mortgage), calculated from 5-year rolling Consumer Expenditure Survey data
- **equivalence_scale** adjusts for family composition using the SPM three-parameter scale
- **geoadj** adjusts for local housing costs based on ACS median rents

## Installation

```bash
pip install spm-calculator
```

## Quick Start

```python
from spm_calculator import SPMCalculator

# Initialize calculator for a specific year
calc = SPMCalculator(year=2024)

# Get base thresholds by tenure (national, before geographic adjustment)
base = calc.get_base_thresholds()
# {'renter': 39430, 'owner_with_mortgage': 39068, 'owner_without_mortgage': 32586}

# Get GEOADJ for a specific geography
geoadj = calc.get_geoadj("congressional_district", "0612")  # CA-12
# 1.24 (24% above national average due to high housing costs)

# Calculate threshold for a specific family in a specific location
threshold = calc.calculate_threshold(
    num_adults=2,
    num_children=2,
    tenure="renter",
    geography_type="congressional_district",
    geography_id="0612"
)
# ~$48,893 (base $39,430 × equiv_scale 1.0 × geoadj 1.24)
```

## Supported Geographies

- `nation` - National average
- `state` - 50 states + DC
- `county` - ~3,200 counties
- `metro_area` - Metropolitan statistical areas
- `congressional_district` - 435 congressional districts
- `puma` - Public Use Microdata Areas
- `tract` - Census tracts (limited availability)

## Data Sources

- **Base thresholds**: [BLS Consumer Expenditure Survey](https://www.bls.gov/cex/) - 5-year rolling FCSUti (Food, Clothing, Shelter, Utilities, telephone, internet)
- **Geographic adjustment**: [ACS 5-Year Estimates](https://www.census.gov/programs-surveys/acs) - Table B25031 (Median Gross Rent by Bedrooms)
- **Methodology**: [Census SPM Technical Documentation](https://www2.census.gov/programs-surveys/supplemental-poverty-measure/datasets/spm/spm_techdoc.pdf)

## Methodology

### Base Threshold Calculation

Following BLS methodology (updated September 2021):
1. Download 5 years of CE Survey PUMD (Public Use Microdata)
2. Filter to consumer units with children
3. Calculate FCSUti expenditures
4. Convert to reference family (2 adults, 2 children) using equivalence scale
5. Calculate 83% of median (47th-53rd percentile average) by tenure type

### Geographic Adjustment (GEOADJ)

Following Census methodology:
```
GEOADJ = (local_median_rent / national_median_rent) × 0.492 + 0.508
```

Where 0.492 is the housing portion of the SPM threshold for renters.

### Equivalence Scale

The SPM uses a three-parameter equivalence scale:
- First adult: 1.0
- Additional adults: 0.5 each
- Children: 0.3 each
- Normalized to reference family (2A2C = 1.0)

## Validation

Base thresholds are validated against [BLS published values](https://www.bls.gov/pir/spm/spm_thresholds_2024.htm):

| Tenure | 2024 BLS | Calculator |
|--------|----------|------------|
| Renter | $39,430 | $39,430 |
| Owner w/ mortgage | $39,068 | $39,068 |
| Owner w/o mortgage | $32,586 | $32,586 |

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
