"""Release gates for complete, reproducible forecast inputs and evaluations."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import build_rolling_forecast as builder
from spm_calculator.release import load_release

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def components():
    ce = json.loads(builder.CE_PATH.read_text())
    acs = json.loads(builder.ACS_PATH.read_text())
    areas = load_release().to_dict()["geographies"]["metro"]["areas"]
    return ce, acs, areas


def test_complete_real_evaluation_and_all_horizons(components):
    result = builder.validate_evaluations(*components)
    assert result["ce"]["fold_count"] == 21
    assert result["ce"]["fold_tenure_observation_count"] == 63
    assert result["acs"]["area_count"] == 341
    assert result["ce"]["by_horizon"]["5"]["fold_count"] == 2
    for result in (result["ce"], result["acs"]):
        assert result["status"] == "complete"
        assert result["unvalidated"] is False


@pytest.mark.parametrize(
    "failure",
    [
        "missing_fold",
        "missing_tenure",
        "wrong_shrinkage",
        "missing_area",
        "blocked",
        "bad_metric_flag",
    ],
)
def test_incomplete_or_inconsistent_evaluation_cannot_ship(
    components, failure
):
    ce, acs, areas = copy.deepcopy(components)
    if failure == "missing_fold":
        ce["backtest"]["folds"].pop()
    elif failure == "missing_tenure":
        ce["backtest"]["folds"][0]["scenarios"]["ce_trend"][
            "errors_by_tenure"
        ].pop("renter")
    elif failure == "wrong_shrinkage":
        ce["backtest"]["folds"][0]["scenarios"]["ce_trend"]["shrinkage"] = 1
    elif failure == "missing_area":
        acs["backtest"]["areas"].pop("41860")
    elif failure == "blocked":
        acs["backtest"]["status"] = "blocked"
    elif failure == "bad_metric_flag":
        candidate = ce["backtest"]["scenarios"]["ce_trend"]
        candidate["beats_baseline"] = not candidate["beats_baseline"]
    with pytest.raises(ValueError):
        builder.validate_evaluations(ce, acs, areas)


def test_cpi_receipt_is_package_relative_and_matches_official_m13():
    checks = builder.verify_source_checks()
    assert not Path(checks["bls_cpi"]["path"]).is_absolute()
    assert (
        checks["bls_cpi"]["sha256"]
        == "482678b4dc2070b434ff44b2d09417992b63546dea0ac3a30ec300244e14415e"
    )


def test_different_packaged_cpi_cannot_be_labeled_observed(monkeypatch):
    read = builder.read_json

    def altered(path):
        result = read(path)
        if Path(path).name == "cpi_annual.json":
            result["series"]["CUUR0000SA0"]["2025"] = 322
        return result

    monkeypatch.setattr(builder, "read_json", altered)
    with pytest.raises(ValueError, match="official annual values"):
        builder.verify_source_checks()


@pytest.mark.parametrize(
    "path,digest",
    [
        (
            "web/public/data/spm_config.json",
            "a9173d56ee8e092fd5150f9920c88f9557d383b9ad19eee3bdc67c257cff6996",
        ),
        (
            "spm_calculator/data/releases/spm-2026-09-08.json",
            "a12113b5b574e0d4371814f2c3f127b00f91016bddc94c0f6459b7a7742cf02d",
        ),
        (
            "spm_calculator/data/current/ce_replication_2019_2025.json",
            "d04e2a61552795f9d90e282045610774a4ff68f67b97067677358741f58a289c",
        ),
    ],
)
def test_published_and_archived_artifact_bytes_remain_unchanged(path, digest):
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest


def test_committed_forecast_rebuilds_offline(monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("Assembly must remain offline")

    monkeypatch.setattr(socket, "socket", forbidden)
    assert builder.build_document() == json.loads(builder.OUT.read_text())
