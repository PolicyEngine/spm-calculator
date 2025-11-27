"""
Forecast SPM thresholds for future years.

Uses historical BLS thresholds and CPI projections to forecast thresholds
for years not yet published by BLS.

The BLS typically publishes thresholds with a 1-2 year lag, so forecasting
is necessary for current and future year calculations.
"""

from typing import Optional

import numpy as np

# Historical BLS published thresholds
HISTORICAL_THRESHOLDS = {
    2015: {
        "renter": 25155,
        "owner_with_mortgage": 24859,
        "owner_without_mortgage": 20639,
    },
    2016: {
        "renter": 25558,
        "owner_with_mortgage": 25248,
        "owner_without_mortgage": 20943,
    },
    2017: {
        "renter": 26213,
        "owner_with_mortgage": 25897,
        "owner_without_mortgage": 21527,
    },
    2018: {
        "renter": 26905,
        "owner_with_mortgage": 26565,
        "owner_without_mortgage": 22095,
    },
    2019: {
        "renter": 27515,
        "owner_with_mortgage": 27172,
        "owner_without_mortgage": 22600,
    },
    2020: {
        "renter": 28881,
        "owner_with_mortgage": 28533,
        "owner_without_mortgage": 23948,
    },
    2021: {
        "renter": 31453,
        "owner_with_mortgage": 31089,
        "owner_without_mortgage": 26022,
    },
    2022: {
        "renter": 33402,
        "owner_with_mortgage": 32949,
        "owner_without_mortgage": 27679,
    },
    2023: {
        "renter": 36606,
        "owner_with_mortgage": 36192,
        "owner_without_mortgage": 30347,
    },
    2024: {
        "renter": 39430,
        "owner_with_mortgage": 39068,
        "owner_without_mortgage": 32586,
    },
}

# Latest year with published BLS thresholds
LATEST_PUBLISHED_YEAR = 2024

# CPI-U annual inflation projections (from CBO/Federal Reserve forecasts)
# These should be updated periodically based on latest forecasts
CPI_PROJECTIONS = {
    2025: 0.025,  # 2.5% projected inflation
    2026: 0.023,  # 2.3%
    2027: 0.022,  # 2.2%
    2028: 0.020,  # 2.0% (long-run target)
    2029: 0.020,
    2030: 0.020,
}

# Default long-run inflation assumption
DEFAULT_INFLATION = 0.020  # 2.0% Fed target


def get_inflation_rate(year: int) -> float:
    """
    Get projected or assumed inflation rate for a year.

    Args:
        year: Calendar year

    Returns:
        Annual inflation rate (e.g., 0.025 for 2.5%)
    """
    return CPI_PROJECTIONS.get(year, DEFAULT_INFLATION)


def calculate_cumulative_inflation(
    from_year: int, to_year: int
) -> float:
    """
    Calculate cumulative inflation factor between two years.

    Args:
        from_year: Starting year
        to_year: Ending year

    Returns:
        Cumulative inflation factor (e.g., 1.05 for 5% total inflation)
    """
    if to_year <= from_year:
        return 1.0

    factor = 1.0
    for year in range(from_year + 1, to_year + 1):
        factor *= 1 + get_inflation_rate(year)

    return factor


def forecast_thresholds(
    year: int,
    base_year: Optional[int] = None,
    custom_inflation: Optional[float] = None,
) -> dict[str, float]:
    """
    Forecast SPM thresholds for a future year.

    Uses historical thresholds and CPI projections to estimate thresholds
    for years not yet published by BLS.

    Args:
        year: Target year for forecast
        base_year: Year to use as base for projection. If None, uses
                   the latest published year.
        custom_inflation: Optional custom annual inflation rate to use
                         instead of projections.

    Returns:
        Dict with forecasted threshold values by tenure type
    """
    if year <= LATEST_PUBLISHED_YEAR:
        if year in HISTORICAL_THRESHOLDS:
            return HISTORICAL_THRESHOLDS[year].copy()
        else:
            raise ValueError(
                f"Year {year} not in historical data. "
                f"Available: {sorted(HISTORICAL_THRESHOLDS.keys())}"
            )

    # Use latest published year as base
    if base_year is None:
        base_year = LATEST_PUBLISHED_YEAR

    base_thresholds = HISTORICAL_THRESHOLDS[base_year]

    # Calculate inflation adjustment
    if custom_inflation is not None:
        years_ahead = year - base_year
        inflation_factor = (1 + custom_inflation) ** years_ahead
    else:
        inflation_factor = calculate_cumulative_inflation(base_year, year)

    # Apply inflation to all tenure types
    forecasted = {
        tenure: int(round(value * inflation_factor))
        for tenure, value in base_thresholds.items()
    }

    return forecasted


def get_thresholds(
    year: int,
    allow_forecast: bool = True,
    custom_inflation: Optional[float] = None,
) -> dict[str, float]:
    """
    Get SPM thresholds for any year, with optional forecasting.

    This is the main entry point for getting thresholds. It returns
    published values when available and forecasts when necessary.

    Args:
        year: Target year
        allow_forecast: If True, forecast future years. If False,
                       raise error for unpublished years.
        custom_inflation: Optional custom inflation rate for forecasting.

    Returns:
        Dict with threshold values by tenure type

    Raises:
        ValueError: If year not available and forecasting disabled
    """
    if year in HISTORICAL_THRESHOLDS:
        return HISTORICAL_THRESHOLDS[year].copy()

    if not allow_forecast:
        raise ValueError(
            f"Thresholds not available for {year} and forecasting disabled. "
            f"Latest published: {LATEST_PUBLISHED_YEAR}"
        )

    return forecast_thresholds(year, custom_inflation=custom_inflation)


def get_threshold_with_metadata(
    year: int,
    allow_forecast: bool = True,
    custom_inflation: Optional[float] = None,
) -> dict:
    """
    Get thresholds with metadata about source and methodology.

    Args:
        year: Target year
        allow_forecast: If True, forecast future years.
        custom_inflation: Optional custom inflation rate.

    Returns:
        Dict with:
        - thresholds: threshold values by tenure
        - year: the year
        - source: 'published' or 'forecast'
        - base_year: base year used for forecast (if applicable)
        - inflation_factor: total inflation applied (if forecasted)
    """
    is_forecast = year > LATEST_PUBLISHED_YEAR

    if is_forecast and not allow_forecast:
        raise ValueError(f"Year {year} requires forecasting")

    thresholds = get_thresholds(
        year,
        allow_forecast=allow_forecast,
        custom_inflation=custom_inflation,
    )

    result = {
        "thresholds": thresholds,
        "year": year,
        "source": "forecast" if is_forecast else "published",
    }

    if is_forecast:
        base_year = LATEST_PUBLISHED_YEAR
        if custom_inflation is not None:
            years_ahead = year - base_year
            inflation_factor = (1 + custom_inflation) ** years_ahead
        else:
            inflation_factor = calculate_cumulative_inflation(
                base_year, year
            )

        result["base_year"] = base_year
        result["inflation_factor"] = inflation_factor
        result["inflation_rate"] = (
            custom_inflation
            if custom_inflation
            else get_inflation_rate(year)
        )

    return result


def get_available_years() -> list[int]:
    """Get list of years with published thresholds."""
    return sorted(HISTORICAL_THRESHOLDS.keys())


def get_latest_published_year() -> int:
    """Get the most recent year with published BLS thresholds."""
    return LATEST_PUBLISHED_YEAR
