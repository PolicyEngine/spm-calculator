"""Scientific stage contracts, including an observed CE minor-only unit."""

import numpy as np
import pandas as pd
import pytest

from spm_calculator.ce_threshold import (
    calculate_base_thresholds,
    estimate_thresholds,
    normalize_ce_sample,
    replicate_thresholds,
)
from spm_calculator.fcsuti_cpi import CPI_SERIES, get_fcsuti_inflation_factor


def sample():
    """Identical reference families; analytically known threshold 0.984*3200."""
    return pd.DataFrame(
        {
            "NEWID": [1, 2, 3],
            "CUTENURE": [4, 1, 2],
            "PERSLT18": [2, 2, 2],
            "FAM_SIZE": [4, 4, 4],
            "ce_year": [2023] * 3,
            "FINLWT21": [1000.0] * 3,
            "FOODPQ": [100.0] * 3,
            "FOODCQ": [100.0] * 3,
            **{
                f"{name}{q}": [value] * 3
                for name, value in [
                    ("APPAR", 0.0),
                    ("SHELT", 300.0),
                    ("UTIL", 0.0),
                    ("TELEPH", 0.0),
                ]
                for q in ("PQ", "CQ")
            },
        }
    )


def flat_cpi():
    return {
        sid: pd.Series({2023: 100.0, 2024: 100.0})
        for sid in CPI_SERIES.values()
    }


def youth_row():
    """Observed demographics, CE 2020Q4; spending is synthetic in this test.

    NEWID 4429352 has AGE_REF=16, FAM_SIZE=PERSLT18=1, FINLWT21=39790.985.
    BLS's CU definition permits financially independent people under 18:
    https://www.bls.gov/cex/csxgloss.htm . An exact CE SPM A=0 treatment
    could not be established from https://www.bls.gov/pir/spmhome.htm .
    """
    row = sample().iloc[:1].copy()
    row["NEWID"] = 4429352
    row["AGE_REF"] = 16
    row["FAM_SIZE"] = 1
    row["PERSLT18"] = 1
    row["FINLWT21"] = 39790.985
    row["CUTENURE"] = 2
    return row


def test_minor_only_unit_is_unresolved_not_malformed():
    raw = pd.concat([sample(), youth_row()])
    with pytest.raises(ValueError, match="unresolved.*exclude_unresolved"):
        normalize_ce_sample(raw)
    normalized, diagnostics = normalize_ce_sample(
        raw, youth_policy="exclude_unresolved"
    )
    assert len(normalized) == 3
    assert diagnostics["unresolved_youth"]["rows"] == 1
    assert diagnostics["unresolved_youth"]["weight_sum"] == 39790.985
    assert diagnostics["exclusions"]["unresolved_youth"]["rows"] == 1
    assert diagnostics["unresolved_youth"]["records"][0]["NEWID"] == 4429352
    assert raw.iloc[-1]["FAM_SIZE"] == 1  # no caller mutation/adult invention


def test_legacy_youth_sensitivity_is_explicit_and_preserves_original_counts():
    normalized, diagnostics = normalize_ce_sample(
        pd.concat([sample(), youth_row()]), youth_policy="legacy_recode"
    )
    assert len(normalized) == 4
    assert normalized.iloc[-1]["FAM_SIZE"] == 1
    assert normalized.iloc[-1]["num_adults"] == 1
    assert normalized.iloc[-1]["num_children"] == 1
    assert diagnostics["youth_policy"] == "legacy_recode"
    assert diagnostics["approximations"]


@pytest.mark.parametrize(
    "field,value", [("FAM_SIZE", 0.5), ("PERSLT18", 5), ("PERSLT18", -1)]
)
def test_malformed_counts_still_fail_under_exclusion(field, value):
    raw = sample().astype({field: float})
    raw.loc[0, field] = value
    with pytest.raises(ValueError, match="family composition"):
        normalize_ce_sample(raw, youth_policy="exclude_unresolved")


def test_excluded_tenures_have_weight_and_count_diagnostics():
    raw = sample()
    raw.loc[0, "CUTENURE"] = 5
    normalized, diagnostic = normalize_ce_sample(raw)
    assert len(normalized) == 2
    assert diagnostic["exclusions"]["tenure_5"]["weight_sum"] == 1000
    assert diagnostic["raw"]["weight_sum"] == 3000
    assert diagnostic["included"]["weight_sum"] == 2000


def test_duplicate_indexes_do_not_duplicate_estimation_rows():
    frame = pd.DataFrame(
        {
            "fcsuti_2a2c": np.arange(100) * 10.0 + 1000,
            "su_2a2c": np.arange(100) * 3.0 + 200,
            "ce_weight": np.ones(100),
            "tenure_type": [
                "renter",
                "owner_with_mortgage",
                "owner_without_mortgage",
                "renter",
            ]
            * 25,
        }
    )
    expected, diagnostics = estimate_thresholds(frame)
    frame.index = np.zeros(100, dtype=int)
    actual, duplicated = estimate_thresholds(frame)
    assert actual == expected
    assert duplicated == diagnostics
    assert diagnostics["band_rows"] == 6
    assert diagnostics["fcsuti_mean"] == 1495.0


def test_pinned_cpi_is_offline_and_rebased(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Pinned replay must not request transport")

    monkeypatch.setattr("spm_calculator.fcsuti_cpi.fetch_bls_cpi_series", fail)
    series = {
        CPI_SERIES["food"]: pd.Series({2023: 100.0, 2024: 110.0}),
        CPI_SERIES["shelter"]: pd.Series({2023: 500.0, 2024: 600.0}),
    }
    factor = get_fcsuti_inflation_factor(
        2023, 2024, weights={"food": 0.5, "shelter": 0.5}, cpi_series=series
    )
    assert factor == pytest.approx(1.15)
    with pytest.raises(ValueError, match="missing"):
        get_fcsuti_inflation_factor(
            2023, 2024, weights={"apparel": 1.0}, cpi_series=series
        )


def test_stages_reconcile_and_entrypoint_preserves_return_shape():
    result = replicate_thresholds(sample(), 2024, cpi_series=flat_cpi())
    assert result["thresholds"]["renter"] == pytest.approx(0.984 * 3200)
    assert result["sample"]["included"]["rows"] == 3
    assert result["estimation"]["band_fallback"] is False
    assert (
        calculate_base_thresholds(
            ce=sample(), target_year=2024, cpi_series=flat_cpi()
        )
        == result["thresholds"]
    )


@pytest.mark.parametrize(
    "option,value",
    [
        ("youth_policy", "exclude_unresolved"),
        ("tenure_policy", "include_5_6_as_renter"),
        ("mortgage_principal", "exclude"),
        ("annualization", "pqcq2"),
        ("median_share", 0.83),
    ],
)
def test_replication_configurations_have_distinct_methodology_ids(
    option, value
):
    cpi = flat_cpi()
    for series in cpi.values():
        series.loc[2025] = 100.0
    base = replicate_thresholds(sample(), 2024, cpi_series=cpi)
    target = replicate_thresholds(
        sample(), 2025, cpi_series=cpi, **{option: value}
    )
    assert base["methodology_id"] != target["methodology_id"]
    assert (
        base["methodology_config"][option]
        != target["methodology_config"][option]
    )


def test_method_configuration_identity_is_independent_of_target_year():
    cpi = flat_cpi()
    for series in cpi.values():
        series.loc[2025] = 100.0
    base = replicate_thresholds(sample(), 2024, cpi_series=cpi)
    target = replicate_thresholds(sample(), 2025, cpi_series=cpi)
    assert base["methodology_id"] == target["methodology_id"]
