# Bundled data

## Congressional district GEOADJ (`cd_geoadj_2023.json`)

Pre-computed geographic adjustment factors (GEOADJ) for all 436 congressional districts (118th Congress).

### Source

- **Median 2-bedroom rent by congressional district**: American Community Survey (ACS) 5-Year Estimates, Table B25031 "Median Gross Rent by Bedrooms"
- **Year**: 2023 (2019-2023 ACS 5-year estimates)
- **Geography**: Congressional districts (118th Congress)

### Methodology

GEOADJ is calculated using the standard SPM formula:

```
GEOADJ = (local_median_rent / national_median_rent) × 0.492 + 0.508
```

Where:
- `local_median_rent` = Median 2-bedroom rent for the congressional district
- `national_median_rent` = National median 2-bedroom rent ($1,338 in 2023)
- `0.492` = Housing share of SPM threshold for renters
- `0.508` = Non-housing share (1 - 0.492)

Values are clamped to the range [0.70, 1.50] to match Census Bureau practice.

### References

- [Census Bureau SPM Methodology](https://www.census.gov/topics/income-poverty/supplemental-poverty-measure/library/publications.html)
- [ACS Table B25031](https://data.census.gov/table/ACSDT5Y2023.B25031)
- [BLS SPM Thresholds](https://www.bls.gov/pir/spm.htm)
