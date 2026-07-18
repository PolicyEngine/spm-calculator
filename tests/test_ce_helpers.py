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


def _fcsuti_frame(**overrides):
    base = {
        "FOODPQ": [0.0],
        "FOODCQ": [0.0],
        "APPARPQ": [0.0],
        "APPARCQ": [0.0],
        "SHELTPQ": [0.0],
        "SHELTCQ": [0.0],
        "UTILPQ": [0.0],
        "UTILCQ": [0.0],
        "TELEPHPQ": [0.0],
        "TELEPHCQ": [0.0],
    }
    base.update({k: [float(x) for x in v] for k, v in overrides.items()})
    return pd.DataFrame(base)


class TestCalculateFCSUti:
    def test_annualizes_recall_window_by_four(self):
        """PQ+CQ is one 3-month recall window split across calendar
        quarters, so annual = (PQ+CQ) * 4. The pre-0.4 code multiplied
        by 2, understating annual FCSUti by half."""
        df = _fcsuti_frame(FOODPQ=[1000], FOODCQ=[500])
        assert calculate_fcsuti(df).iloc[0] == 6000

    def test_legacy_pqcq2_mode_reproduces_old_behavior(self):
        df = _fcsuti_frame(FOODPQ=[1000], FOODCQ=[500])
        assert calculate_fcsuti(df, annualization="pqcq2").iloc[0] == 3000

    def test_telephone_not_double_counted(self):
        """UTIL already contains TELEPH (UTIL = NTLGAS + ELCTRC +
        ALLFUL + TELEPH + WATRPS), so FCSUti must not add the TELEPH
        summary on top of UTIL."""
        df = _fcsuti_frame(
            UTILPQ=[800], UTILCQ=[400], TELEPHPQ=[300], TELEPHCQ=[150]
        )
        # utilities-only total: (800+400)*4; telephone columns add
        # nothing because they are already inside UTIL.
        assert calculate_fcsuti(df).iloc[0] == 4800

    def test_includes_mortgage_principal_by_default(self):
        """SPM shelter is the outlays concept: CE's SHELT excludes
        owner mortgage principal, so the EMRTPNO*/MRTPRNO* outlay
        columns are added back."""
        df = _fcsuti_frame(
            SHELTPQ=[2000],
            SHELTCQ=[1000],
            EMRTPNOP=[500],
            EMRTPNOC=[250],
            MRTPRNOP=[100],
            MRTPRNOC=[50],
        )
        # (3000 shelter + 750 home principal + 150 vacation) * 4
        assert calculate_fcsuti(df).iloc[0] == pytest.approx(15600)
        assert calculate_fcsuti(df, mortgage_principal="exclude").iloc[
            0
        ] == pytest.approx(12000)

    def test_food_redesign_fallback_uses_fdhome_fdaway(self):
        """Vintages after the 2023 CE food redesign drop the FOOD
        summary; food is rebuilt from FDHOME + FDAWAY."""
        df = _fcsuti_frame().drop(columns=["FOODPQ", "FOODCQ"])
        df["FDHOMEPQ"] = [600.0]
        df["FDHOMECQ"] = [300.0]
        df["FDAWAYPQ"] = [200.0]
        df["FDAWAYCQ"] = [100.0]
        assert calculate_fcsuti(df).iloc[0] == 4800

    def test_rejects_unknown_modes(self):
        df = _fcsuti_frame()
        with pytest.raises(ValueError, match="mortgage_principal"):
            calculate_fcsuti(df, mortgage_principal="subtract")
        with pytest.raises(ValueError, match="annualization"):
            calculate_fcsuti(df, annualization="cq4")


class TestGetTenureType:
    def test_modern_cutenure_codes_split_owners(self):
        """Post-2013 FMLI: 1=owner w/mortgage, 2=owner w/o, 3=renter."""
        df = pd.DataFrame(
            {
                "CUTENURE": [1, 2, 3, 4],
                "ce_year": [2020, 2020, 2020, 2020],
            }
        )
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
                "ce_year": [2010, 2010, 2010],
                "EMRTPNOP": [500, 0, 0],
                "EMRTPNOC": [500, 0, 0],
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

    def test_owners_only_modern_subset_labels_by_schema_not_observed_codes(
        self,
    ):
        """Regression: filtering a modern CE vintage down to owners-only
        (CUTENURE ∈ {1, 2}) used to trip the observed-code heuristic
        (`(cutenure >= 3).any() == False`) and misclassify rows as
        legacy-schema, relabelling `CUTENURE == 2` as renter. With
        schema derived from `ce_year`, owners-only subsets on the modern
        schema classify correctly."""
        df = pd.DataFrame(
            {
                "CUTENURE": [1, 2, 1, 2],
                "ce_year": [2020, 2020, 2020, 2020],
            }
        )
        tenure = get_tenure_type(df)
        assert tenure.tolist() == [
            "owner_with_mortgage",
            "owner_without_mortgage",
            "owner_with_mortgage",
            "owner_without_mortgage",
        ]

    def test_mixed_vintage_raises_on_schema_ambiguity(self):
        """Mixing pre-2013 and post-2013 rows in a single frame would
        apply the wrong CUTENURE interpretation to at least one side;
        we refuse rather than silently coerce."""
        df = pd.DataFrame(
            {
                "CUTENURE": [1, 2],
                "ce_year": [2010, 2020],
            }
        )
        with pytest.raises(ValueError, match="mixes pre-2013 and post-2013"):
            get_tenure_type(df)


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

    def test_returns_nan_on_empty_input(self):
        """Previously the function indexed `cumulative[-1]` on an empty
        array and raised `IndexError`. This path is reachable when a
        tenure bucket drops to zero rows after `dropna` and the pooled
        fallback is also empty."""
        assert np.isnan(
            _weighted_percentile(
                np.array([]),
                np.array([]),
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


class TestFoodRedesign:
    """The April 2023 CE food redesign (GROCER-based vintages)."""

    def test_grocer_rows_use_eighty_percent_allocation(self):
        """Redesign rows: food = 0.8 x GROCER + FDAWAY (BLS errata)."""
        df = _fcsuti_frame(GROCERPQ=[1000], GROCERCQ=[500])
        df = df.drop(columns=["FOODPQ", "FOODCQ"])
        df["FDAWAYPQ"] = [200.0]
        df["FDAWAYCQ"] = [100.0]
        # (0.8 * 1500 + 300) * 4 = 6000
        assert calculate_fcsuti(df).iloc[0] == pytest.approx(6000)

    def test_mixed_vintage_window_is_rowwise(self):
        """Pooled windows mix legacy-FOOD and GROCER schemas; food must
        resolve per row. A frame-wide column check zeroes food for one
        vintage — the artifact that made replicated 2025 thresholds
        fall 4-5% nominal before this construction existed."""
        import numpy as np

        df = pd.DataFrame(
            {
                "FOODPQ": [1000.0, np.nan],
                "FOODCQ": [500.0, np.nan],
                "GROCERPQ": [np.nan, 1000.0],
                "GROCERCQ": [np.nan, 500.0],
                "FDAWAYPQ": [np.nan, 200.0],
                "FDAWAYCQ": [np.nan, 100.0],
                "APPARPQ": [0.0, 0.0],
                "APPARCQ": [0.0, 0.0],
                "SHELTPQ": [0.0, 0.0],
                "SHELTCQ": [0.0, 0.0],
                "UTILPQ": [0.0, 0.0],
                "UTILCQ": [0.0, 0.0],
            }
        )
        result = calculate_fcsuti(df)
        assert result.iloc[0] == pytest.approx(6000)  # legacy: 1500*4
        assert result.iloc[1] == pytest.approx(6000)  # 0.8*1500+300, *4
