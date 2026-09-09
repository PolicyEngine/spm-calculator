"""SPM calculation and reproducible releases. Heavy legacy APIs load on demand."""

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("spm-calculator")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

_EXPORTS = {
    "SPMCalculator": "calculator",
    "spm_threshold": "calculator",
    "calculate_base_thresholds": "ce_threshold",
    "get_published_thresholds": "ce_threshold",
    "spm_equivalence_scale": "equivalence_scale",
    "FCSUTI_WEIGHTS": "fcsuti_cpi",
    "compute_fcsuti_weights_from_ce": "fcsuti_cpi",
    "get_fcsuti_cpi": "fcsuti_cpi",
    "get_fcsuti_inflation_factor": "fcsuti_cpi",
    "HISTORICAL_THRESHOLDS": "forecast",
    "forecast_thresholds": "forecast",
    "get_available_years": "forecast",
    "get_latest_published_year": "forecast",
    "get_threshold_with_metadata": "forecast",
    "get_thresholds": "forecast",
    "calculate_geoadj_from_rent": "geoadj",
    "create_geoadj_lookup": "geoadj",
    "get_available_metro_years": "geoadj",
    "get_bundled_cd_data": "geoadj",
    "get_bundled_metro_data": "geoadj",
    "get_cd_geoadj": "geoadj",
    "get_cd_geoadj_batch": "geoadj",
    "get_geoadj": "geoadj",
    "get_latest_bundled_metro_year": "geoadj",
    "get_metro_geoadj": "geoadj",
    "get_metro_rent_index": "geoadj",
    "list_metro_areas": "geoadj",
    "get_nowcast_years": "nowcast",
    "nowcast_thresholds": "nowcast",
    "nowcast_with_metadata": "nowcast",
    "spm_unit_id": "units",
    "spm_threshold_match": "validation",
    "spm_unit_id_match": "validation",
    "SPMRelease": "release",
    "SPMUnit": "release",
    "load_release": "release",
    "SPMForecast": "rolling_forecast",
    "load_forecast": "rolling_forecast",
}

__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{_EXPORTS[name]}", __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
