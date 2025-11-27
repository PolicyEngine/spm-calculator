"""
Tests for the main SPMCalculator API.

The full SPM threshold calculation is:
    threshold = base_threshold[tenure] × equivalence_scale × geoadj
"""

import os

import pytest
import numpy as np


REQUIRES_CENSUS_API = pytest.mark.skipif(
    not os.environ.get("CENSUS_API_KEY"),
    reason="Requires CENSUS_API_KEY environment variable",
)


class TestSPMCalculator:
    """Test the main SPMCalculator class."""

    def test_initialization(self):
        """Should initialize with a year."""
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        assert calc.year == 2024

    def test_get_base_thresholds(self):
        """Should return base thresholds by tenure."""
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        base = calc.get_base_thresholds()

        assert "renter" in base
        assert "owner_with_mortgage" in base
        assert "owner_without_mortgage" in base
        assert all(v > 0 for v in base.values())

    def test_get_geoadj_nation(self):
        """National GEOADJ should be 1.0."""
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        geoadj = calc.get_geoadj("nation", "US")

        assert geoadj == pytest.approx(1.0)

    @REQUIRES_CENSUS_API
    def test_get_geoadj_state(self):
        """Should return state GEOADJ."""
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        ca_geoadj = calc.get_geoadj("state", "06")

        assert ca_geoadj > 1.0  # California above average


class TestThresholdCalculation:
    """Test full threshold calculation."""

    def test_reference_family_national(self):
        """Reference family (2A2C) at national level."""
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        threshold = calc.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="renter",
            geography_type="nation",
            geography_id="US",
        )

        # Should equal base threshold (equiv_scale=1.0, geoadj=1.0)
        base = calc.get_base_thresholds()["renter"]
        assert threshold == pytest.approx(base)

    def test_single_adult_scales_down(self):
        """Single adult should have lower threshold than 2A2C."""
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

        assert single_threshold < ref_threshold
        # Single adult = 1.0/2.1 ≈ 0.476 of reference
        ratio = single_threshold / ref_threshold
        assert ratio == pytest.approx(1.0 / 2.1, rel=0.01)

    @REQUIRES_CENSUS_API
    def test_high_cost_area_scales_up(self):
        """High cost area should increase threshold."""
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)

        national = calc.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="renter",
            geography_type="nation",
            geography_id="US",
        )

        # San Francisco area congressional district
        sf_threshold = calc.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="renter",
            geography_type="congressional_district",
            geography_id="0611",  # CA-11 (SF area)
        )

        assert sf_threshold > national
        # SF should be ~15-30% higher
        ratio = sf_threshold / national
        assert 1.10 < ratio < 1.40

    @REQUIRES_CENSUS_API
    def test_low_cost_area_scales_down(self):
        """Low cost area should decrease threshold."""
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)

        national = calc.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="renter",
            geography_type="nation",
            geography_id="US",
        )

        # West Virginia district
        wv_threshold = calc.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="renter",
            geography_type="congressional_district",
            geography_id="5401",  # WV-01
        )

        assert wv_threshold < national
        # WV should be ~10-20% lower
        ratio = wv_threshold / national
        assert 0.80 < ratio < 0.95

    def test_tenure_affects_threshold(self):
        """Different tenure types should give different thresholds."""
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

        # Owner without mortgage should be lower
        assert owner_no_mortgage < renter
        # About 15-20% lower
        ratio = owner_no_mortgage / renter
        assert 0.75 < ratio < 0.90


class TestBatchCalculation:
    """Test batch/vectorized threshold calculation."""

    @REQUIRES_CENSUS_API
    def test_batch_calculation(self):
        """Should handle batch calculation for multiple units."""
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)

        # Multiple SPM units
        results = calc.calculate_thresholds(
            num_adults=np.array([1, 2, 2, 3]),
            num_children=np.array([0, 0, 2, 4]),
            tenure=["renter", "renter", "renter", "owner_with_mortgage"],
            geography_type="state",
            geography_ids=["06", "06", "54", "54"],  # CA, CA, WV, WV
        )

        assert len(results) == 4
        assert all(t > 0 for t in results)

        # CA thresholds should be higher than WV
        assert results[0] > results[2]  # Single in CA > couple in WV? Depends
        assert results[1] > results[3]  # Compare same compositions

    def test_batch_with_single_geography(self):
        """Should broadcast single geography to all units."""
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)

        results = calc.calculate_thresholds(
            num_adults=np.array([1, 2, 3]),
            num_children=np.array([0, 2, 4]),
            tenure=["renter", "renter", "renter"],
            geography_type="nation",
            geography_ids="US",  # Single value, broadcast to all
        )

        assert len(results) == 3
        # Should scale by equivalence only (geoadj=1.0 for all)
        base = calc.get_base_thresholds()["renter"]
        expected_ratios = np.array([1.0, 2.1, 3.2]) / 2.1
        expected = base * expected_ratios
        np.testing.assert_array_almost_equal(results, expected)


class TestYearForecasting:
    """Test threshold calculation for different years."""

    def test_future_year_higher_than_past(self):
        """Future year should have higher thresholds (inflation)."""
        from spm_calculator import SPMCalculator

        calc_2022 = SPMCalculator(year=2022)
        calc_2024 = SPMCalculator(year=2024)

        t_2022 = calc_2022.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="renter",
            geography_type="nation",
            geography_id="US",
        )

        t_2024 = calc_2024.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="renter",
            geography_type="nation",
            geography_id="US",
        )

        assert t_2024 > t_2022

    def test_forecasting_beyond_published(self):
        """Should be able to forecast beyond published years."""
        from spm_calculator import SPMCalculator

        # 2025 thresholds not published yet
        calc = SPMCalculator(year=2025)
        threshold = calc.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="renter",
            geography_type="nation",
            geography_id="US",
        )

        # Should be higher than 2024
        calc_2024 = SPMCalculator(year=2024)
        t_2024 = calc_2024.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="renter",
            geography_type="nation",
            geography_id="US",
        )

        assert threshold > t_2024


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_tenure_raises(self):
        """Invalid tenure type should raise ValueError."""
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)

        with pytest.raises(ValueError, match="tenure"):
            calc.calculate_threshold(
                num_adults=2,
                num_children=2,
                tenure="invalid_tenure",
                geography_type="nation",
                geography_id="US",
            )

    def test_zero_persons_returns_zero(self):
        """Zero adults and zero children should return 0 or raise."""
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)

        result = calc.calculate_threshold(
            num_adults=0,
            num_children=0,
            tenure="renter",
            geography_type="nation",
            geography_id="US",
        )

        assert result == 0.0

    def test_negative_persons_raises(self):
        """Negative person counts should raise ValueError."""
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)

        with pytest.raises(ValueError):
            calc.calculate_threshold(
                num_adults=-1,
                num_children=2,
                tenure="renter",
                geography_type="nation",
                geography_id="US",
            )
