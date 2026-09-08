"""Generic anchored projections and information-date enforcement."""

import pytest

from spm_calculator.projection import ProjectionInput, project_thresholds


def observation(year, value, kind, available_on="2026-09-08", method=None):
    values = (
        value
        if kind == "price"
        else {
            "renter": value,
            "owner_with_mortgage": value,
            "owner_without_mortgage": value,
        }
    )
    return ProjectionInput(
        year=year,
        values=values,
        kind=kind,
        available_on=available_on,
        source_id=f"synthetic-{kind}-{year}",
        methodology_id=method or f"synthetic-{kind}",
    )


def test_anchored_ratio_preserves_official_level():
    result = project_thresholds(
        observation(2024, 30000, "published"),
        2025,
        as_of="2026-09-08",
        method="replication_ratio",
        replicated_base=observation(2024, 24000, "replication"),
        replicated_target=observation(2025, 26400, "replication"),
    )
    assert result["thresholds"]["renter"] == pytest.approx(33000)
    assert result["evaluation_mode"] == "retrospective"
    assert result["uncertainty"]["status"] == "unavailable"


@pytest.mark.parametrize(
    "method,expected", [("price_only", 31500), ("blend", 32250)]
)
def test_price_and_blend(method, expected):
    options = {}
    if method == "blend":
        options.update(
            replicated_base=observation(2024, 24000, "replication"),
            replicated_target=observation(2025, 26400, "replication"),
        )
    result = project_thresholds(
        observation(2024, 30000, "published"),
        2025,
        as_of="2026-09-08",
        method=method,
        price_base=observation(2024, 100, "price"),
        price_target=observation(2025, 105, "price"),
        **options,
    )
    assert result["thresholds"]["renter"] == pytest.approx(expected)


def test_as_of_rejects_later_input_even_when_target_is_historical():
    with pytest.raises(ValueError, match="available"):
        project_thresholds(
            observation(2024, 30000, "published"),
            2025,
            as_of="2025-08-01",
            method="price_only",
            price_base=observation(2024, 100, "price"),
            price_target=observation(2025, 105, "price"),
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("available_on", "2026-02-30"),
        ("source_id", ""),
        ("values", {"renter": 100}),
        ("year", 2024.5),
    ],
)
def test_input_contract_rejects_invalid_values(field, value):
    fields = dict(
        year=2024,
        values={
            "renter": 1,
            "owner_with_mortgage": 1,
            "owner_without_mortgage": 1,
        },
        kind="published",
        available_on="2026-09-08",
        source_id="test",
        methodology_id="synthetic",
    )
    fields[field] = value
    with pytest.raises((ValueError, TypeError)):
        ProjectionInput(**fields)


def test_ratio_refuses_different_replication_methods():
    with pytest.raises(ValueError, match="same methodology"):
        project_thresholds(
            observation(2024, 30000, "published"),
            2025,
            as_of="2026-09-08",
            method="replication_ratio",
            replicated_base=observation(
                2024, 24000, "replication", method="old"
            ),
            replicated_target=observation(
                2025, 26400, "replication", method="new"
            ),
        )


def test_projection_does_not_accept_unselected_inputs_or_bad_years():
    with pytest.raises(ValueError, match="unused"):
        project_thresholds(
            observation(2024, 30000, "published"),
            2025,
            as_of="2026-09-08",
            method="price_only",
            replicated_base=observation(2024, 24000, "replication"),
            price_base=observation(2024, 100, "price"),
            price_target=observation(2025, 105, "price"),
        )


def test_input_values_are_immutable_snapshot():
    values = {
        "renter": 10,
        "owner_with_mortgage": 10,
        "owner_without_mortgage": 10,
    }
    item = ProjectionInput(
        2024, values, "published", "2026-09-08", "test", "test"
    )
    values["renter"] = 999
    assert item.to_dict()["values"]["renter"] == 10
    with pytest.raises(TypeError):
        item.values["renter"] = 999
