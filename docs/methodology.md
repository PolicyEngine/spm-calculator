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
threshold = base_threshold[tenure] × equivalence_scale × geoadj[tenure]
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
4. Calculate 83% of the median-range expenditure (47th-53rd percentile average) by tenure type

### 2024 Base Thresholds

| Tenure | Threshold |
|--------|-----------|
| Renter | $39,430 |
| Owner with mortgage | $39,068 |
| Owner without mortgage | $32,586 |

Source: [BLS SPM Thresholds 2024](https://www.bls.gov/pir/spm/spm_thresholds_2024.htm)

## Component 2: Equivalence Scale

The SPM uses the official Betson three-parameter equivalence scale to adjust thresholds for family size.

### Formula

For a single-adult unit with children:

$$
\text{raw\_scale} = (1 + 0.8 + 0.5 \times (C - 1))^{0.7}
$$

For multiple-adult units with children:

$$
\text{raw\_scale} = (A + 0.5 \times C)^{0.7}
$$

For childless units:
- one adult: $1.0$
- two adults: $1.41$
- three or more adults: $A^{0.7}$

The normalized scale divides by the reference-family raw scale:

$$
\text{equivalence\_scale} = \frac{\text{raw\_scale}}{3^{0.7}}
$$

### Example Values

| Family Type | Adults | Children | Equivalence Scale |
|-------------|--------|----------|-------------------|
| Single adult | 1 | 0 | 0.463 |
| Couple | 2 | 0 | 0.653 |
| Reference (2A2C) | 2 | 2 | 1.000 |
| Single parent, 2 kids | 1 | 2 | 0.830 |
| Large family | 3 | 4 | 1.430 |

## Component 3: Geographic Adjustment (GEOADJ)

The GEOADJ factor adjusts for differences in housing costs across geographic areas.
For public metro areas, the package uses the official Census metro thresholds directly.
For custom geographies derived from ACS rents, the adjustment is tenure-specific.

### Formula

$$
\text{GEOADJ}_t = \frac{\text{local\_median\_rent}}{\text{national\_median\_rent}} \times \text{housing\_share}_t + (1 - \text{housing\_share}_t)
$$

Where:
- renter housing share = 0.443
- owner with mortgage housing share = 0.434
- owner without mortgage housing share = 0.323

### Data Source

- **Survey**: American Community Survey (ACS) 5-Year Estimates
- **Table**: B25031 (Median Gross Rent by Bedrooms)
- **Variable**: 2-bedroom units with complete kitchen and plumbing

### Range of Values

| Area | Approximate GEOADJ |
|------|-------------------|
| Alabama Nonmetro (renter) | ~0.80 |
| National average | 1.00 |
| New York metro (renter) | ~1.16 |
| San Jose metro (renter) | ~1.52 |

Because the housing share differs by tenure, owner adjustments are flatter than renter adjustments.

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

1. Start from the latest published BLS tenure-specific thresholds
2. Apply projected CPI uprating by year
3. Keep the latest published metro adjustment factors when forecasting metro thresholds

## References

- [Census SPM Methodology](https://www.census.gov/topics/income-poverty/supplemental-poverty-measure.html)
- [BLS SPM Thresholds](https://www.bls.gov/pir/spm/spm_thresholds_2024.htm)
- [Census SPM Technical Documentation](https://www2.census.gov/programs-surveys/supplemental-poverty-measure/datasets/spm/spm_techdoc.pdf)
- [Geographic Adjustments Working Paper (2024)](https://www2.census.gov/library/working-papers/2024/demo/sehsd-wp2024-12.pdf)
