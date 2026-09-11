"""Published threshold source access for scientific comparison and backtesting.

Read the bundled ``data/bls/threshold_series.json`` without projecting or
selecting forecasts. Unavailable years raise ``ValueError``. Current package
calculations use ``rolling_forecast.load_forecast``.

The default ``bls-corrected-2026-07-17`` series preserves workbook precision:
old-methodology values for 2005–2018, corrected revised-methodology values
for 2019–2024, and the BLS-published 2025 continuation. Standard errors,
tenure shares and the source segment's provenance remain available.

``census-published-pre-correction`` preserves Census's published 2019–2024
values. ``package-legacy-0.3`` preserves earlier package values, including
known hand-entry errors, solely as reproducibility evidence. Selecting an
archived source series never supplies missing years from another series.
"""

from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from importlib import resources
from typing import Optional

DEFAULT_SERIES = "bls-corrected-2026-07-17"


LEGACY_SERIES = "package-legacy-0.3"


@lru_cache(maxsize=1)
def _threshold_data() -> dict:
    """Load the packaged threshold-series document."""
    ref = resources.files("spm_calculator").joinpath(
        "data/bls/threshold_series.json"
    )
    return json.loads(ref.read_text())


def _flatten_series(name: str) -> dict[int, dict[str, float]]:
    """Flatten a series entry to ``{year: {tenure: threshold}}``.

    For the corrected BLS series, the canonical view splices the
    old-methodology segment (2005-2018) with the revised-methodology
    segment (2019-2024, using the workbook's "2019 Revised" column),
    then the BLS-published 2025 segment -- the same splice Census uses
    for its published SPM statistics.
    """
    doc = _threshold_data()
    try:
        entry = doc["series"][name]
    except KeyError:
        raise ValueError(
            f"Unknown threshold series {name!r}. "
            f"Available: {sorted(doc['series'])}"
        ) from None

    flat: dict[int, dict[str, float]] = {}
    if "segments" in entry:
        # Later segments win overlapping years (2019: revised over
        # published), matching the operative Census series.
        for segment in entry["segments"].values():
            for year_str, tenures in segment["years"].items():
                flat[int(year_str)] = {
                    tenure: measures["threshold"]
                    for tenure, measures in tenures.items()
                }
    else:
        for year_str, tenures in entry["years"].items():
            flat[int(year_str)] = {
                tenure: measures["threshold"]
                for tenure, measures in tenures.items()
            }
    return flat


def _measure_by_year(name: str, measure: str) -> dict[int, dict[str, float]]:
    doc = _threshold_data()
    entry = doc["series"][name]
    out: dict[int, dict[str, float]] = {}
    segments = (
        entry["segments"].values()
        if "segments" in entry
        else [{"years": entry["years"]}]
    )
    for segment in segments:
        for year_str, tenures in segment["years"].items():
            values = {
                tenure: measures[measure]
                for tenure, measures in tenures.items()
                if measure in measures
            }
            if values:
                out[int(year_str)] = values
    return out


#: Full-precision reference-family thresholds from the default source.
HISTORICAL_THRESHOLDS: dict[int, dict[str, float]] = _flatten_series(
    DEFAULT_SERIES
)


LATEST_PUBLISHED_YEAR = max(HISTORICAL_THRESHOLDS)


def _resolve_series(series: Optional[str]) -> dict[int, dict[str, float]]:
    if series is None or series == DEFAULT_SERIES:
        return HISTORICAL_THRESHOLDS
    return _flatten_series(series)


def _segment_for_year(name: str, year: int) -> tuple[str, dict] | None:
    """Return the winning generated segment and its provenance for a year."""
    entry = _threshold_data()["series"][name]
    if "segments" not in entry:
        return None
    winner = None
    for segment_name, segment in entry["segments"].items():
        if str(year) in segment["years"]:
            winner = (segment_name, deepcopy(segment.get("provenance", {})))
    return winner


def get_available_series() -> list[str]:
    """List the threshold series bundled with the package."""
    return sorted(_threshold_data()["series"])


def get_series_provenance(series: Optional[str] = None) -> dict:
    """Return the provenance block for a bundled series."""
    doc = _threshold_data()
    name = series or DEFAULT_SERIES
    try:
        return deepcopy(doc["series"][name].get("provenance", {}))
    except KeyError:
        raise ValueError(
            f"Unknown threshold series {name!r}. "
            f"Available: {sorted(doc['series'])}"
        ) from None


def get_standard_errors(
    year: int, series: Optional[str] = None
) -> dict[str, float]:
    """Published standard errors of the thresholds, where available."""
    by_year = _measure_by_year(series or DEFAULT_SERIES, "standard_error")
    if year not in by_year:
        raise ValueError(
            f"Standard errors not available for {year}. "
            f"Available years: {sorted(by_year)}"
        )
    return by_year[year].copy()


def get_tenure_shares(
    year: int, series: Optional[str] = None
) -> dict[str, float]:
    """Published tenure population shares of the estimation sample.

    Useful for collapsing the three tenure thresholds to a single
    weighted-average threshold.
    """
    by_year = _measure_by_year(series or DEFAULT_SERIES, "tenure_share")
    if year not in by_year:
        raise ValueError(
            f"Tenure shares not available for {year}. "
            f"Available years: {sorted(by_year)}"
        )
    return by_year[year].copy()


def get_available_years(series: Optional[str] = None) -> list[int]:
    """Get list of years with published thresholds."""
    return sorted(_resolve_series(series).keys())


def get_latest_published_year(series: Optional[str] = None) -> int:
    """Get the most recent year with published BLS thresholds."""
    return max(_resolve_series(series))


def get_published_thresholds(
    year: int, series: Optional[str] = None
) -> dict[str, float]:
    """Return a copy of one published source year's thresholds by tenure.

    Only years present in the selected bundled series are supported.
    """
    thresholds = _resolve_series(series)
    if year not in thresholds:
        raise ValueError(
            f"Published thresholds not available for {year}. "
            f"Available years: {sorted(thresholds)}"
        )
    return thresholds[year].copy()


def get_threshold_with_metadata(
    year: int, series: Optional[str] = None
) -> dict:
    """Return published thresholds with their series and segment provenance."""
    series_name = series or DEFAULT_SERIES
    result = {
        "thresholds": get_published_thresholds(year, series=series),
        "year": year,
        "series": series_name,
        "provenance": get_series_provenance(series_name),
        "source": "published",
    }
    segment = _segment_for_year(series_name, year)
    if segment is not None:
        result["segment"], result["segment_provenance"] = segment
    return result
