"""Release selection, immutable providers and PE's input contract."""

from copy import deepcopy

import pytest

from spm_calculator.policyengine_adapter import (
    PolicyEngineSPMProvider,
    validate_policyengine_inputs,
)
from spm_calculator.release import TENURES, SPMRelease, seal_release


@pytest.fixture
def synthetic_release():
    """Deliberately synthetic values; these are not published BLS estimates."""
    entry = {
        "status": "published",
        "methodology_id": "synthetic-test",
        "available_on": "2026-09-08",
        "source_ids": ["synthetic"],
        "thresholds": dict.fromkeys(TENURES, 40000.0),
        "housing_shares": dict.fromkeys(TENURES, 0.4),
        "housing_share_provenance": {
            "source_id": "synthetic",
            "reference_year": 2024,
            "status": "carried",
            "note": "Synthetic carried share fixture",
        },
        "uncertainty": {"kind": "unavailable"},
    }
    forecast = deepcopy(entry)
    forecast.update(status="forecast", methodology_id="synthetic-forecast")
    forecast["thresholds"] = dict.fromkeys(TENURES, 50000.0)
    forecast["housing_shares"] = dict.fromkeys(TENURES, 0.5)
    return SPMRelease.from_dict(
        seal_release(
            {
                "schema_version": 1,
                "release_id": "synthetic-pe-test",
                "created_on": "2026-09-08",
                "information_date": "2026-09-08",
                "units": "USD/year",
                "reference_family": {"adults": 2, "children": 2},
                "sources": [
                    {
                        "id": "synthetic",
                        "url": "https://example.org/synthetic",
                        "sha256": "0" * 64,
                        "available_on": "2026-09-08",
                    }
                ],
                "years": {"2025": entry, "2026": forecast},
                "geographies": {
                    "congressional_district": {
                        "id": "synthetic-cd",
                        "year": 2023,
                        "source_id": "synthetic",
                        "areas": {
                            "101": {
                                "name": "Synthetic district",
                                "rent_index": 1.5,
                            }
                        },
                    }
                },
            }
        )
    )


def synthetic_cpi(instant):
    return {"2025-02-01": 100.0, "2026-02-01": 110.0, "2027-02-01": 121.0}[
        instant
    ]


@pytest.mark.parametrize("year_policy", ["error", "pe_cpi_u"])
@pytest.mark.parametrize("allow_estimated", [False, True])
def test_published_entry_always_wins(
    synthetic_release, year_policy, allow_estimated
):
    provider = PolicyEngineSPMProvider(
        synthetic_release,
        year_policy=year_policy,
        allow_estimated=allow_estimated,
    )
    assert provider.year_metadata(2025)["thresholds"]["renter"] == 40000


@pytest.mark.parametrize("year_policy", ["error", "pe_cpi_u"])
def test_opted_in_forecast_wins(synthetic_release, year_policy):
    provider = PolicyEngineSPMProvider(
        synthetic_release, year_policy=year_policy, allow_estimated=True
    )
    assert provider.year_metadata(2026)["status"] == "forecast"
    assert provider.year_metadata(2026)["housing_shares"]["renter"] == 0.5


def test_estimate_declined_can_extrapolate_with_cpi_receipt(synthetic_release):
    provider = PolicyEngineSPMProvider(synthetic_release)
    with pytest.warns(UserWarning, match="consumer extrapolation"):
        entry = provider.year_metadata(2026, cpi_u=synthetic_cpi)
    assert entry["thresholds"]["renter"] == pytest.approx(44000)
    assert entry["status"] == "consumer_extrapolation"
    assert entry["unused_release_estimate"]["status"] == "forecast"
    assert entry["cpi"]["ratio"] == 1.1
    assert (
        entry["cpi"]["target"]["classification"]
        == "unknown_model_parameter_classification"
    )
    assert entry["housing_share_provenance"]["reference_year"] == 2024
    assert (
        entry["housing_share_provenance"]["carried_from_threshold_year"]
        == 2025
    )
    assert entry["housing_shares"]["renter"] == 0.4
    # Returned dictionaries cannot alter provider results.
    entry["thresholds"]["renter"] = 1
    assert provider.year_metadata(2026, cpi_u=synthetic_cpi)["thresholds"][
        "renter"
    ] == pytest.approx(44000)


def test_strict_policy_rejects_declined_estimate_and_missing_year(
    synthetic_release,
):
    provider = PolicyEngineSPMProvider(synthetic_release, year_policy="error")
    for year in (2024, 2026, 2027):
        with pytest.raises(ValueError):
            provider.year_metadata(year, cpi_u=synthetic_cpi)


def test_cpi_never_backcasts(synthetic_release):
    with pytest.raises(ValueError, match="past|before|interior"):
        PolicyEngineSPMProvider(synthetic_release).year_metadata(
            2024, cpi_u=synthetic_cpi
        )


def test_pinned_geography_and_explicit_fallback(synthetic_release):
    provider = PolicyEngineSPMProvider(
        synthetic_release, geography_kind="congressional_district"
    )
    assert provider.geography_metadata(2025, "renter", geoid="101")[
        "factor"
    ] == pytest.approx(1.2)
    with pytest.raises(ValueError, match="unavailable"):
        provider.geography_metadata(2025, "renter", geoid="9999")
    fallback = PolicyEngineSPMProvider(
        synthetic_release,
        geography_kind="congressional_district",
        missing_geography="national",
    )
    result = fallback.geography_metadata(2025, "renter", geoid="9999")
    assert result["factor"] == 1
    assert result["status"] == "explicit_national_fallback"


def test_input_contract_preserves_unit_members_and_rejects_baked_results():
    records = {
        "spm_unit": [
            {"spm_unit_id": "u1", "members": ["a", "b"]},
            {"spm_unit_id": "u2", "members": ["c"]},
        ],
        "person": [
            {"person_id": "a", "spm_unit_id": "u1", "age": 40},
            {"person_id": "c", "spm_unit_id": "u2", "age": 20},
        ],
    }
    original = deepcopy(records)
    validate_policyengine_inputs(records)
    assert records == original
    records["spm_unit"][1]["spm_unit_spm_threshold"] = 123
    with pytest.raises(ValueError, match="spm_unit_spm_threshold"):
        validate_policyengine_inputs(records)
    assert records["spm_unit"][1]["members"] == ["c"]


@pytest.mark.parametrize("status", ["nowcast", "forecast"])
@pytest.mark.parametrize("allow_estimated", [False, True])
@pytest.mark.parametrize("year_policy", ["error", "pe_cpi_u"])
def test_estimated_entry_precedence_cross_product(
    synthetic_release, status, allow_estimated, year_policy
):
    doc = synthetic_release.to_dict()
    doc["years"]["2026"]["status"] = status
    release = SPMRelease.from_dict(seal_release(doc))
    provider = PolicyEngineSPMProvider(
        release, allow_estimated=allow_estimated, year_policy=year_policy
    )
    if allow_estimated:
        assert provider.year_metadata(2026)["status"] == status
    elif year_policy == "error":
        with pytest.raises(ValueError, match="permitted"):
            provider.year_metadata(2026, cpi_u=synthetic_cpi)
    else:
        with pytest.warns(UserWarning):
            result = provider.year_metadata(2026, cpi_u=synthetic_cpi)
        assert result["unused_release_estimate"]["status"] == status
        assert result["thresholds"]["renter"] == pytest.approx(44000)


@pytest.mark.parametrize("allow_estimated", [False, True])
def test_absent_future_year_uses_published_base_and_warns_once(
    synthetic_release, allow_estimated, recwarn
):
    provider = PolicyEngineSPMProvider(
        synthetic_release, allow_estimated=allow_estimated
    )
    first = provider.year_metadata(2027, cpi_u=synthetic_cpi)
    second = provider.year_metadata(2027, cpi_u=synthetic_cpi)
    assert first == second
    assert first["base_year"] == 2025
    assert first["thresholds"]["renter"] == pytest.approx(48400)
    assert first["unused_release_estimate"] is None
    assert len(recwarn) == 1


def test_explicit_whole_factor_requires_vintage_and_nonnegative_housing(
    synthetic_release,
):
    with pytest.raises(ValueError, match="vintage"):
        PolicyEngineSPMProvider(
            synthetic_release,
            geography_kind="explicit",
            geographic_adjustment=1.2,
        )
    provider = PolicyEngineSPMProvider(
        synthetic_release,
        geography_kind="explicit",
        geographic_adjustment=0.5,
        geography_vintage="Synthetic supplied factor",
    )
    with pytest.raises(ValueError, match="negative housing"):
        provider.geography_metadata(2025, "renter")


def test_representative_entity_tables_preserve_native_membership():
    pd = pytest.importorskip("pandas")
    people = pd.DataFrame(
        {
            "person_id": [1, 2, 3, 4, 5, 6],
            "spm_unit_id": [10, 10, 10, 20, 30, 30],
            "household_id": [1, 1, 1, 1, 2, 2],
            "age": [40, 12, 8, 25, 40, 42],
        }
    )
    units = pd.DataFrame(
        {
            "spm_unit_id": [10, 20, 30],
            "spm_unit_tenure_type": [
                "RENTER",
                "RENTER",
                "OWNER_WITH_MORTGAGE",
            ],
            "spm_unit_net_income_reported": [40000, 12000, 60000],
        }
    )
    before = {
        "person": people.copy(deep=True),
        "spm_unit": units.copy(deep=True),
    }
    validate_policyengine_inputs({"person": people, "spm_unit": units})
    pd.testing.assert_frame_equal(people, before["person"])
    pd.testing.assert_frame_equal(units, before["spm_unit"])
    units["spm_unit_spm_threshold"] = [100, 200, 300]
    with pytest.raises(ValueError, match="computed outputs"):
        validate_policyengine_inputs({"person": people, "spm_unit": units})


def test_actual_country_engine_preserves_multiple_native_spm_units(
    synthetic_release,
):
    """Engineering integration fixture; no population weights or poverty-rate claim."""
    country = pytest.importorskip("policyengine_us")
    from spm_calculator.policyengine_adapter import build_policyengine_reform
    from spm_calculator.release import SPMUnit

    people = {
        "a": {"age": {2025: 40}},
        "b": {"age": {2025: 12}},
        "c": {"age": {2025: 8}},
        "d": {"age": {2025: 25}},
        "e": {"age": {2025: 40}},
        "f": {"age": {2025: 42}},
    }
    units = {
        "u1": {"members": ["a", "b", "c"]},
        "u2": {"members": ["d"]},
        "u3": {"members": ["e", "f"]},
    }
    validate_policyengine_inputs(
        {"person": people.values(), "spm_unit": units.values()}
    )
    simulation = country.Simulation(
        situation={"people": people, "spm_units": units},
        reform=build_policyengine_reform(
            PolicyEngineSPMProvider(synthetic_release)
        ),
    )
    assert list(simulation.calculate("spm_unit_count_adults", 2025)) == [
        1,
        1,
        2,
    ]
    assert list(simulation.calculate("spm_unit_count_children", 2025)) == [
        2,
        0,
        0,
    ]
    expected = [
        synthetic_release.calculate_unit(
            SPMUnit(
                unit_id=key,
                num_adults=a,
                num_children=c,
                tenure="renter",
                year=2025,
            )
        )["threshold"]
        for key, a, c in [("u1", 1, 2), ("u2", 1, 0), ("u3", 2, 0)]
    ]
    assert list(
        simulation.calculate("spm_unit_spm_threshold", 2025)
    ) == pytest.approx(expected, abs=0.01)
    assert list(
        simulation.calculate("spm_unit_spm_threshold", 2025, map_to="person")
    ) == pytest.approx(
        [expected[0]] * 3 + [expected[1]] + [expected[2]] * 2, abs=0.01
    )
