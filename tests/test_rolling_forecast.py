"""The offline forecast consumer keeps all selected-year inputs together."""

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from spm_calculator import SPMUnit
from spm_calculator.release import TENURES, canonical_bytes
from spm_calculator.rolling_forecast import (
    SPMForecast,
    forecast_digest,
    load_forecast,
)


def example_document():
    years = {}
    for year, base, share, index in (
        (2024, 100, 0.4, 1.5),
        (2025, 110, 0.4, 1.6),
        (2026, 120, 0.5, 1.8),
    ):
        years[str(year)] = {
            "thresholds": dict.fromkeys(TENURES, base),
            "housing_shares": dict.fromkeys(TENURES, share),
            "rent_indices": {"A": index, "B": 0.8},
            "geography_by_area": {
                code: {
                    "status": "published_anchor"
                    if year == 2024
                    else "modeled",
                    "anchor_status": "published_anchor",
                    "official_published_area": True,
                    "source_ids": ["source"],
                }
                for code in ("A", "B")
            },
            "national_status": "published" if year <= 2025 else "forecast",
            "geography_status": (
                "published_anchor" if year == 2024 else "modeled"
            ),
            "housing_share_status": (
                "published_anchor" if year == 2024 else "modeled"
            ),
            "ce_window": {
                "start": f"{year - 5}Q2",
                "end": f"{year}Q1",
                "observed_quarters": 20 if year <= 2025 else 16,
                "projected_quarters": 0 if year <= 2025 else 4,
            },
            "acs_window": {
                "start": year - 5,
                "end": year - 1,
                "observed_years": 5 if year <= 2025 else 4,
                "projected_years": 0 if year <= 2025 else 1,
            },
            "median_diagnostics": {"A": {"thin_support": True}},
        }
    trend = copy.deepcopy(years)
    trend["2026"]["thresholds"] = dict.fromkeys(TENURES, 130)
    trend["2026"]["housing_shares"] = dict.fromkeys(TENURES, 0.6)
    document = {
        "schema_version": 2,
        "method": "rolling_ce_acs_v1",
        "units": "USD/year",
        "reference_family": {"adults": 2, "children": 2},
        "forecast_id": "synthetic-forecast",
        "information_date": "2026-09-09",
        "created_on": "2026-09-09",
        "base_release_sha256": "a" * 64,
        "default_scenario": "ce_trend",
        "areas": {
            "A": {"name": "Area A", "area_type": "msa"},
            "B": {"name": "Area B", "area_type": "state_nonmetro"},
        },
        "county_assignments": {
            "county_vintage": "2020",
            "boundary_vintage": "2013-02-28",
            "assignment_method": "research_county_assignment",
            "maps": {"current": {"01001": "A", "01003": "B"}},
            "year_maps": {str(y): "current" for y in (2024, 2025, 2026)},
        },
        "sources": [
            {
                "id": "source",
                "url": "https://example.org/source",
                "sha256": "b" * 64,
                "available_on": "2026-09-09",
            }
        ],
        "assumptions": {"note": "Synthetic unit-test inputs"},
        "validation": {
            "ce": {"status": "complete"},
            "acs": {"status": "complete"},
        },
        "scenarios": {
            "zero_real": {
                "label": "No real spending growth",
                "real_growth_rate": 0.0,
                "years": years,
            },
            "ce_trend": {
                "label": "CE real-spending trend",
                "real_growth_rate": 0.01,
                "shrinkage": 0.5,
                "years": trend,
            },
        },
    }
    document["assumption_sha256"] = hashlib.sha256(
        canonical_bytes(document["assumptions"])
    ).hexdigest()
    document["county_assignments"]["sha256"] = hashlib.sha256(
        canonical_bytes(document["county_assignments"])
    ).hexdigest()
    document["content_sha256"] = forecast_digest(document)
    return document


def test_county_assignment_is_an_area_lookup_with_explicit_provenance():
    projection = SPMForecast.from_dict(example_document())
    assignment = projection.resolve_county(2026, "01001")
    assert assignment["area_id"] == "A"
    assert assignment["kind"] == "metro"
    assert assignment["county_vintage"] == "2020"
    assert assignment["status"] == "research_assignment"
    assert projection.areas_for_year(2024)["A"]["status"] == "published_anchor"
    assert projection.areas_for_year(2026)["A"]["status"] == "modeled"
    for county in (1001, "1001", "99999", None):
        with pytest.raises(ValueError):
            projection.resolve_county(2026, county)
    with pytest.raises(ValueError, match="vintage"):
        projection.resolve_county(2026, "01001", county_vintage="2010")
    with pytest.raises(ValueError, match="no entry"):
        projection.resolve_county(2037, "01001")


def test_year_specific_area_universe_and_unanchored_status():
    document = example_document()
    document["areas"]["C"] = {
        "name": "Residual modeled",
        "area_type": "modeled_residual_metro",
    }
    for scenario in document["scenarios"].values():
        entry = scenario["years"]["2026"]
        entry["rent_indices"]["C"] = entry["rent_indices"].pop("B")
        entry["geography_by_area"].pop("B")
        entry["geography_by_area"]["C"] = {
            "status": "modeled_unanchored",
            "anchor_status": "modeled_unanchored",
            "official_published_area": False,
            "source_ids": ["source"],
        }
        entry["geography_status"] = "mixed"
    assignment = document["county_assignments"]
    assignment["maps"]["later"] = {"01001": "A", "01003": "C"}
    assignment["year_maps"]["2026"] = "later"
    assignment["sha256"] = hashlib.sha256(
        canonical_bytes({k: v for k, v in assignment.items() if k != "sha256"})
    ).hexdigest()
    document["content_sha256"] = forecast_digest(document)
    projection = SPMForecast.from_dict(document)
    assert set(projection.areas_for_year(2024)) == {"A", "B"}
    assert set(projection.areas_for_year(2026)) == {"A", "C"}
    assert projection.resolve_county(2024, "01003")["area_id"] == "B"
    assert projection.resolve_county(2026, "01003")["area_id"] == "C"
    result = projection.geography_factor(
        2026, "renter", kind="metro", geoid="C"
    )
    assert result["status"] == "modeled_unanchored"
    assert result["official_published_area"] is False
    with pytest.raises(ValueError, match="unavailable"):
        projection.geography_factor(2026, "renter", kind="metro", geoid="B")


def unit(year=2026, **kwargs):
    return SPMUnit(
        unit_id="family",
        num_adults=2,
        num_children=2,
        tenure="renter",
        year=year,
        geography_kind="metro",
        geography_id="A",
        **kwargs,
    )


def test_selected_year_and_scenario_change_all_inputs():
    projection = SPMForecast.from_dict(example_document())
    old = projection.calculate_unit(unit(2024))
    observed = projection.calculate_unit(unit(2025))
    zero = projection.calculate_unit(unit(), scenario="zero_real")
    trend = projection.calculate_unit(unit(), scenario="ce_trend")
    assert old["threshold"] == pytest.approx(120)
    assert observed["threshold"] == pytest.approx(136.4)
    assert zero["threshold"] == pytest.approx(168)
    assert trend["threshold"] == pytest.approx(192.4)
    assert trend["housing_portion"] == pytest.approx(140.4)
    assert observed["national_status"] == "published"
    assert observed["geography_status"] == "modeled"
    assert trend["provenance"]["geography"]["diagnostics"]["thin_support"]
    assert trend["provenance"]["ce_window"]["end"] == "2026Q1"


def test_resources_and_reference_family_scaling():
    projection = SPMForecast.from_dict(example_document())
    assert (
        projection.calculate_unit(unit(resources=192.4))["is_in_poverty"]
        is False
    )
    assert (
        projection.calculate_unit(unit(resources=190))["is_in_poverty"] is True
    )
    single = SPMUnit("single", 1, 0, "renter", 2026)
    result = projection.calculate_unit(single)
    assert result["geographic_factor"] == 1
    assert result["geography_status"] == "explicit_national"
    assert result["threshold"] == pytest.approx(
        130 * result["equivalence_factor"]
    )


def test_forecast_is_immutable_and_accessors_return_copies():
    document = example_document()
    projection = SPMForecast.from_dict(document)
    document["scenarios"]["ce_trend"]["years"]["2026"]["thresholds"][
        "renter"
    ] = 1
    projection.entry(2026)["thresholds"]["renter"] = 2
    projection.to_dict()["scenarios"].clear()
    projection.calculate_unit(unit())["provenance"]["geography"][
        "diagnostics"
    ]["thin_support"] = False
    assert projection.entry(2026)["thresholds"]["renter"] == 130
    assert projection.calculate_unit(unit())["provenance"]["geography"][
        "diagnostics"
    ]["thin_support"]
    with pytest.raises(AttributeError):
        projection._json = b"changed"


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["scenarios"]["ce_trend"]["years"]["2026"][
            "rent_indices"
        ].pop("A"),
        lambda d: d["scenarios"]["ce_trend"]["years"]["2026"][
            "housing_shares"
        ].update(renter=1.1),
        lambda d: d["scenarios"]["ce_trend"]["years"]["2026"][
            "ce_window"
        ].update(end="2027Q1"),
        lambda d: d["scenarios"]["ce_trend"]["years"]["2026"][
            "acs_window"
        ].update(projected_years=2),
        lambda d: d["sources"][0].update(available_on="2026-09-10"),
        lambda d: d.update(units="USD/month"),
        lambda d: d["assumptions"].update(note="Changed assumptions"),
        lambda d: d["scenarios"]["ce_trend"].update(shrinkage=1),
        lambda d: d["scenarios"]["ce_trend"]["years"]["2026"].update(
            median_diagnostics=None
        ),
    ],
)
def test_invalid_contract_rejected_even_with_recomputed_digest(change):
    document = example_document()
    change(document)
    document["content_sha256"] = forecast_digest(document)
    with pytest.raises(ValueError):
        SPMForecast.from_dict(document)


def test_digest_and_information_date_enforced(tmp_path):
    document = example_document()
    with pytest.raises(ValueError, match="expected_sha256"):
        SPMForecast.from_dict(document, expected_sha256="f" * 64)
    with pytest.raises(ValueError, match="information date"):
        SPMForecast.from_dict(document, as_of="2025-12-31")
    document["forecast_id"] = "tampered"
    with pytest.raises(ValueError, match="hash mismatch"):
        SPMForecast.from_dict(document)
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        load_forecast(path)


def test_missing_selection_never_falls_back():
    projection = SPMForecast.from_dict(example_document())
    with pytest.raises(ValueError, match="scenario"):
        projection.entry(2026, scenario="guess")
    with pytest.raises(ValueError, match="2027"):
        projection.entry(2027)
    with pytest.raises(ValueError, match="unavailable"):
        projection.calculate_unit(
            SPMUnit(
                "x",
                2,
                2,
                "renter",
                2026,
                geography_kind="metro",
                geography_id="missing",
            )
        )


def test_explicit_adjustment_status_and_housing_boundary():
    projection = SPMForecast.from_dict(example_document())
    explicit = SPMUnit("x", 2, 2, "renter", 2026, geographic_adjustment=0.4)
    result = projection.calculate_unit(explicit)
    assert result["geography_status"] == "caller_supplied"
    assert result["bundled_geography_status"] == "modeled"
    assert result["housing_portion"] == pytest.approx(0)
    with pytest.raises(ValueError, match="negative housing portion"):
        projection.calculate_unit(
            SPMUnit("x", 2, 2, "renter", 2026, geographic_adjustment=0.39)
        )
    with pytest.raises(ValueError, match="unsupported"):
        projection.calculate_unit(
            SPMUnit(
                "x",
                2,
                2,
                "renter",
                2026,
                geography_kind="state",
                geography_id="06",
            )
        )


def test_consumer_runs_without_site_packages_or_network(tmp_path):
    path = tmp_path / "forecast.json"
    path.write_text(json.dumps(example_document()))
    code = """
import socket
def forbidden(*args, **kwargs):
    raise AssertionError('network forbidden')
socket.socket = forbidden
from spm_calculator import load_forecast, SPMUnit
p = load_forecast(sys.argv[1])
r = p.calculate_unit(SPMUnit('x',2,2,'renter',2026,geography_kind='metro',geography_id='A'))
assert abs(r['threshold'] - 192.4) < 1e-10
assert not any(m in sys.modules for m in ('numpy','pandas','policyengine','requests'))
"""
    subprocess.run(
        [sys.executable, "-S", "-c", "import sys\n" + code, str(path)],
        cwd=Path(__file__).parents[1],
        check=True,
        capture_output=True,
    )
