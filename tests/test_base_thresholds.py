"""
Tests for SPM base threshold calculation from Consumer Expenditure Survey.

Corrected BLS 2024 thresholds (reference family 2A2C), published
2026-07-17:
- Renter: $39,219.89
- Owner with mortgage: $39,231.00
- Owner without mortgage: $32,878.59

Source: https://www.bls.gov/pir/spm/spm_thresholds_2024_correction.htm
(workbook bundled at spm_calculator/data/bls/, parsed by
scripts/build_threshold_series.py).
"""

import pytest

from spm_calculator.ce_threshold import (
    BLS_PUBLISHED_THRESHOLDS_2024,
    get_published_thresholds,
)


class TestPublishedThresholds:
    """Test retrieval of published BLS thresholds."""

    def test_2024_thresholds_match_corrected_bls(self):
        """2024 thresholds should match the corrected BLS workbook at
        full precision."""
        thresholds = get_published_thresholds(2024)

        assert thresholds["renter"] == pytest.approx(39219.893902)
        assert thresholds["owner_with_mortgage"] == pytest.approx(39230.994457)
        assert thresholds["owner_without_mortgage"] == pytest.approx(
            32878.594848
        )

    def test_2023_thresholds(self):
        """2023 thresholds should match the corrected series."""
        thresholds = get_published_thresholds(2023)

        assert thresholds["renter"] == pytest.approx(37230.752855)
        assert thresholds["owner_with_mortgage"] == pytest.approx(36966.23764)
        assert thresholds["owner_without_mortgage"] == pytest.approx(
            30587.725238
        )

    def test_2022_thresholds(self):
        """2022 thresholds should match the corrected series."""
        thresholds = get_published_thresholds(2022)

        assert thresholds["renter"] == pytest.approx(34140.062994)
        assert thresholds["owner_with_mortgage"] == pytest.approx(33978.493165)
        assert thresholds["owner_without_mortgage"] == pytest.approx(
            28454.915504
        )

    def test_published_thresholds_cover_full_historical_range(self):
        """`get_published_thresholds` must expose the same years as
        `forecast.HISTORICAL_THRESHOLDS` (2005–2024 since the corrected
        workbook), not a hardcoded subset."""
        from spm_calculator.forecast import HISTORICAL_THRESHOLDS

        assert min(HISTORICAL_THRESHOLDS) == 2005
        assert max(HISTORICAL_THRESHOLDS) == 2024
        for year in HISTORICAL_THRESHOLDS:
            assert (
                get_published_thresholds(year) == HISTORICAL_THRESHOLDS[year]
            ), f"get_published_thresholds({year}) drifted from HISTORICAL_THRESHOLDS"

    def test_unavailable_year_raises(self):
        """Pre-2005 and far-future years are genuinely unavailable."""
        with pytest.raises(ValueError, match="not available"):
            get_published_thresholds(1999)

    def test_returns_copy(self):
        """Should return a copy, not the original dict."""
        thresholds = get_published_thresholds(2024)
        thresholds["renter"] = 0

        # Original should be unchanged
        assert BLS_PUBLISHED_THRESHOLDS_2024["renter"] == pytest.approx(
            39219.893902
        )


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


class TestCEThresholdMethodology:
    """Test core CE-threshold methodology details."""

    @staticmethod
    def _renter_sample():
        import pandas as pd

        return pd.DataFrame(
            {
                "CUTENURE": [3, 3, 3],
                "PERSLT18": [2, 2, 2],
                "FAM_SIZE": [4, 4, 4],
                "ce_year": [2023, 2023, 2023],
                "FINLWT21": [1000.0, 1000.0, 1000.0],
                "FOODPQ": [100.0, 100.0, 100.0],
                "FOODCQ": [100.0, 100.0, 100.0],
                "SHELTPQ": [300.0, 300.0, 300.0],
                "SHELTCQ": [300.0, 300.0, 300.0],
            }
        )

    def test_calculate_base_thresholds_applies_fcsuti_inflation(
        self, monkeypatch
    ):
        """Doubling the CPI factor must double the threshold — proving
        the per-year inflation factors flow through the pipeline."""
        import spm_calculator.ce_threshold as ce_threshold

        results = {}
        for factor in (1.0, 2.0):
            monkeypatch.setattr(
                ce_threshold,
                "get_fcsuti_inflation_factor",
                lambda from_year, to_year, weights=None, f=factor: f,
            )
            results[factor] = ce_threshold.calculate_base_thresholds(
                ce=self._renter_sample(),
                target_year=2024,
                use_published_fallback=False,
            )

        assert results[2.0]["renter"] == pytest.approx(
            2 * results[1.0]["renter"]
        )
        # Absolute check for factor 1: every CU is an identical
        # 2A2C renter, so SU terms cancel and the formula reduces to
        # 0.82 * 1.2 * FCSUti = 0.82 * 1.2 * (200 + 600) * 4.
        assert results[1.0]["renter"] == pytest.approx(0.82 * 1.2 * 3200)

    def test_calculate_base_thresholds_requires_perslt18(self, monkeypatch):
        """Regression: without `PERSLT18`, the old fallback
        `FAM_SIZE > PERSOT64` silently matched any CU with a non-elderly
        member, including two-adult / zero-child units — a methodology
        error. The function now refuses rather than producing a wrong
        number."""
        import pandas as pd

        import spm_calculator.ce_threshold as ce_threshold

        # A two-adult no-child CU would pass the old fallback
        # (FAM_SIZE=2 > PERSOT64=0) but must not be included.
        sample = pd.DataFrame(
            {
                "CUTENURE": [2, 2],
                "FAM_SIZE": [2, 2],
                "PERSOT64": [0, 0],
                "ADULT": [2, 2],
                "ce_year": [2022, 2023],
            }
        )

        monkeypatch.setattr(
            ce_threshold, "download_ce_pumd_years", lambda years: sample.copy()
        )

        with pytest.raises(ValueError, match="PERSLT18"):
            ce_threshold.calculate_base_thresholds(
                years=[2022, 2023],
                target_year=2024,
                use_published_fallback=False,
            )


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
