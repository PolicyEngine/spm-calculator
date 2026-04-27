"""Tests for SPM validation helpers."""

import pandas as pd

from spm_calculator import spm_threshold_match, spm_unit_id_match


def test_spm_unit_id_match_ignores_arbitrary_id_labels():
    persons = pd.DataFrame(
        {
            "household_id": [10, 10, 10, 20],
            "SPM_ID": [100, 100, 101, 200],
            "predicted": [5, 5, 6, 7],
        }
    )

    report = spm_unit_id_match(
        persons,
        predicted_spm_unit_id="predicted",
    )

    assert report["match"] is True
    assert report["households"] == 2
    assert report["matching_households"] == 2
    assert report["household_match_rate"] == 1.0
    assert report["person_weighted_household_match_rate"] == 1.0


def test_spm_unit_id_match_can_infer_against_native_reference():
    persons = pd.DataFrame(
        {
            "person_id": [1, 2, 3, 4],
            "household_id": [10, 10, 10, 10],
            "age": [40, 38, 12, 16],
            "relationship_to_head": [0, 1, 3, 3],
            "SPM_ID": [100, 100, 100, 101],
        }
    )

    report = spm_unit_id_match(persons)

    assert report["match"] is True
    assert report["predicted_source"] == "inferred"


def test_spm_unit_id_match_reports_mismatching_households():
    persons = pd.DataFrame(
        {
            "household_id": [10, 10, 20, 20],
            "SPM_ID": [100, 100, 200, 201],
            "predicted": [5, 6, 7, 8],
        }
    )

    report = spm_unit_id_match(
        persons,
        predicted_spm_unit_id="predicted",
    )

    assert report["match"] is False
    assert report["matching_households"] == 1
    assert report["mismatching_households"] == 1
    assert report["mismatching_household_ids"] == [10]


def test_spm_threshold_match_accepts_small_errors_with_tolerance():
    report = spm_threshold_match(
        calculated=pd.Series([10_000.50, 20_001.00]),
        reference=pd.Series([10_000.00, 20_000.00]),
        atol=1.0,
        rtol=0.0,
    )

    assert report["match"] is True
    assert report["matching_values"] == 2
    assert report["max_abs_error"] == 1.0


def test_spm_threshold_match_reports_large_errors():
    report = spm_threshold_match(
        calculated=pd.Series([10_000.00, 20_005.00], index=["a", "b"]),
        reference=pd.Series([10_000.00, 20_000.00]),
        atol=1.0,
        rtol=0.0,
    )

    assert report["match"] is False
    assert report["matching_values"] == 1
    assert report["mismatching_values"] == 1
    assert report["mismatching_indices"] == ["b"]
