# Bundled data

## Congressional district rents (`cd_geoadj_2023.json`)

Bundled congressional district rent data for all 436 congressional districts (118th Congress).

### Source

- **Median 2-bedroom rent by congressional district**: American Community Survey (ACS) 5-Year Estimates, Table B25031 "Median Gross Rent by Bedrooms"
- **Year**: 2023 (2019-2023 ACS 5-year estimates)
- **Geography**: Congressional districts (118th Congress)

### Methodology

The package converts these rents into a tenure-specific SPM adjustment at runtime:

```
GEOADJ_t = (local_median_rent / national_median_rent) × housing_share_t + (1 - housing_share_t)
```

Where:
- `local_median_rent` = Median 2-bedroom rent for the congressional district
- `national_median_rent` = National median 2-bedroom rent ($1,338 in 2023)
- `housing_share_t` is tenure-specific (`0.443` renter, `0.434` owner with mortgage, `0.323` owner without mortgage)

Values are clamped to the range [0.70, 1.50] to match Census Bureau practice.

## Metro thresholds (`metro_geoadj_2024.json`)

Bundled official Census metro threshold data for 2024.

### Source

- **Census workbook**: `SPM-pov-threshold-2024.xlsx`
- **Table**: `Thresholds 2024`
- **Contents**:
  - raw median-rent index
  - tenure-specific reference-family threshold adjustments
  - tenure-specific 2-adult, 2-child thresholds

### References

- [Census Bureau SPM Methodology](https://www.census.gov/topics/income-poverty/supplemental-poverty-measure/library/publications.html)
- [ACS Table B25031](https://data.census.gov/table/ACSDT5Y2023.B25031)
- [BLS SPM Thresholds](https://www.bls.gov/pir/spm.htm)
