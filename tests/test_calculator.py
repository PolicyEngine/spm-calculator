"""
Tests for the main SPM calculator API.
"""

import os

import numpy as np
import pytest

REQUIRES_CENSUS_API = pytest.mark.skipif(
    not os.environ.get("CENSUS_API_KEY"),
    reason="Requires CENSUS_API_KEY environment variable",
)

REFERENCE_RAW_SCALE = 3**0.7


class TestSPMCalculator:
    """Test the main SPMCalculator class."""

    def test_initialization(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        assert calc.year == 2024

    def test_get_base_thresholds(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        base = calc.get_base_thresholds()

        assert "renter" in base
        assert "owner_with_mortgage" in base
        assert "owner_without_mortgage" in base
        assert all(v > 0 for v in base.values())

    def test_future_year_base_thresholds_use_shared_forecast_path(self):
        from spm_calculator import SPMCalculator, get_thresholds

        calc = SPMCalculator(year=2026)
        assert calc.get_base_thresholds() == get_thresholds(2026)

    def test_get_geoadj_nation(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        geoadj = calc.get_geoadj("nation", "US", tenure="renter")

        assert geoadj == pytest.approx(1.0)

    def test_get_geoadj_metro_uses_official_census_data(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        geoadj = calc.get_geoadj("metro_area", "35620", tenure="renter")

        assert geoadj == pytest.approx(45736 / 39430)

    @REQUIRES_CENSUS_API
    def test_get_geoadj_state(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        ca_geoadj = calc.get_geoadj("state", "06", tenure="renter")

        assert ca_geoadj > 1.0


class TestThresholdCalculation:
    """Test full threshold calculation."""

    def test_reference_family_national(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        threshold = calc.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="renter",
            geography_type="nation",
            geography_id="US",
        )

        assert threshold == pytest.approx(calc.get_base_thresholds()["renter"])

    def test_single_adult_scales_down(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)

        ref_threshold = calc.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="renter",
            geography_type="nation",
            geography_id="US",
        )

        single_threshold = calc.calculate_threshold(
            num_adults=1,
            num_children=0,
            tenure="renter",
            geography_type="nation",
            geography_id="US",
        )

        ratio = single_threshold / ref_threshold
        assert ratio == pytest.approx(1.0 / REFERENCE_RAW_SCALE)

    def test_reference_family_metro_matches_census_workbook(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        threshold = calc.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="renter",
            geography_type="metro_area",
            geography_id="1002",
        )

        assert threshold == pytest.approx(31622)

    def test_spm_threshold_matches_census_workbook(self):
        from spm_calculator import spm_threshold

        assert spm_threshold(2, 2, tenure="renter", metro="35620", year=2024) == pytest.approx(
            45736
        )
        assert spm_threshold(
            2,
            2,
            tenure="owner_with_mortgage",
            metro="35620",
            year=2024,
        ) == pytest.approx(45189)

    def test_tenure_affects_threshold(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)

        renter = calc.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="renter",
            geography_type="nation",
            geography_id="US",
        )

        owner_no_mortgage = calc.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="owner_without_mortgage",
            geography_type="nation",
            geography_id="US",
        )

        assert owner_no_mortgage < renter
        ratio = owner_no_mortgage / renter
        assert 0.75 < ratio < 0.90


class TestBatchCalculation:
    """Test batch/vectorized threshold calculation."""

    @REQUIRES_CENSUS_API
    def test_batch_calculation(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)

        results = calc.calculate_thresholds(
            num_adults=np.array([1, 2, 2, 3]),
            num_children=np.array([0, 0, 2, 4]),
            tenure=["renter", "renter", "renter", "owner_with_mortgage"],
            geography_type="state",
            geography_ids=["06", "06", "54", "54"],
        )

        assert len(results) == 4
        assert all(t > 0 for t in results)

    def test_batch_with_single_geography(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)

        results = calc.calculate_thresholds(
            num_adults=np.array([1, 2, 3]),
            num_children=np.array([0, 2, 4]),
            tenure=["renter", "renter", "renter"],
            geography_type="nation",
            geography_ids="US",
        )

        assert len(results) == 3
        base = calc.get_base_thresholds()["renter"]
        expected_scales = np.array([1.0, REFERENCE_RAW_SCALE, 5**0.7]) / REFERENCE_RAW_SCALE
        expected = base * expected_scales
        np.testing.assert_allclose(results, expected)

    def test_batch_uses_tenure_specific_metro_adjustments(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        results = calc.calculate_thresholds(
            num_adults=np.array([2, 2, 2]),
            num_children=np.array([2, 2, 2]),
            tenure=[
                "renter",
                "owner_with_mortgage",
                "owner_without_mortgage",
            ],
            geography_type="metro_area",
            geography_ids=["1002", "1002", "1002"],
        )

        np.testing.assert_allclose(results, np.array([31622, 31489, 27881]))


# Published 2024 reference thresholds from the Census SPM metro workbook,
# for a 2-adult, 2-child reference family. Pins every tenure across a range
# of cost levels so a regression in rent index, tenure share, or base
# threshold in any direction is caught.
CENSUS_2024_METRO_REFERENCE_THRESHOLDS = [
    # (metro_geoid, name, renter, owner_with_mortgage, owner_without_mortgage)
    ("41940", "San Jose (high cost)", 59815, 58855, 44869),
    ("31080", "Los Angeles", 49910, 49241, 38901),
    ("47900", "Washington, DC", 48076, 47461, 37796),
    ("35620", "New York", 45736, 45189, 36386),
    ("16980", "Chicago", 40094, 39712, 32986),
    ("1002", "Alabama Nonmetro (low cost)", 31622, 31489, 27881),
]


@pytest.mark.parametrize(
    "metro_geoid,name,renter,owner_with_mortgage,owner_without_mortgage",
    CENSUS_2024_METRO_REFERENCE_THRESHOLDS,
    ids=[row[1] for row in CENSUS_2024_METRO_REFERENCE_THRESHOLDS],
)
def test_metro_reference_thresholds_match_published_2024(
    metro_geoid,
    name,
    renter,
    owner_with_mortgage,
    owner_without_mortgage,
):
    """All three tenure-specific thresholds for a 2A2C reference family must
    match the Census Bureau's published 2024 SPM metro workbook exactly."""
    from spm_calculator import spm_threshold

    assert spm_threshold(
        2, 2, tenure="renter", metro=metro_geoid, year=2024
    ) == pytest.approx(renter)
    assert spm_threshold(
        2, 2, tenure="owner_with_mortgage", metro=metro_geoid, year=2024
    ) == pytest.approx(owner_with_mortgage)
    assert spm_threshold(
        2, 2, tenure="owner_without_mortgage", metro=metro_geoid, year=2024
    ) == pytest.approx(owner_without_mortgage)
