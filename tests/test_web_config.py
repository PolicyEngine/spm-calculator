"""Checks that the generated web bundle preserves data vintages."""

import json
from pathlib import Path

import pytest

from scripts.generate_geoadj_data import (
    generate_all_thresholds,
    generate_nowcast_evaluations,
)

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
