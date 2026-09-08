"""Real Microcosm Frame tests; no country engine or population download."""

import pytest

mc = pytest.importorskip("microcosm.frame")
pd = pytest.importorskip("pandas")

from spm_calculator.microcosm_adapter import (
    apply_release_to_frame,
    summarize_spm_units,
)
from spm_calculator.release import load_release


@pytest.fixture
def frame():
    # Synthetic membership: one poor single-adult unit and one nonpoor
    # three-person unit. Unequal sizes distinguish units from persons.
    return mc.Frame(
        {
            "person": pd.DataFrame(
                {
                    "person_id": [1, 2, 3, 4],
                    "person_household_id": [1, 2, 2, 2],
                    "person_spm_unit_id": [10, 20, 20, 20],
                }
            ),
            "household": pd.DataFrame({"household_id": [1, 2]}),
            "spm_unit": pd.DataFrame(
                {
                    "spm_unit_id": [10, 20],
                    "spm_num_adults": [1, 2],
                    "spm_num_children": [0, 1],
                    "spm_tenure": ["renter", "owner_with_mortgage"],
                    "resources": [0.0, 1_000_000.0],
                }
            ),
        },
        mc.EntitySchema(group_entities=("household", "spm_unit")),
        {"household": mc.Weights([100, 200], mc.WeightKind.DESIGN)},
        metadata={"source": "synthetic software fixture"},
    )


def apply(frame, **kwargs):
    return apply_release_to_frame(
        frame,
        load_release(),
        year=2025,
        unit_entity="spm_unit",
        weight_entity="household",
        membership_provenance="Synthetic native membership; all persons represented",
        columns={
            "num_adults": "spm_num_adults",
            "num_children": "spm_num_children",
            "tenure": "spm_tenure",
            "resources": "resources",
        },
        **kwargs,
    )


def test_real_frame_preserves_membership_weights_and_source(frame):
    applied = apply(frame)
    pd.testing.assert_frame_equal(applied.person, frame.person)
    assert "spm_release_threshold" not in frame.table("spm_unit")
    assert applied.weights_for("household") is frame.weights_for("household")
    assert applied.metadata["source"] == frame.metadata["source"]
    assert (
        applied.metadata["spm_release_application"]["weights"]["source_entity"]
        == "household"
    )
    summary = summarize_spm_units(
        applied, unit_entity="spm_unit", weight_entity="household"
    )
    assert summary["poor_units"] == 100
    assert summary["unit_poverty_rate"] == pytest.approx(1 / 3)
    # A person-level rate would be 1/7; the API makes its unit denominator explicit.
    assert summary["unit_poverty_rate"] != pytest.approx(1 / 7)


def test_reweighting_changes_population_accounting_not_thresholds(frame):
    reweighted = frame.with_weights(
        "household",
        mc.Weights([200, 100], mc.WeightKind.CALIBRATED),
        mass="conserve",
    )
    first, second = apply(frame), apply(reweighted)
    pd.testing.assert_series_equal(
        first.table("spm_unit")["spm_release_threshold"],
        second.table("spm_unit")["spm_release_threshold"],
    )
    summary = summarize_spm_units(
        second, unit_entity="spm_unit", weight_entity="household"
    )
    assert summary["unit_poverty_rate"] == pytest.approx(2 / 3)
    assert summary["weights"]["kind"] == "calibrated"


def test_wrong_weight_entity_is_not_silently_substituted(frame):
    applied = apply(frame)
    with pytest.raises(ValueError, match="not requested"):
        summarize_spm_units(
            applied, unit_entity="spm_unit", weight_entity="spm_unit"
        )


def test_counts_must_match_existing_membership(frame):
    frame.table("spm_unit").loc[0, "spm_num_children"] = 1
    with pytest.raises(ValueError, match="do not match linked membership"):
        apply(frame)


def test_postconstruction_link_corruption_fails_before_application(frame):
    frame.person.loc[0, "person_spm_unit_id"] = 999
    with pytest.raises(ValueError):
        apply(frame)


def test_missing_resources_do_not_become_nonpoor(frame):
    result = apply_release_to_frame(
        frame,
        load_release(),
        year=2025,
        unit_entity="spm_unit",
        weight_entity="household",
        membership_provenance="Synthetic fixture membership",
    )
    summary = summarize_spm_units(
        result, unit_entity="spm_unit", weight_entity="household"
    )
    assert summary["unit_poverty_rate"] is None
    assert summary["poor_units"] is None
