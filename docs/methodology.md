# Methodology

This document describes the methodology for calculating SPM thresholds, following Census Bureau and BLS guidelines.

## Overview

The Supplemental Poverty Measure (SPM) threshold represents the amount of resources a family needs to meet basic needs. Unlike the official poverty measure, the SPM:

1. Varies by geographic location (housing costs)
2. Accounts for housing tenure (renter vs. owner)
3. Uses a different family unit definition (SPM unit vs. family)
4. Includes more resources (tax credits, in-kind benefits)

## The Threshold Formula

```
threshold = base_threshold[tenure] × equivalence_scale × geoadj
```

## Component 1: Base Threshold

The base threshold comes from the Bureau of Labor Statistics Consumer Expenditure (CE) Survey.

### Data Source

- **Survey**: Consumer Expenditure Interview Survey (PUMD)
- **Time Period**: Rolling 5 years, lagged by 1 year
- **Sample**: Consumer units with children

### Expenditure Categories (FCSUti)

The threshold is based on spending on:

| Category | CE Variable(s) |
|----------|---------------|
| **F**ood | FOODPQ, FOODCQ |
| **C**lothing | APPARPQ, APPARCQ |
| **S**helter | SHELTPQ, SHELTCQ |
| **U**tilities | UTILPQ, UTILCQ |
| **t**elephone | TELEPHPQ, TELEPHCQ |
| **i**nternet | (included in utilities) |

### Calculation Method

1. Sum FCSUti expenditures for each consumer unit
2. Convert quarterly to annual (× 4)
3. Normalize to reference family (2A2C) using equivalence scale
4. Calculate 33rd percentile by tenure type

The 33rd percentile approximates 83% of the median, which is the target in the SPM methodology.

### 2024 Base Thresholds

| Tenure | Threshold |
|--------|-----------|
| Renter | $39,430 |
| Owner with mortgage | $39,068 |
| Owner without mortgage | $32,586 |

Source: [BLS SPM Thresholds 2024](https://www.bls.gov/pir/spm/spm_thresholds_2024.htm)

## Component 2: Equivalence Scale

The SPM uses a three-parameter equivalence scale to adjust thresholds for family size.

### Formula

For a family with $A$ adults and $C$ children:

$$
\text{raw\_scale} = 1.0 + 0.5 \times (A - 1) + 0.3 \times C
$$

$$
\text{equivalence\_scale} = \frac{\text{raw\_scale}}{2.1}
$$

Where 2.1 is the raw scale for the reference family (2 adults, 2 children).

### Example Values

| Family Type | Adults | Children | Equivalence Scale |
|-------------|--------|----------|-------------------|
| Single adult | 1 | 0 | 0.476 |
| Couple | 2 | 0 | 0.714 |
| Reference (2A2C) | 2 | 2 | 1.000 |
| Single parent, 2 kids | 1 | 2 | 0.762 |
| Large family | 3 | 4 | 1.524 |

## Component 3: Geographic Adjustment (GEOADJ)

The GEOADJ factor adjusts for differences in housing costs across geographic areas.

### Formula

$$
\text{GEOADJ} = \frac{\text{local\_median\_rent}}{\text{national\_median\_rent}} \times 0.492 + 0.508
$$

Where:
- 0.492 = housing portion of threshold for renters
- 0.508 = non-housing portion (not adjusted geographically)

### Data Source

- **Survey**: American Community Survey (ACS) 5-Year Estimates
- **Table**: B25031 (Median Gross Rent by Bedrooms)
- **Variable**: 2-bedroom units with complete kitchen and plumbing

### Range of Values

| Area | Approximate GEOADJ |
|------|-------------------|
| West Virginia (lowest) | ~0.84 |
| Mississippi | ~0.86 |
| National average | 1.00 |
| New York | ~1.12 |
| California | ~1.15 |
| Hawaii (highest) | ~1.27 |

This represents approximately 50% variation from lowest to highest cost areas.

## Supported Geographies

The ACS provides median rent data at multiple geographic levels:

| Level | Count | Example |
|-------|-------|---------|
| Nation | 1 | US |
| State | 51 | California |
| County | ~3,200 | San Francisco County |
| Congressional District | 435 | CA-11 |
| Metro Area | ~400 | SF-Oakland-Berkeley |
| PUMA | ~2,300 | (varies) |
| Census Tract | ~84,000 | (varies) |

## Forecasting

For years beyond published BLS thresholds, we:

1. Download latest available CE Survey data
2. Calculate base thresholds using the rolling 5-year methodology
3. Apply inflation adjustment if needed

This provides more accurate forecasts than simple CPI-U uprating.

## References

- [Census SPM Methodology](https://www.census.gov/topics/income-poverty/supplemental-poverty-measure.html)
- [BLS SPM Thresholds](https://www.bls.gov/pir/spm/spm_thresholds_2024.htm)
- [Census SPM Technical Documentation](https://www2.census.gov/programs-surveys/supplemental-poverty-measure/datasets/spm/spm_techdoc.pdf)
- [Geographic Adjustments Working Paper (2024)](https://www2.census.gov/library/working-papers/2024/demo/sehsd-wp2024-12.pdf)
