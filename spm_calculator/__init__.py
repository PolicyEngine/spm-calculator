"""
SPM Calculator - Calculate Supplemental Poverty Measure thresholds.

Install with: uv add spm-calculator

Quick start:
    >>> from spm_calculator import spm_threshold
    >>> spm_threshold(2, 2, metro="San Jose")  # 2 adults, 2 children
    59815.0
    >>> spm_threshold(1, 0, tenure="owner_without_mortgage", metro="Alabama Nonmetro")
    12921.81

The threshold calculation is: base[tenure] × equivalence_scale × geoadj[tenure]

Get the pieces separately:
    >>> from spm_calculator import get_thresholds, spm_equivalence_scale, get_metro_geoadj, get_metro_rent_index
    >>> get_thresholds(2024)["renter"]  # Base threshold
    39430.0
    >>> spm_equivalence_scale(2, 2)  # Family size adjustment
    1.0
    >>> get_metro_geoadj("41940", tenure="renter")  # San Jose renter adjustment
    1.5169921379660156
    >>> get_metro_rent_index("41940")  # San Jose raw rent index
    2.167
"""

from .calculator import SPMCalculator, spm_threshold
from .ce_threshold import calculate_base_thresholds, get_published_thresholds
from .equivalence_scale import spm_equivalence_scale
from .fcsuti_cpi import (
    FCSUTI_WEIGHTS,
    compute_fcsuti_weights_from_ce,
    get_fcsuti_cpi,
    get_fcsuti_inflation_factor,
)
from .forecast import (
    HISTORICAL_THRESHOLDS,
    forecast_thresholds,
    get_available_years,
    get_latest_published_year,
    get_threshold_with_metadata,
    get_thresholds,
)
from .geoadj import (
    calculate_geoadj_from_rent,
    create_geoadj_lookup,
    get_available_metro_years,
    get_bundled_cd_data,
    get_bundled_metro_data,
    get_cd_geoadj,
    get_cd_geoadj_batch,
    get_geoadj,
    get_latest_bundled_metro_year,
    get_metro_geoadj,
    get_metro_rent_index,
    list_metro_areas,
)

try:
    from importlib.metadata import (
        PackageNotFoundError,
    )
    from importlib.metadata import (
        version as _pkg_version,
    )
except ImportError:  # pragma: no cover - Python <3.8
    from importlib_metadata import (
        PackageNotFoundError,
    )
    from importlib_metadata import (
        version as _pkg_version,
    )

try:
    __version__ = _pkg_version("spm-calculator")
except PackageNotFoundError:  # pragma: no cover - running from source tree
    __version__ = "0.0.0+unknown"

__all__ = [
    "spm_threshold",
    "SPMCalculator",
    "calculate_base_thresholds",
    "get_published_thresholds",
    "get_geoadj",
    "create_geoadj_lookup",
    "get_cd_geoadj",
    "get_cd_geoadj_batch",
    "get_bundled_cd_data",
    "get_metro_geoadj",
    "get_metro_rent_index",
    "get_bundled_metro_data",
    "get_available_metro_years",
    "get_latest_bundled_metro_year",
    "list_metro_areas",
    "calculate_geoadj_from_rent",
    "spm_equivalence_scale",
    "get_fcsuti_cpi",
    "get_fcsuti_inflation_factor",
    "compute_fcsuti_weights_from_ce",
    "FCSUTI_WEIGHTS",
    "forecast_thresholds",
    "get_thresholds",
    "get_threshold_with_metadata",
    "get_available_years",
    "get_latest_published_year",
    "HISTORICAL_THRESHOLDS",
]
