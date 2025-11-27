"""
Tests for SPM base threshold calculation from Consumer Expenditure Survey.

BLS 2024 published thresholds (for reference family 2A2C):
- Renter: $39,430
- Owner with mortgage: $39,068
- Owner without mortgage: $32,586

Source: https://www.bls.gov/pir/spm/spm_thresholds_2024.htm
"""

import pytest

from spm_calculator.ce_threshold import (
    get_published_thresholds,
    BLS_PUBLISHED_THRESHOLDS_2024,
)


class TestPublishedThresholds:
    """Test retrieval of published BLS thresholds."""

    def test_2024_thresholds_match_bls(self):
        """2024 thresholds should match BLS published values."""
        thresholds = get_published_thresholds(2024)

        assert thresholds["renter"] == 39430
        assert thresholds["owner_with_mortgage"] == 39068
        assert thresholds["owner_without_mortgage"] == 32586

    def test_2023_thresholds(self):
        """2023 thresholds should be available."""
        thresholds = get_published_thresholds(2023)

        assert thresholds["renter"] == 36606
        assert thresholds["owner_with_mortgage"] == 36192
        assert thresholds["owner_without_mortgage"] == 30347

    def test_2022_thresholds(self):
        """2022 thresholds should be available."""
        thresholds = get_published_thresholds(2022)

        assert thresholds["renter"] == 33402
        assert thresholds["owner_with_mortgage"] == 32949
        assert thresholds["owner_without_mortgage"] == 27679

    def test_unavailable_year_raises(self):
        """Requesting unavailable year should raise ValueError."""
        with pytest.raises(ValueError, match="not available"):
            get_published_thresholds(2015)

    def test_returns_copy(self):
        """Should return a copy, not the original dict."""
        thresholds = get_published_thresholds(2024)
        thresholds["renter"] = 0

        # Original should be unchanged
        assert BLS_PUBLISHED_THRESHOLDS_2024["renter"] == 39430


class TestThresholdRelationships:
    """Test relationships between tenure-specific thresholds."""

    def test_owner_without_mortgage_lowest(self):
        """Owner without mortgage should have lowest threshold."""
        thresholds = get_published_thresholds(2024)

        assert thresholds["owner_without_mortgage"] < thresholds["renter"]
        assert (
            thresholds["owner_without_mortgage"]
            < thresholds["owner_with_mortgage"]
        )

    def test_renter_and_owner_with_mortgage_similar(self):
        """Renter and owner with mortgage should be similar (within 5%)."""
        thresholds = get_published_thresholds(2024)

        ratio = thresholds["renter"] / thresholds["owner_with_mortgage"]
        assert 0.95 < ratio < 1.05

    def test_owner_without_mortgage_significantly_lower(self):
        """Owner without mortgage should be ~15-20% lower than renter."""
        thresholds = get_published_thresholds(2024)

        ratio = thresholds["owner_without_mortgage"] / thresholds["renter"]
        assert 0.75 < ratio < 0.90


class TestThresholdTrends:
    """Test that thresholds trend upward over time."""

    def test_thresholds_increase_2022_to_2024(self):
        """All tenure types should increase from 2022 to 2024."""
        t2022 = get_published_thresholds(2022)
        t2024 = get_published_thresholds(2024)

        for tenure in [
            "renter",
            "owner_with_mortgage",
            "owner_without_mortgage",
        ]:
            assert t2024[tenure] > t2022[tenure], f"{tenure} should increase"

    def test_inflation_rate_reasonable(self):
        """Implied inflation rate should be reasonable (5-25% over 2 years)."""
        t2022 = get_published_thresholds(2022)
        t2024 = get_published_thresholds(2024)

        for tenure in [
            "renter",
            "owner_with_mortgage",
            "owner_without_mortgage",
        ]:
            growth = (t2024[tenure] - t2022[tenure]) / t2022[tenure]
            assert (
                0.05 < growth < 0.30
            ), f"{tenure} growth {growth:.1%} outside range"


# TODO: Add integration tests that actually download CE data
# These would be slower and require network access
class TestCEDataDownload:
    """Integration tests for CE Survey data download."""

    @pytest.mark.skip(reason="Requires network access and is slow")
    def test_download_single_quarter(self):
        """Should be able to download a single quarter of CE data."""
        from spm_calculator.ce_threshold import download_ce_fmli

        df = download_ce_fmli(2022, 1)
        assert len(df) > 0
        assert "CUTENURE" in df.columns

    @pytest.mark.skip(reason="Requires network access and is slow")
    def test_calculate_thresholds_from_ce(self):
        """Calculated thresholds should be within 10% of published."""
        from spm_calculator.ce_threshold import calculate_base_thresholds

        calculated = calculate_base_thresholds(
            years=[2018, 2019, 2020, 2021, 2022],
            target_year=2024,
            use_published_fallback=False,
        )
        published = get_published_thresholds(2024)

        for tenure in [
            "renter",
            "owner_with_mortgage",
            "owner_without_mortgage",
        ]:
            ratio = calculated[tenure] / published[tenure]
            assert 0.90 < ratio < 1.10, f"{tenure} off by more than 10%"
