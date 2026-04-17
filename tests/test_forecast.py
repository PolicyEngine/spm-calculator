"""Tests for the forecast module.

Covers:

- The "far-future" RuntimeWarning (bug 9): silently compounding decades
  of 2% inflation off a hardcoded base is not useful output.
- The historical back-cast error message (bug 10): a clearer "earliest
  supported year is 2015" rather than "Year 2014 not in historical data".
- Sub-dollar precision (bug 16): `forecast_thresholds` no longer casts
  to int before composition with equivalence and geographic adjustments.
"""

from __future__ import annotations

import warnings

import pytest

from spm_calculator.forecast import (
    CPI_PROJECTIONS,
    FORECAST_WARNING_HORIZON,
    HISTORICAL_THRESHOLDS,
    LATEST_PUBLISHED_YEAR,
    calculate_cumulative_inflation,
    forecast_thresholds,
    get_threshold_with_metadata,
)


class TestForecastHorizonWarning:
    def test_short_horizon_is_silent(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            forecast_thresholds(LATEST_PUBLISHED_YEAR + 1)
        assert not any(
            "Forecasting SPM thresholds" in str(w.message) for w in caught
        )

    def test_far_horizon_warns_past_threshold(self):
        target = LATEST_PUBLISHED_YEAR + FORECAST_WARNING_HORIZON + 1
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            forecast_thresholds(target)
        matching = [
            w
            for w in caught
            if "Forecasting SPM thresholds" in str(w.message)
        ]
        assert matching, "Expected a RuntimeWarning past the horizon"

    def test_far_horizon_metadata_flag(self):
        target = LATEST_PUBLISHED_YEAR + FORECAST_WARNING_HORIZON + 10
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            meta = get_threshold_with_metadata(target)
        assert meta["beyond_reliable_horizon"] is True
        assert meta["horizon_years"] == target - LATEST_PUBLISHED_YEAR

    def test_near_horizon_metadata_flag_is_false(self):
        target = LATEST_PUBLISHED_YEAR + 1
        meta = get_threshold_with_metadata(target)
        assert meta["beyond_reliable_horizon"] is False


class TestBackCastErrorMessage:
    def test_below_earliest_supported_year_message(self):
        """Previously raised 'Year 2014 not in historical data'; now
        explicitly references the earliest supported year."""
        earliest = min(HISTORICAL_THRESHOLDS.keys())
        with pytest.raises(
            ValueError, match="below the earliest supported year"
        ):
            forecast_thresholds(earliest - 1)


class TestForecastPrecision:
    def test_precision_is_retained_through_float_return(self):
        """Previously `int(round(...))` truncated sub-dollar precision
        before downstream composition with equivalence and geographic
        adjustments. Values now flow as floats so `base × scale ×
        geoadj` matches the mathematically exact product."""
        year = LATEST_PUBLISHED_YEAR + 1
        base = HISTORICAL_THRESHOLDS[LATEST_PUBLISHED_YEAR]["renter"]
        factor = calculate_cumulative_inflation(LATEST_PUBLISHED_YEAR, year)
        expected = base * factor
        forecast = forecast_thresholds(year)
        assert forecast["renter"] == pytest.approx(expected)
        # Concrete: the old int-round path returned an integer with
        # zero fractional part; the new path retains precision past
        # the decimal point.
        assert isinstance(forecast["renter"], float)

    def test_historical_year_still_returns_int_values(self):
        """Historical published values stay as integers (the BLS
        tables report whole-dollar thresholds); only the forecast
        path keeps floats."""
        values = forecast_thresholds(LATEST_PUBLISHED_YEAR)
        for tenure, amount in values.items():
            assert amount == int(amount), (
                f"Published {tenure} threshold drifted from "
                f"HISTORICAL_THRESHOLDS"
            )


def test_cpi_projections_end_year_referenced_in_warning():
    """Sanity: the warning mentions the end of the CPI projection window
    so callers know the 2%/yr extrapolation is not arbitrary."""
    end = max(CPI_PROJECTIONS)
    target = LATEST_PUBLISHED_YEAR + FORECAST_WARNING_HORIZON + 1
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        forecast_thresholds(target)
    texts = [str(w.message) for w in caught]
    assert any(str(end) in text for text in texts), (
        f"Expected CPI projection end year {end} in warning"
    )
