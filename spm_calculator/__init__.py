"""Canonical SPM forecasts, reproducible releases and scientific source tools."""

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("spm-calculator")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

_EXPORTS = {
    "calculate_base_thresholds": "ce_threshold",
    "get_published_thresholds": "published_thresholds",
    "spm_equivalence_scale": "equivalence_scale",
    "FCSUTI_WEIGHTS": "fcsuti_cpi",
    "compute_fcsuti_weights_from_ce": "fcsuti_cpi",
    "get_fcsuti_cpi": "fcsuti_cpi",
    "get_fcsuti_inflation_factor": "fcsuti_cpi",
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
