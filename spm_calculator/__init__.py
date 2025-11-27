"""
SPM Calculator - Calculate Supplemental Poverty Measure thresholds.

This package calculates SPM thresholds for any US geography and year using:
- Base thresholds from BLS Consumer Expenditure Survey (by tenure type)
- Geographic adjustments (GEOADJ) from ACS median rents
- SPM three-parameter equivalence scale for family composition

Example:
    >>> from spm_calculator import SPMCalculator
    >>> calc = SPMCalculator(year=2024)
    >>> threshold = calc.calculate_threshold(
    ...     num_adults=2,
    ...     num_children=2,
    ...     tenure="renter",
    ...     geography_type="congressional_district",
    ...     geography_id="0612"
    ... )
"""

from .calculator import SPMCalculator
from .ce_threshold import calculate_base_thresholds, get_published_thresholds
from .geoadj import get_geoadj, create_geoadj_lookup
from .equivalence_scale import spm_equivalence_scale
from .fcsuti_cpi import get_fcsuti_cpi, get_fcsuti_inflation_factor
from .forecast import (
    forecast_thresholds,
    get_thresholds,
    get_threshold_with_metadata,
    get_available_years,
    get_latest_published_year,
    HISTORICAL_THRESHOLDS,
)

__version__ = "0.1.0"

__all__ = [
    "SPMCalculator",
    "calculate_base_thresholds",
    "get_published_thresholds",
    "get_geoadj",
    "create_geoadj_lookup",
    "spm_equivalence_scale",
    "get_fcsuti_cpi",
    "get_fcsuti_inflation_factor",
    "forecast_thresholds",
    "get_thresholds",
    "get_threshold_with_metadata",
    "get_available_years",
    "get_latest_published_year",
    "HISTORICAL_THRESHOLDS",
]
