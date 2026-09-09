# Methodology

This document distinguishes published threshold lookup, approximate CE replication and projection. The package's research estimator follows the published Census/BLS framework with explicitly documented approximations; it does not claim exact reproduction of unpublished BLS code or imputation choices.

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
| **i**nternet | (no FMLI summary variable; documented gap) |

### Calculation Method

1. Sum FCSUti expenditures for each consumer unit (shelter includes owner mortgage-principal outlays; UTIL already contains telephone)
2. Convert each quarterly recall window to annual (× 4)
3. Convert expenditures to target-year dollars using the sample-derived composite CPI weights and explicit annual CPI inputs (an approximation to BLS's quarterly treatment)
4. Normalize to reference family (2A2C) using equivalence scale
5. Apply the BLS formula over the estimation sample E (consumer units inside the 47th-53rd percentile range of equivalized FCSUti): `0.82 × (1.2 × FCSUti_E − SU_E + SU_Eh)`, where SU is shelter + utilities excluding telephone and h indexes housing tenure. The anchor was 83% before the July 17, 2026 correction (see [The 2026 BLS threshold correction](bls-2026-correction.md))

CE `FINLWT21` survey weights govern the expenditure distribution and within-band averages. Population calibration weights must not replace them. The current midpoint-CDF convention has not been verified against BLS's exact percentile implementation. Original CE consumer units and repeated interviews remain separate from the population SPM units used for poverty calculations.

For minor-only units (`FAM_SIZE == PERSLT18`), exact BLS adult/child treatment remains unresolved. The default calculation raises; research runs must explicitly select `youth_policy="exclude_unresolved"` or the nonofficial `legacy_recode` sensitivity. Excluding tenure 5/6 and assigning tenure 3 to owners with mortgage are also named research sample policies, not verified BLS instructions. The [current CE experiment](current-ce-replication.md) reports counts, weight mass, estimated levels and sensitivity. Other unresolved approximations include the post-redesign `GROCER` food allocation and omitted internet/in-kind expenditures.

### 2024 Base Thresholds

Corrected series published July 17, 2026:

| Tenure | Threshold |
|--------|-----------|
| Renter | $39,219.89 |
| Owner with mortgage | $39,231.00 |
| Owner without mortgage | $32,878.59 |

Source: [Corrected SPM Thresholds](https://www.bls.gov/pir/spm/spm_thresholds_2024_correction.htm) (workbook bundled in the package with recorded SHA-256; see [The 2026 BLS threshold correction](bls-2026-correction.md))

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

These counts are already-classified SPM adults and children. Age alone does not resolve every teenage membership/dependency case. Household consumers validate supported compositions; the CE estimator owns its separate unresolved-unit sample policy.

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

These are the fixed 2024-derived legacy accessor values. Explicit releases identify the share reference year and any carried-value approximation; they must not label carried 2024 shares as official target-year shares. New provider calculations use the selected release's shares. The release's geographic identifier and year also determine its rent or metro inputs; unknown requested areas raise unless a caller explicitly selects a documented fallback.

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

The ACS publishes median rent data at multiple geographic levels. This table describes source coverage; actual offline support is limited to areas present in the selected release, and is not a promise that every listed area has an available estimate:

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

Published lookup consumes a pinned release. Missing years raise by default;
an explicitly supplied estimated entry requires opt-in. The archived 2025
nowcast remains available for evaluation, separately from the published
2025 threshold.

The generic projection helper anchors to an official base:

```
projected threshold = official base × replicated target / replicated base
```

It also supports price-only ratios and explicit blends. Each input carries
its year, methodology, source identity and availability date. Inputs later
than `as_of` are rejected. The helper does not itself predict unobserved
expenditures or prices. Current-method historical results are retrospective;
they do not replace frozen forecasts or demonstrate real-time accuracy.
See [current CE replication](current-ce-replication.md).

Legacy calculator and PE paths retain their documented CPI extrapolation
behavior. The new PE compatibility adapter labels any such result as
consumer extrapolation with its base release and evaluated model CPI
ratio; it is not a published release entry. Projecting poverty rates also
requires projected population characteristics and resources, which this
threshold estimator does not supply. No new consumption-based 2026 forecast is
made in this CE research experiment. The browser separately offers 2026–2030
price-only projections using explicit inflation assumptions; see
[SPM releases](spm-releases.md#browser-geography-scope).

## References

- [Census SPM Methodology](https://www.census.gov/topics/income-poverty/supplemental-poverty-measure.html)
- [BLS SPM Thresholds](https://www.bls.gov/pir/spm/spm_thresholds_2024.htm)
- [Census SPM Technical Documentation](https://www2.census.gov/programs-surveys/supplemental-poverty-measure/datasets/spm/spm_techdoc.pdf)
- [Geographic Adjustments Working Paper (2024)](https://www2.census.gov/library/working-papers/2024/demo/sehsd-wp2024-12.pdf)
