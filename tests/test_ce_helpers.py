"""Unit tests for the CE threshold helper functions.

These cover the pure-function helpers that run without a live BLS
download: FCSUti expenditure assembly, tenure classification, and the
weighted-percentile routine. End-to-end tests against the full BLS
pipeline live in ``test_ce_validation.py`` and are gated behind a
network skip.
"""

import numpy as np
import pandas as pd
import pytest

from spm_calculator.ce_threshold import (
    _sum_pair,
    _weighted_percentile,
    calculate_fcsuti,
    get_tenure_type,
)


class TestSumPair:
    def test_sums_two_columns_when_both_present(self):
        df = pd.DataFrame({"FOODPQ": [100, 200], "FOODCQ": [50, 75]})
        result = _sum_pair(df, "FOODPQ", "FOODCQ")
        assert list(result) == [150, 275]

    def test_returns_zero_when_either_column_missing(self):
        df = pd.DataFrame({"FOODPQ": [100, 200]})
        result = _sum_pair(df, "FOODPQ", "FOODCQ")
        assert list(result) == [0, 0]

    def test_treats_nan_as_zero(self):
        df = pd.DataFrame({"FOODPQ": [100, np.nan], "FOODCQ": [np.nan, 50]})
        result = _sum_pair(df, "FOODPQ", "FOODCQ")
        assert list(result) == [100, 50]


class TestCalculateFCSUti:
    def test_annualizes_by_factor_two_not_four(self):
        """PQ+CQ covers 2 of 4 quarters, so annual = sum * 2."""
        df = pd.DataFrame(
            {
                "FOODPQ": [1000],
                "FOODCQ": [1000],
                "APPARPQ": [0],
                "APPARCQ": [0],
                "SHELTPQ": [0],
                "SHELTCQ": [0],
                "UTILPQ": [0],
                "UTILCQ": [0],
                "TELEPHPQ": [0],
                "TELEPHCQ": [0],
            }
        )
        # (1000 + 1000) * 2 = 4000 (the old buggy code returned 8000).
        assert calculate_fcsuti(df).iloc[0] == 4000

    def test_subtracts_mortgage_principal_from_shelter(self):
        df = pd.DataFrame(
            {
                "FOODPQ": [0],
                "FOODCQ": [0],
                "APPARPQ": [0],
                "APPARCQ": [0],
                "SHELTPQ": [2000],
                "SHELTCQ": [2000],
                "UTILPQ": [0],
                "UTILCQ": [0],
                "TELEPHPQ": [0],
                "TELEPHCQ": [0],
                "MRTPRINPQ": [500],
                "MRTPRINCQ": [500],
            }
        )
        # shelter = (2000+2000) - (500+500) = 3000; annualized = 6000.
        assert calculate_fcsuti(df).iloc[0] == 6000

    def test_includes_internet_services_when_present(self):
        df_without_internet = pd.DataFrame(
            {
                "FOODPQ": [0],
                "FOODCQ": [0],
                "APPARPQ": [0],
                "APPARCQ": [0],
                "SHELTPQ": [0],
                "SHELTCQ": [0],
                "UTILPQ": [0],
                "UTILCQ": [0],
                "TELEPHPQ": [0],
                "TELEPHCQ": [0],
            }
        )
        df_with_internet = df_without_internet.assign(
            INFOTECHPQ=[200], INFOTECHCQ=[200]
        )
        assert calculate_fcsuti(df_without_internet).iloc[0] == 0
        assert calculate_fcsuti(df_with_internet).iloc[0] == 800


class TestGetTenureType:
    def test_modern_cutenure_codes_split_owners(self):
        """Post-2013 FMLI: 1=owner w/mortgage, 2=owner w/o, 3=renter."""
        df = pd.DataFrame({"CUTENURE": [1, 2, 3, 4]})
        tenure = get_tenure_type(df)
        assert tenure.tolist() == [
            "owner_with_mortgage",
            "owner_without_mortgage",
            "renter",
            "renter",  # Occupied without payment defaults to renter.
        ]

    def test_legacy_cutenure_uses_mortgage_expenditure(self):
        """Pre-2013 vintages only split owners (1) vs renters (2)."""
        df = pd.DataFrame(
            {
                # No row uses the modern code 2 for owner-without; the
                # branch falls back to mortgage-expenditure detection.
                "CUTENURE": [1, 1, 2],
                "MRTPRINPQ": [500, 0, 0],
                "MRTPRINCQ": [500, 0, 0],
                "MRTINTPQ": [0, 0, 0],
                "MRTINTCQ": [0, 0, 0],
            }
        )
        tenure = get_tenure_type(df)
        assert tenure.tolist() == [
            "owner_with_mortgage",
            "owner_without_mortgage",
            "renter",
        ]


class TestWeightedPercentile:
    def test_uniform_weights_median_is_center_for_odd_length(self):
        """At p=50 on an odd-length array with uniform weights, the
        midpoint-CDF convention returns the center element — this is
        the one percentile where it coincides with numpy.percentile."""
        values = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0])
        weights = np.ones_like(values)
        got = _weighted_percentile(values, weights, 50.0)
        assert got == pytest.approx(40.0)

    def test_midpoint_cdf_convention_differs_from_numpy_default(self):
        """Regression guard: document that this helper uses the
        midpoint-CDF convention, not numpy's default ``linear``.

        For uniform weights on ``[10, 20, ..., 70]``:
        - numpy default at p=25 → 25.0 (linear: 25 = 10 + 0.25·60)
        - midpoint-CDF at p=25 → 22.5 (each obs sits at CDF ~= 0.5/7,
          1.5/7, ..., 6.5/7; interpolating p=0.25 lands between 20 and
          30 at 22.5).
        If someone "fixes" this helper to match numpy default, this
        test fails and they re-read the docstring."""
        values = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0])
        weights = np.ones_like(values)
        assert _weighted_percentile(values, weights, 25.0) == pytest.approx(
            22.5
        )
        assert _weighted_percentile(values, weights, 75.0) == pytest.approx(
            57.5
        )

    def test_weights_move_the_median(self):
        """A CU with large weight should dominate the median."""
        values = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        weights = np.array([1.0, 1.0, 1.0, 1.0, 100.0])
        # The value 50 carries almost all the weight, so median ≈ 50.
        assert _weighted_percentile(values, weights, 50.0) == pytest.approx(
            50.0, rel=1e-2
        )

    def test_returns_nan_on_zero_weights(self):
        assert np.isnan(
            _weighted_percentile(
                np.array([1.0, 2.0, 3.0]),
                np.array([0.0, 0.0, 0.0]),
                50.0,
            )
        )

    def test_p47_and_p53_bracket_the_median(self):
        """The BLS robust-median window: P47 ≤ median ≤ P53."""
        rng = np.random.default_rng(42)
        values = rng.normal(40000, 5000, 1000)
        weights = rng.uniform(100, 10000, 1000)
        p47 = _weighted_percentile(values, weights, 47.0)
        p50 = _weighted_percentile(values, weights, 50.0)
        p53 = _weighted_percentile(values, weights, 53.0)
        assert p47 <= p50 <= p53
