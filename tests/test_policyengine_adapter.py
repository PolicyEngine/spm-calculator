"""Canonical forecast selection, native SPM membership and real model parity."""

from copy import deepcopy
from math import isfinite

import pytest

from spm_calculator.errors import SPMInputError
from spm_calculator.policyengine_adapter import (
    PolicyEngineSPMProvider,
    build_policyengine_reform,
    validate_policyengine_inputs,
)
from spm_calculator.rolling_forecast import SPMForecast, seal_forecast
from tests.test_rolling_forecast import example_document


@pytest.fixture
def synthetic_forecast():
    doc = example_document()
    for scenario in doc["scenarios"].values():
        for entry in scenario["years"].values():
            entry["thresholds"] = {
                key: value * 500 for key, value in entry["thresholds"].items()
            }
    return SPMForecast.from_dict(seal_forecast(doc))


def test_selected_year_and_scenario_have_no_consumer_uprating(
    synthetic_forecast,
):
    provider = PolicyEngineSPMProvider(synthetic_forecast)
    other = PolicyEngineSPMProvider(synthetic_forecast, scenario="zero_real")
    for year in synthetic_forecast.years:
        result = provider.calculate_unit(
            year=year,
            adults=2,
            children=2,
            tenure="renter",
            county_fips="01001",
        )
        assert (
            result["reference_threshold"]
            == synthetic_forecast.entry(year)["thresholds"]["renter"]
        )
        assert result["provenance"]["county_assignment"]["area_id"] == "A"
    assert (
        provider.year_metadata(2026)["thresholds"]
        != other.year_metadata(2026)["thresholds"]
    )
    with pytest.raises(ValueError, match="no entry"):
        provider.year_metadata(2036)
    assert "consumer_extrapolation" not in str(provider.provenance())
    assert "national_fallback" not in str(provider.provenance())


def test_location_requires_available_county_or_explicit_selection(
    synthetic_forecast,
):
    provider = PolicyEngineSPMProvider(synthetic_forecast)
    kwargs = dict(year=2025, adults=2, children=2, tenure="renter")
    for county in (None, "99999", "1001", 1001):
        with pytest.raises(ValueError):
            provider.calculate_unit(**kwargs, county_fips=county)
    for kind in ("congressional_district", "explicit", "state"):
        with pytest.raises(ValueError, match="geography_kind"):
            PolicyEngineSPMProvider(synthetic_forecast, geography_kind=kind)
    national = PolicyEngineSPMProvider(
        synthetic_forecast, geography_kind="national"
    )
    assert (
        national.calculate_unit(**kwargs)["geography_status"]
        == "explicit_national"
    )
    with pytest.raises(ValueError, match="conflicts"):
        national.calculate_unit(**kwargs, county_fips="01001")
    area = PolicyEngineSPMProvider(
        synthetic_forecast, geography_kind="metro", geography_id="A"
    )
    assert (
        area.calculate_unit(**kwargs)["threshold"]
        == provider.calculate_unit(**kwargs, county_fips="01001")["threshold"]
    )


@pytest.mark.parametrize(
    "keyword,value",
    [
        ("year_policy", "pe_cpi_u"),
        ("allow_estimated", True),
        ("missing_geography", "national"),
    ],
)
def test_removed_fallback_options_rejected(synthetic_forecast, keyword, value):
    with pytest.raises(TypeError):
        PolicyEngineSPMProvider(synthetic_forecast, **{keyword: value})


def test_unknown_explicit_area_uses_structured_geography_error(
    synthetic_forecast,
):
    from spm_calculator.errors import SPMInputError

    provider = PolicyEngineSPMProvider(
        synthetic_forecast, geography_kind="metro", geography_id="unknown"
    )
    with pytest.raises(SPMInputError) as raised:
        provider.calculate_unit(
            year=2025, adults=2, children=2, tenure="renter"
        )
    assert raised.value.code == "SPM_GEOGRAPHY_UNAVAILABLE"
    assert provider.provenance()["geographies"] == []


@pytest.mark.parametrize("year", [2021, 2036])
@pytest.mark.parametrize("geography", ["national", "metro", "county"])
def test_missing_measurement_year_has_same_typed_error_for_every_geography(
    synthetic_forecast, year, geography
):
    provider = PolicyEngineSPMProvider(
        synthetic_forecast,
        geography_kind=geography,
        geography_id="A" if geography == "metro" else None,
    )
    with pytest.raises(SPMInputError) as raised:
        provider.calculate_unit(
            year=year,
            adults=2,
            children=2,
            tenure="renter",
            county_fips="01001" if geography == "county" else None,
        )
    assert raised.value.code == "SPM_YEAR_UNAVAILABLE"
    assert str(year) in str(raised.value)
    assert provider.provenance()["years"] == {}
    assert provider.provenance()["geographies"] == []


@pytest.mark.parametrize("year", [2021, 2036])
def test_missing_requested_year_metadata_has_typed_error(
    synthetic_forecast, year
):
    provider = PolicyEngineSPMProvider(synthetic_forecast)
    with pytest.raises(SPMInputError) as raised:
        provider.year_metadata(year)
    assert raised.value.code == "SPM_YEAR_UNAVAILABLE"
    assert provider.provenance()["years"] == {}


@pytest.mark.parametrize("year", [2021, 2036])
@pytest.mark.parametrize("geography", ["national", "metro"])
def test_actual_tax_only_calculation_does_not_require_forecast_year(
    synthetic_forecast, year, geography
):
    """Forecast coverage is checked by a measurement, never tax-only work."""
    country = pytest.importorskip("policyengine_us")
    from policyengine_us.system import CountryTaxBenefitSystem

    reform = build_policyengine_reform(
        PolicyEngineSPMProvider(
            synthetic_forecast,
            geography_kind=geography,
            geography_id="A" if geography == "metro" else None,
        )
    )
    sim = country.Simulation(
        situation=situation(
            {"adult": {"age": {year: 35}}}, {"unit": ["adult"]}
        ),
        tax_benefit_system=reform(CountryTaxBenefitSystem()),
    )
    tax = sim.calculate("spm_unit_federal_tax", year)
    assert len(tax) == 1
    assert isfinite(float(tax[0]))
    assert (
        sim.tax_benefit_system.spm_forecast_provider.provenance()["years"]
        == {}
    )


def test_provider_snapshot_and_provenance_cannot_mutate_calculation(
    synthetic_forecast,
):
    provider = PolicyEngineSPMProvider(synthetic_forecast)
    other = provider.snapshot()
    entry = provider.year_metadata(2025)
    entry["thresholds"]["renter"] = 1
    assert provider.year_metadata(2025)["thresholds"]["renter"] == 55000
    assert other.provenance()["years"] == {}
    receipt = provider.provenance()
    receipt["years"].clear()
    assert provider.provenance()["years"]


def test_input_ownership_is_limited_to_spm_measurement():
    records = {
        "person": [
            {
                "age": 16,
                "is_spm_independent_minor_role": True,
                "is_adult": False,
            }
        ],
        "spm_units": [{"members": ["a"], "spm_unit_count_adults": 0}],
    }
    before = deepcopy(records)
    validate_policyengine_inputs(records)
    assert records == before
    records["spm_units"][0]["spm_unit_spm_threshold"] = 123
    with pytest.raises(ValueError, match="spm_unit_spm_threshold"):
        validate_policyengine_inputs(records)


def situation(people, units):
    """Explicit native memberships; no computed SPM outputs supplied."""
    names = list(people)
    return {
        "people": people,
        "tax_units": {"tax": {"members": names}},
        "spm_units": {
            key: {"members": members} for key, members in units.items()
        },
        "families": {"family": {"members": names}},
        "marital_units": {key: {"members": [key]} for key in names},
        "households": {
            "household": {"members": names, "county_fips": {2025: "01001"}}
        },
    }


def actual_simulation(synthetic_forecast, people, units):
    country = pytest.importorskip("policyengine_us")
    reform = build_policyengine_reform(
        PolicyEngineSPMProvider(synthetic_forecast)
    )
    from policyengine_us.system import CountryTaxBenefitSystem

    system = reform(CountryTaxBenefitSystem())
    return country.Simulation(
        situation=situation(people, units), tax_benefit_system=system
    ), reform


def test_actual_country_native_membership_single_cast_and_household_minor(
    synthetic_forecast,
):
    import numpy as np

    sim, reform = actual_simulation(
        synthetic_forecast,
        {
            "head": {
                "age": {2025: 16},
                "is_household_head": {"eternity": True},
            },
            "child": {"age": {2025: 1}},
            "adult": {"age": {2025: 35}},
            "dependent": {"age": {2025: 17}},
        },
        {
            "minor_family": ["head", "child"],
            "adult_family": ["adult", "dependent"],
        },
    )
    assert list(sim.spm_unit.ids) == ["minor_family", "adult_family"]
    assert list(sim.calculate("spm_measurement_adults", 2025)) == [1, 1]
    assert list(sim.calculate("spm_measurement_children", 2025)) == [1, 1]
    # Generic benefit eligibility still treats the 16-year-old as a child.
    assert not bool(sim.calculate("is_adult", 2025)[0])
    values = sim.calculate("spm_unit_spm_threshold", 2025)
    tenures = sim.calculate("spm_unit_tenure_type", 2025).decode_to_str()
    expected = [
        reform.spm_forecast_provider.calculate_unit(
            year=2025,
            adults=1,
            children=1,
            tenure=str(tenure).lower(),
            county_fips="01001",
        )["threshold"]
        for tenure in tenures
    ]
    assert np.array_equal(values, np.asarray(expected).astype(values.dtype))
    housing = sim.calculate("spm_unit_spm_threshold_housing_portion", 2025)
    expected_housing = [
        reform.spm_forecast_provider.calculate_unit(
            year=2025,
            adults=1,
            children=1,
            tenure=str(tenure).lower(),
            county_fips="01001",
        )["housing_portion"]
        for tenure in tenures
    ]
    assert np.array_equal(
        housing, np.asarray(expected_housing).astype(housing.dtype)
    )


@pytest.mark.parametrize(
    "person,expected",
    [
        ({"age": {2025: 16}, "is_household_head": {"eternity": True}}, 1),
        ({"age": {2025: 16}, "is_household_spouse": {"eternity": True}}, 1),
        (
            {
                "age": {2025: 17},
                "is_spm_independent_minor_role": {"eternity": True},
            },
            1,
        ),
        ({"age": {2025: 16}}, 0),
        ({"age": {2025: 14}, "is_household_head": {"eternity": True}}, 0),
        (
            {
                "age": {2025: 16},
                "is_household_head": {"eternity": True},
                "is_spm_independent_minor_role": {"eternity": False},
            },
            0,
        ),
    ],
)
def test_actual_minor_role_contract(synthetic_forecast, person, expected):
    sim, _ = actual_simulation(
        synthetic_forecast, {"person": person}, {"unit": ["person"]}
    )
    assert int(sim.calculate("spm_measurement_adults", 2025)[0]) == expected
    if expected:
        assert sim.calculate("spm_unit_spm_threshold", 2025)[0] > 0
    else:
        with pytest.raises(ValueError, match="no classified adult"):
            sim.calculate("spm_unit_spm_threshold", 2025)
