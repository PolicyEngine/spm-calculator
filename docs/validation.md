# Validation

This document describes how `spm-calculator` is validated against official
threshold sources and the package's own deterministic formulas.

## Base Threshold Validation

### Published BLS Values

We validate base thresholds against BLS published values:

| Year | Tenure | BLS Published | Calculator | Difference |
|------|--------|--------------|------------|------------|
| 2024 | Renter | $39,430 | $39,430 | 0% |
| 2024 | Owner w/ mortgage | $39,068 | $39,068 | 0% |
| 2024 | Owner w/o mortgage | $32,586 | $32,586 | 0% |
| 2023 | Renter | $36,606 | $36,606 | 0% |
| 2023 | Owner w/ mortgage | $36,192 | $36,192 | 0% |
| 2023 | Owner w/o mortgage | $30,347 | $30,347 | 0% |

Source: [BLS SPM Thresholds](https://www.bls.gov/pir/spm/spm_thresholds_2024.htm)

### CE Survey Reconstruction

When reconstructing thresholds from CE Survey data, we target:

- Within 2% of published values when using the same data years
- Consistent ranking across tenure types: owner without mortgage < owner with mortgage approximately renter
- Correct use of the FCSUti CPI adjustment into threshold-year dollars

## GEOADJ Validation

### Official Metro Thresholds

For metro areas and nonmetro areas, we validate against the published Census
2024 workbook of 2-adult, 2-child thresholds.

| Geography | Tenure | Census published | Calculator | Difference |
|-----------|--------|------------------|------------|------------|
| Alabama Nonmetro | Renter | $31,622 | $31,622 | 0% |
| New York metro | Renter | $45,736 | $45,736 | 0% |
| San Jose metro | Renter | $59,815 | $59,815 | 0% |

The bundled metro data also preserves the raw Census rent index separately from
the tenure-specific threshold adjustment.

### ACS-Derived Geographies

For states, counties, congressional districts, PUMAs, and tracts, we validate
the transformation itself:

```python
GEOADJ_t = (local_rent / national_rent) * housing_share_t + (1 - housing_share_t)
```

where `housing_share_t` is tenure-specific.

## Equivalence Scale Validation

The Betson three-parameter equivalence scale is deterministic:

```python
from spm_calculator import spm_equivalence_scale

# Reference family
assert spm_equivalence_scale(2, 2) == 1.0

# Known values
assert abs(spm_equivalence_scale(1, 0) - 0.4634630568) < 1e-9
assert abs(spm_equivalence_scale(2, 0) - 0.6534829100) < 1e-9
```

## Running Validation Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=spm_calculator --cov-report=html
```

## Automated CI Validation

Every PR runs validation tests against:

1. Published BLS threshold values
2. Official Census metro thresholds
3. Tenure-specific GEOADJ formulas
4. Equivalence scale formulas

## Reporting Issues

If you find discrepancies between calculated and expected values:

1. Check the data year. ACS and CE data are released with lags.
2. Verify the geography identifier format.
3. Open an issue at [GitHub Issues](https://github.com/PolicyEngine/spm-calculator/issues).
