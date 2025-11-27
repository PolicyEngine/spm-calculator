# Validation

This document describes how the spm-calculator is validated against official sources.

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

### CE Survey Calculation

When calculating from CE Survey data (for forecasting beyond published years), we target:

- Within 2% of published values when using the same data years
- Consistent ranking across tenure types (owner w/o mortgage < owner w/ mortgage ≈ renter)

## GEOADJ Validation

### Expected Ranges

GEOADJ values should fall within the range observed in Census data:

| Statistic | Expected | Observed |
|-----------|----------|----------|
| Minimum | ~0.84 (WV) | [TO BE VALIDATED] |
| Maximum | ~1.27 (HI) | [TO BE VALIDATED] |
| National mean | 1.00 | 1.00 (by definition) |
| Std deviation | ~0.10 | [TO BE VALIDATED] |

### State-Level Validation

Cross-check against Census published GEOADJ values:

| State | Census GEOADJ | Calculator | Difference |
|-------|--------------|------------|------------|
| California | ~1.15 | [TO BE VALIDATED] | - |
| Hawaii | ~1.27 | [TO BE VALIDATED] | - |
| West Virginia | ~0.84 | [TO BE VALIDATED] | - |
| Texas | ~0.95 | [TO BE VALIDATED] | - |

## Equivalence Scale Validation

The three-parameter equivalence scale is deterministic:

```python
from spm_calculator import spm_equivalence_scale

# Reference family
assert spm_equivalence_scale(2, 2) == 1.0

# Known values
assert abs(spm_equivalence_scale(1, 0) - 1.0/2.1) < 0.001
assert abs(spm_equivalence_scale(2, 0) - 1.5/2.1) < 0.001
```

## Poverty Rate Validation

### National SPM Rate

When applied to CPS microdata, calculated thresholds should produce SPM poverty rates consistent with Census publications:

| Year | Census SPM Rate | Calculated | Difference |
|------|----------------|------------|------------|
| 2023 | 12.9% | [TO BE VALIDATED] | - |
| 2022 | 12.4% | [TO BE VALIDATED] | - |

### State-Level Rates

State-level poverty rates should be directionally consistent:

- High-cost states (CA, NY, HI) should have different relative poverty rates when using local thresholds vs. national thresholds
- Low-cost states (WV, MS, AR) should similarly differ

## Running Validation Tests

```bash
# Run all tests including validation
pytest tests/ -v

# Run only validation tests
pytest tests/test_validation.py -v

# Run with coverage
pytest tests/ --cov=spm_calculator --cov-report=html
```

## Automated CI Validation

Every PR runs validation tests against:

1. Published BLS threshold values
2. Expected GEOADJ ranges
3. Equivalence scale formulas

See `.github/workflows/ci.yaml` for CI configuration.

## Reporting Issues

If you find discrepancies between calculated and expected values:

1. Check the data year - ACS and CE data are released with lags
2. Verify the geography identifier format
3. Open an issue at [GitHub Issues](https://github.com/PolicyEngine/spm-calculator/issues)
