"""Checks that the generated web bundle preserves data vintages."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts.export_web_release import build_config
from scripts.generate_geoadj_data import (
    generate_all_thresholds,
    generate_nowcast_evaluations,
)
from spm_calculator.release import SPMUnit, canonical_bytes
from spm_calculator.rolling_forecast import load_forecast

REPO = Path(__file__).parents[1]
CONFIG = REPO / "web/public/data/spm_config.json"

PUBLISHED_2025 = {
    "owner_with_mortgage": 41322.707394,
    "owner_without_mortgage": 34325.99772,
    "renter": 41700.555713,
}


def test_generated_thresholds_use_published_2025_values():
    thresholds = generate_all_thresholds()
    assert thresholds["2025"] == pytest.approx(PUBLISHED_2025)


def test_archived_nowcast_evaluation_is_separate_from_active_nowcasts():
    evaluation = generate_nowcast_evaluations()["2025"]
    assert evaluation["actual_series"] == "bls-published-2025"
    assert evaluation["mean_absolute_percentage_error"] == pytest.approx(
        1.170566081645456
    )
    assert evaluation["tenures"]["renter"] == pytest.approx(
        {
            "nowcast": 40755.97769114959,
            "actual": 41700.555713,
            "percentage_error": -2.265144926008611,
        }
    )


def test_committed_config_marks_2025_as_published():
    config = json.loads(CONFIG.read_text())
    assert config["forecast"]["latestPublishedYear"] == 2025
    assert config["baseThresholds"]["2025"] == pytest.approx(PUBLISHED_2025)
    assert "2025" not in config["nowcast"]
    assert (
        config["nowcastEvaluation"]["2025"]["actual_series"]
        == "bls-published-2025"
    )


def test_browser_exports_only_official_census_spm_areas():
    """The 2024 Census workbook defines MSAs and state residual areas.

    Source: https://www2.census.gov/programs-surveys/demo/tables/p60/287/
    SPM-pov-threshold-2024.xlsx, bundled in metro_geoadj_2024.json.
    State, county and district rent approximations are not these areas.
    """
    config = build_config()
    official = json.loads(
        (REPO / "spm_calculator/data/metro_geoadj_2024.json").read_text()
    )["metroAreas"]
    assert set(config["metroAreas"]) == set(official)
    assert len(official) == 341
    names = [area["name"] for area in config["metroAreas"].values()]
    assert sum(name.endswith(" Nonmetro") for name in names) == 47
    assert sum(name.endswith(" Metro") for name in names) == 34
    assert len(names) - 47 - 34 == 260
    for identity, area in config["metroAreas"].items():
        assert area["name"] == official[identity]["name"]
        assert area["rentIndex"] == official[identity]["rentIndex"]
    assert "acsLookup" not in config
    assert not any(
        key in config for key in ("state", "county", "congressional_district")
    )
    assert "nationalMedianRent" not in json.dumps(config)


def test_committed_browser_export_matches_official_area_contract():
    config = json.loads(
        (REPO / "web/public/data/release_config.json").read_text()
    )
    assert config == build_config()
    assert config["baseThresholds"]["2025"] == pytest.approx(PUBLISHED_2025)


def test_forecast_layer_replays_rolling_artifact_separately():
    config = build_config()
    forecast = config["forecast"]
    assert set(forecast["thresholdsByYear"]) == {
        str(year) for year in range(2026, 2031)
    }
    assert "2026" not in config["baseThresholds"]
    assert config["nowcast"] == {}
    projection = load_forecast()
    document = projection.to_dict()
    assert forecast["method"] == "rolling_ce_acs_v1"
    assert forecast["contentSha256"] == projection.content_sha256
    assert forecast["cpiProjections"]["2026"] == 0.023
    assert forecast["defaultScenario"] == "ce_trend"
    for year, thresholds in forecast["thresholdsByYear"].items():
        assert thresholds == projection.entry(int(year))["thresholds"]
    digest = hashlib.sha256(
        canonical_bytes(document["assumptions"])
    ).hexdigest()
    assert forecast["assumptionSha256"] == digest
    assert forecast["baseReleaseSha256"] == config["releaseMetadata"]["sha256"]


@pytest.mark.parametrize("scenario", ["ce_trend", "zero_real"])
@pytest.mark.parametrize("year", range(2024, 2031))
def test_browser_inputs_reproduce_standalone_local_threshold(year, scenario):
    config = build_config()
    projection = load_forecast()
    entry = config["forecast"]["scenarios"][scenario]["years"][str(year)]
    assert set(entry["rent_indices"]) == set(config["metroAreas"])
    for area in ("35620", "41860"):
        unit = SPMUnit(
            "family",
            1,
            2,
            "renter",
            year,
            geography_kind="metro",
            geography_id=area,
        )
        result = projection.calculate_unit(unit, scenario=scenario)
        factor = 1 + entry["housing_shares"]["renter"] * (
            entry["rent_indices"][area] - 1
        )
        browser_amount = (
            entry["thresholds"]["renter"]
            * result["equivalence_factor"]
            * factor
        )
        assert browser_amount == pytest.approx(result["threshold"])
        assert entry["ce_window"]["end"] == f"{year}Q1"
        assert entry["acs_window"]["end"] == year - 1
    if year == 2025:
        assert entry["national_status"] == "published"
        assert entry["geography_status"] == "modeled"
        assert entry["thresholds"] == pytest.approx(PUBLISHED_2025)
