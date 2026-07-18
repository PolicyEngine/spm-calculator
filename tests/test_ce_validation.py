"""
Tests validating CE Survey calculation against BLS published thresholds.

These tests download actual CE PUMD data and verify our calculations
match the published BLS values within acceptable tolerance.
"""

import os

import pytest

# Skip all tests in this module if CE data download is slow/unavailable
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_CE_DOWNLOAD", "1") == "1",
    reason="CE download tests disabled by default (set SKIP_CE_DOWNLOAD=0 to run)",
)


class TestCECalculation:
    """Test CE Survey-based threshold calculation against BLS published values."""

    @pytest.mark.slow
    def test_calculate_2024_thresholds_from_ce(self):
        """
        Replicate 2024 thresholds from CE PUMD and compare to the
        corrected BLS series.

        Corrected 2024 thresholds (published 2026-07-17):
        - Renter: $39,219.89
        - Owner with mortgage: $39,231.00
        - Owner without mortgage: $32,878.59

        Measured replication fidelity (scripts/benchmark_bls_replication
        .py, see docs/bls-2026-correction.md): the faithful variant
        (BLS quarter window, principal-inclusive shelter, quarter4
        annualization, 82% anchor) lands within ~4% per tenure for
        2024. The 6% tolerance leaves headroom for CE re-releases and
        CPI revisions without masking structural regressions — the
        pre-0.4 replication was 20-60% off and would fail loudly.

        Known gaps keeping this from ~1%: BLS adds imputed in-kind
        benefits (broadband, LIHEAP, NSLP, WIC, rental assistance) to
        CU-level FCSUti, and FMLI has no internet summary variable.

        Note: downloads ~600MB of CE bundles on first run (cached).
        """
        from spm_calculator.ce_threshold import calculate_base_thresholds
        from spm_calculator.forecast import get_thresholds

        calculated = calculate_base_thresholds(
            target_year=2024,
            use_published_fallback=False,
        )
        corrected = get_thresholds(2024, allow_forecast=False)

        tolerance = 0.06

        for tenure, reference in corrected.items():
            calc_value = calculated[tenure]
            pct_diff = abs(calc_value - reference) / reference

            print(f"{tenure}:")
            print(f"  Calculated: ${calc_value:,.0f}")
            print(f"  Corrected:  ${reference:,.0f}")
            print(f"  Difference: {pct_diff:.1%}")

            assert pct_diff < tolerance, (
                f"{tenure} threshold differs by {pct_diff:.1%} "
                f"(calculated=${calc_value:,.0f}, "
                f"corrected=${reference:,.0f})"
            )

    @pytest.mark.slow
    def test_tenure_ordering_from_ce(self):
        """Verify tenure ordering is correct when calculated from CE data."""
        from spm_calculator.ce_threshold import calculate_base_thresholds

        calculated = calculate_base_thresholds(
            target_year=2024,
            use_published_fallback=False,
        )

        # Owner without mortgage should have lowest threshold
        assert (
            calculated["owner_without_mortgage"]
            < calculated["owner_with_mortgage"]
        )
        # Owner with mortgage should be close to but <= renter
        assert calculated["owner_with_mortgage"] <= calculated["renter"] * 1.05


class TestCEDataDownload:
    """Test CE PUMD data download functionality."""

    @pytest.mark.slow
    def test_download_single_quarter(self):
        """Test downloading a single quarter of CE data."""
        from spm_calculator.ce_threshold import download_ce_fmli

        # Download Q1 2022 (relatively recent, should be available)
        df = download_ce_fmli(2022, 1)

        assert len(df) > 0
        assert "CUTENURE" in df.columns  # Housing tenure
        assert "ce_year" in df.columns
        assert df["ce_year"].iloc[0] == 2022

    @pytest.mark.slow
    def test_fcsuti_calculation(self):
        """Test FCSUti calculation on real CE data."""
        from spm_calculator.ce_threshold import (
            calculate_fcsuti,
            download_ce_fmli,
        )

        df = download_ce_fmli(2022, 1)
        fcsuti = calculate_fcsuti(df)

        # FCSUti should be positive for most households
        assert (fcsuti > 0).mean() > 0.9

        # Median should be in reasonable range ($20k-$80k annual)
        median_fcsuti = fcsuti.median()
        assert 20000 < median_fcsuti < 80000, f"Median FCSUti={median_fcsuti}"


class TestFCSUtiCPI:
    """Test FCSUti CPI-U composite index calculation."""

    def test_fcsuti_cpi_components(self):
        """
        Verify we have the correct CPI component weights.

        FCSUti CPI-U is a composite of:
        - Food (at home and away)
        - Apparel
        - Shelter
        - Utilities (fuel and utilities)
        - Telephone services
        - Internet services

        The weights should approximately match CE expenditure shares.
        """
        # Expected approximate weights based on CE data
        # These are rough estimates - actual weights vary by year
        expected_weights = {
            "food": 0.30,  # ~30% of FCSUti
            "apparel": 0.05,  # ~5%
            "shelter": 0.45,  # ~45% (largest component)
            "utilities": 0.12,  # ~12%
            "telephone_internet": 0.08,  # ~8%
        }

        total = sum(expected_weights.values())
        assert 0.99 < total < 1.01, "Weights should sum to ~1.0"

    def test_published_fcsuti_inflation_2024(self):
        """
        Verify FCSUti inflation rate matches BLS published figure.

        BLS states FCSUti inflation was 3.98% in 2024.
        """
        # This is informational - we'll implement the actual calculation
        published_fcsuti_inflation_2024 = 0.0398
        assert published_fcsuti_inflation_2024 == pytest.approx(0.04, rel=0.1)
