"""Tests for the packaged consumption-based threshold nowcast."""

import pytest

from spm_calculator import (
    get_nowcast_years,
    nowcast_thresholds,
    nowcast_with_metadata,
)
from spm_calculator.forecast import get_thresholds


class TestNowcast2025:
    def test_years(self):
        assert get_nowcast_years() == [2025]

    def test_unavailable_year_raises(self):
        with pytest.raises(ValueError, match="No packaged nowcast"):
            nowcast_thresholds(2030)

    def test_values_are_plausible_relative_to_2024(self):
        """Nowcast 2025 must sit within a few percent of the corrected
        2024 base — a guard against unit or construction errors, not a
        precision claim."""
        base = get_thresholds(2024, allow_forecast=False)
        now = nowcast_thresholds(2025)
        for tenure, value in now.items():
            assert 0.97 < value / base[tenure] < 1.10, (tenure, value)

    def test_metadata_carries_method_and_caveats(self):
        doc = nowcast_with_metadata(2025)
        assert "NOT a BLS publication" in doc["label"]
        assert doc["base_series"] == "bls-corrected-2026-07-17"
        assert doc["caveats"]
        for tenure, parts in doc["components"].items():
            blend = (parts["price_ratio"] + parts["replication_ratio"]) / 2
            assert parts["blend_ratio"] == pytest.approx(blend)

    def test_blend_matches_components_times_base(self):
        doc = nowcast_with_metadata(2025)
        base = get_thresholds(2024, allow_forecast=False)
        for tenure, value in doc["values"].items():
            expected = base[tenure] * doc["components"][tenure]["blend_ratio"]
            assert value == pytest.approx(expected)
