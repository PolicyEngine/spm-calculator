# spm-calculator

Calculate [Supplemental Poverty Measure (SPM)](https://www.census.gov/topics/income-poverty/supplemental-poverty-measure.html) thresholds for any US geography and year.

[![Try the Calculator](https://img.shields.io/badge/Try-Calculator-teal)](https://spm-calculator.vercel.app/)
[![Documentation](https://img.shields.io/badge/docs-github-green)](https://github.com/PolicyEngine/spm-calculator/tree/main/docs)

## Interactive Calculator

**[Try the SPM Threshold Calculator](https://spm-calculator.vercel.app/)** - A browser-based calculator for metros, states, counties, and congressional districts, with a direct handoff to the Python package for tract-level and batch work.

The calculator runs entirely in your browser with no server required. National thresholds and official metro data are bundled; state, county, and district rent adjustments are fetched directly from the Census ACS API.

### Run Locally

**Next.js app (recommended):**
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
threshold = base_threshold[tenure] × equivalence_scale × geoadj[tenure]
```

Where:
- **base_threshold** varies by housing tenure (renter, owner with mortgage, owner without mortgage), calculated from 5-year rolling Consumer Expenditure Survey data
- **equivalence_scale** adjusts for family composition using the official Betson three-parameter SPM scale
- **geoadj** adjusts for local housing costs, using official Census metro thresholds where available and a tenure-specific ACS rent adjustment elsewhere

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

# Get GEOADJ for a specific location
geoadj = calc.get_geoadj("metro_area", "35620", tenure="renter")  # New York metro
# 1.1599

# Calculate threshold for a specific family in a specific location
threshold = calc.calculate_threshold(
    num_adults=2,
    num_children=2,
    tenure="renter",
    geography_type="metro_area",
    geography_id="35620"
)
# $45,736 (official 2024 Census metro threshold for NYC renters)
```

Official metro thresholds are bundled with the package. For custom ACS-based
geographies like states, counties, congressional districts, PUMAs, and tracts,
set `CENSUS_API_KEY` to fetch current median rents.

### SPM unit IDs

If your data does not already include Census SPM resource-unit IDs, use
`spm_unit_id` to create person-level IDs before calculating thresholds:

```python
from spm_calculator import spm_unit_id

ids, diagnostics = spm_unit_id(persons, diagnostics=True)
```

The function preserves native `person_spm_unit_id`, `spm_unit_id`, or `SPM_ID`
columns when present. Otherwise, it reconstructs units from the smallest
available person-level inputs:

| Input class | Columns recognized by default |
|-------------|-------------------------------|
| Required | `household_id`, `person_household_id`, `H_SEQ`, or `PH_SEQ` |
| Strongly recommended | `family_id`, `person_family_id`, or `PF_SEQ`; `age` or `A_AGE` |
| Person pointers | `line_number`, `person_line_number`, or `A_LINENO`; `parent_id`, `mother_id`, `father_id`, `PEPAR1`, `PEPAR2`; `spouse_id` or `A_SPOUSE`; `unmarried_partner_id`, `partner_id`, `cohabiting_partner_id`, or `PECOHAB` |
| Census SPM assignment flags | `SPM_WFOSTER22`, `SPM_WUI_LT15`, and `SPM_WNEWPARENT`; `SPM_WCOHABIT` is used only when no direct cohabiting partner pointer such as `PECOHAB` is available |
| Generic fallback flags | `relationship_to_head`, `family_relationship`, or `A_FAMREL`; `is_foster_child` or `foster_child` |

Diagnostics describe assignment provenance and missing recommended inputs; they
do not summarize the resulting unit distribution.

For parity checks against Census/native IDs or published thresholds:

```python
from spm_calculator import spm_threshold_match, spm_unit_id_match

id_report = spm_unit_id_match(persons)
threshold_report = spm_threshold_match(calculated, reference, atol=1.0)
```

The optional ASEC parity tests run against a real Census CPS ASEC HDFStore when
`SPM_CALCULATOR_ASEC_H5=/path/to/census_cps_2024.h5` is set.

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

For official public metro areas, the package uses the published Census metro table directly.

For custom geographies built from ACS rents, the adjustment is tenure-specific:
```
GEOADJ_t = (local_median_rent / national_median_rent) × housing_share_t + (1 - housing_share_t)
```

For 2024 thresholds, the tenure-specific housing shares are:
- `0.443` for renters
- `0.434` for owners with a mortgage
- `0.323` for owners without a mortgage

### Equivalence Scale

The SPM uses the official Betson three-parameter scale:
- Single adult with children: `(1 + 0.8 + 0.5 × (children - 1))^0.7`
- Multiple adults with children: `(adults + 0.5 × children)^0.7`
- One adult without children: `1.0`
- Two adults without children: `1.41`
- Three or more adults without children: `adults^0.7`
- Normalized to the reference family `(2 adults, 2 children) = 3^0.7`

## Validation

Base thresholds are validated against [BLS published values](https://www.bls.gov/pir/spm/spm_thresholds_2024.htm):

| Tenure | 2024 BLS | Calculator |
|--------|----------|------------|
| Renter | $39,430 | $39,430 |
| Owner w/ mortgage | $39,068 | $39,068 |
| Owner w/o mortgage | $32,586 | $32,586 |

Official metro thresholds are validated against [Census SPM Thresholds by Metro Area: 2024](https://www2.census.gov/programs-surveys/demo/tables/p60/287/SPM-pov-threshold-2024.xlsx).

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
