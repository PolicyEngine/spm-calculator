"""Tests for SPM resource-unit membership helpers."""

import pandas as pd

from spm_calculator import spm_unit_id


def test_spm_unit_id_preserves_native_person_spm_unit_id():
    persons = pd.DataFrame(
        {
            "person_id": [1, 2, 3],
            "household_id": [10, 10, 20],
            "person_spm_unit_id": [100, 100, 200],
        },
        index=["a", "b", "c"],
    )

    ids, diagnostics = spm_unit_id(persons, diagnostics=True)

    assert ids.tolist() == [100, 100, 200]
    assert ids.index.tolist() == ["a", "b", "c"]
    assert ids.name == "spm_unit_id"
    assert diagnostics == {
        "method": "native_spm_id",
        "native_id_column": "person_spm_unit_id",
        "used_columns": ["person_spm_unit_id"],
        "missing_recommended_columns": [],
        "fallback_rules_used": [],
        "confidence": "native",
    }


def test_spm_unit_id_preserves_native_spm_unit_id():
    persons = pd.DataFrame(
        {
            "person_id": [1, 2, 3],
            "household_id": [10, 10, 20],
            "spm_unit_id": [100, 101, 200],
        }
    )

    ids = spm_unit_id(persons)

    assert ids.tolist() == [100, 101, 200]


def test_spm_unit_id_uses_family_and_unmarried_partner_links():
    persons = pd.DataFrame(
        {
            "person_id": [1, 2, 3, 4],
            "household_id": [10, 10, 10, 20],
            "family_id": [100, 200, 200, 300],
            "unmarried_partner_id": [2, 1, None, None],
            "age": [35, 34, 8, 70],
        }
    )

    ids, diagnostics = spm_unit_id(persons, diagnostics=True)

    assert ids.iloc[0] == ids.iloc[1]
    assert ids.iloc[1] == ids.iloc[2]
    assert ids.iloc[3] != ids.iloc[0]
    assert diagnostics["method"] == "census_relationship_rules"
    assert diagnostics["confidence"] == "rule_based"
    assert "link_unmarried_partners" in diagnostics["fallback_rules_used"]


def test_spm_unit_id_uses_asec_line_number_parent_pointers():
    persons = pd.DataFrame(
        {
            "PH_SEQ": [1, 1, 1],
            "P_SEQ": [1, 2, 3],
            "A_LINENO": [10, 20, 30],
            "PEPAR1": [-1, 10, -1],
            "PEPAR2": [-1, -1, -1],
            "A_AGE": [45, 12, 40],
        }
    )

    ids, diagnostics = spm_unit_id(persons, diagnostics=True)

    assert ids.iloc[0] == ids.iloc[1]
    assert ids.iloc[2] != ids.iloc[0]
    assert "link_parent_child" in diagnostics["fallback_rules_used"]
    assert {"A_LINENO", "PEPAR1", "PEPAR2"}.issubset(
        diagnostics["used_columns"]
    )


def test_spm_unit_id_uses_asec_spm_assignment_flags():
    persons = pd.DataFrame(
        {
            "PH_SEQ": [1, 1, 2, 2, 3, 3],
            "PF_SEQ": [1, 2, 1, 2, 1, 2],
            "A_AGE": [30, 31, 45, 7, 28, 29],
            "SPM_WCOHABIT": [1, 1, 0, 0, 0, 0],
            "SPM_WFOSTER22": [0, 0, 1, 1, 0, 0],
            "SPM_WUI_LT15": [0, 0, 1, 1, 0, 0],
            "SPM_WNEWPARENT": [0, 0, 0, 0, 1, 1],
        }
    )

    ids, diagnostics = spm_unit_id(persons, diagnostics=True)

    assert ids.iloc[0] == ids.iloc[1]
    assert ids.iloc[2] == ids.iloc[3]
    assert ids.iloc[4] == ids.iloc[5]
    assert (
        "merge_census_cohabiting_unit_flags"
        in diagnostics["fallback_rules_used"]
    )
    assert (
        "merge_census_foster_under_22_flags"
        in diagnostics["fallback_rules_used"]
    )
    assert (
        "merge_census_unrelated_under_15_flags"
        in diagnostics["fallback_rules_used"]
    )
    assert (
        "merge_census_new_parent_flags" in diagnostics["fallback_rules_used"]
    )


def test_spm_unit_id_prefers_partner_links_over_cohabiting_unit_flag():
    persons = pd.DataFrame(
        {
            "PH_SEQ": [1, 1, 1, 1],
            "A_LINENO": [1, 2, 3, 4],
            "PF_SEQ": [1, 2, 3, 4],
            "PECOHAB": [2, 1, 4, 3],
            "SPM_WCOHABIT": [1, 1, 1, 1],
        }
    )

    ids, diagnostics = spm_unit_id(persons, diagnostics=True)

    assert ids.iloc[0] == ids.iloc[1]
    assert ids.iloc[2] == ids.iloc[3]
    assert ids.iloc[0] != ids.iloc[2]
    assert "link_unmarried_partners" in diagnostics["fallback_rules_used"]
    assert (
        "merge_census_cohabiting_unit_flags"
        not in diagnostics["fallback_rules_used"]
    )


def test_spm_unit_id_handles_asec_family_relationship_codes():
    persons = pd.DataFrame(
        {
            "PH_SEQ": [1, 1, 1, 1, 1],
            "A_FAMREL": [1, 2, 3, 0, 4],
        }
    )

    ids = spm_unit_id(persons)

    assert ids.iloc[0] == ids.iloc[1]
    assert ids.iloc[1] == ids.iloc[2]
    assert ids.iloc[3] != ids.iloc[0]
    assert ids.iloc[4] != ids.iloc[0]


def test_spm_unit_id_prefers_unrelated_child_flags_over_generic_relationship():
    persons = pd.DataFrame(
        {
            "PH_SEQ": [1, 1, 1, 1],
            "PF_SEQ": [1, 2, 2, 3],
            "A_AGE": [62, 40, 5, 0],
            "A_FAMREL": [0, 1, 3, 0],
            "SPM_WUI_LT15": [1, 0, 0, 1],
        }
    )

    ids = spm_unit_id(persons)

    assert ids.iloc[0] == ids.iloc[3]
    assert ids.iloc[1] == ids.iloc[2]
    assert ids.iloc[0] != ids.iloc[1]


def test_spm_unit_id_attaches_unrelated_children_under_15():
    persons = pd.DataFrame(
        {
            "person_id": [1, 2, 3, 4, 5],
            "household_id": [10, 10, 10, 10, 10],
            "age": [40, 39, 10, 14, 15],
            "relationship_to_head": [0, 1, 2, 3, 3],
        }
    )

    ids, diagnostics = spm_unit_id(persons, diagnostics=True)

    assert ids.iloc[0] == ids.iloc[1]
    assert ids.iloc[1] == ids.iloc[2]
    assert ids.iloc[2] == ids.iloc[3]
    assert ids.iloc[4] != ids.iloc[0]
    assert diagnostics["method"] == "census_relationship_rules"
    assert diagnostics["fallback_rules_used"] == [
        "attach_unrelated_under_15_to_reference_unit"
    ]


def test_spm_unit_id_attaches_foster_children_under_22():
    persons = pd.DataFrame(
        {
            "person_id": [1, 2, 3],
            "household_id": [10, 10, 10],
            "age": [45, 16, 22],
            "relationship_to_head": [0, 3, 3],
            "is_foster_child": [False, True, True],
        }
    )

    ids, diagnostics = spm_unit_id(persons, diagnostics=True)

    assert ids.iloc[0] == ids.iloc[1]
    assert ids.iloc[2] != ids.iloc[0]
    assert diagnostics["fallback_rules_used"] == [
        "attach_foster_under_22_to_reference_unit"
    ]


def test_spm_unit_id_diagnostics_describe_assignment_not_profile():
    persons = pd.DataFrame(
        {
            "person_id": [1, 2],
            "household_id": [10, 10],
            "age": [30, 20],
        }
    )

    _, diagnostics = spm_unit_id(persons, diagnostics=True)

    assert diagnostics["method"] == "fallback_household_rules"
    assert diagnostics["fallback_rules_used"] == ["household_level_fallback"]
    assert "num_spm_units" not in diagnostics
    assert "child_only_units" not in diagnostics
    assert "avg_unit_size" not in diagnostics
