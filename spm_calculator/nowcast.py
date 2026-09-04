"""Consumption-based threshold nowcasts retained for evaluation.

BLS does not age thresholds by a price index — each year is re-estimated
from the rolling five-year CE window, so the published series moves with
consumption as well as prices. Pure CPI aging therefore under-projects
whenever real FCSUti spending grows or the shelter-heavy FCSUti basket
outruns headline CPI (it missed by 2.2%/yr on average over 2020-2024).

Before BLS published its 2025 thresholds, a nowcast used realized CE and
CPI data instead of assumptions. The packaged values remain an immutable
historical commitment for evaluating the method, but callers should now
use :func:`spm_calculator.forecast.get_thresholds` for 2025 calculations.
The packaged method -- selected by backtest over 2020-2024
(``scripts/backtest_threshold_projection.py``, results in
``docs/bls-2026-correction.md``) -- blends two independent signals 50/50
and applies them to the corrected published base:

- the realized FCSUti-composite CPI ratio, and
- the CE replication growth ratio (replicated year-T over year-T-1
  thresholds from identical code, so replication level biases largely
  cancel).

Backtest mean absolute error (post composite repair, 2026-07-18):
0.76%/yr (blend) vs 1.57% (FCSUti CPI alone), 0.41% (replication
ratio alone), 2.23% (All-Items CPI-U aging, the
``forecast_thresholds`` behavior). The repaired backtest ranks the
replication ratio first; the blend remains the committed primary
because it was selected before the repair and re-selecting on a
second look at five backtest years would be selection on noise.

Nowcasts are PolicyEngine model output, NOT BLS publications. The 2025
artifact records its method, components, and caveats and is superseded
by BLS's published 2025 thresholds.
"""

import json
import warnings
from functools import lru_cache
from importlib import resources

NOWCAST_YEARS = (2025,)

SUPERSEDED_BY = {
    2025: {
        "source": "BLS published 2025 SPM thresholds",
        "series": "bls-published-2025",
        "source_url": "https://www.bls.gov/pir/spm/spm_thresholds_2025.htm",
        "accessor": "spm_calculator.forecast.get_thresholds(2025)",
    }
}

NOWCAST_SUPERSEDED_WARNING = (
    "BLS has published the actual 2025 SPM thresholds; "
    "nowcast_thresholds(2025) returns the committed historical nowcast "
    "for evaluation only. Use get_thresholds(2025) for published BLS values."
)


@lru_cache(maxsize=8)
def _nowcast_doc(year: int) -> dict:
    ref = resources.files("spm_calculator").joinpath(
        f"data/nowcast/nowcast_{year}.json"
    )
    try:
        return json.loads(ref.read_text())
    except FileNotFoundError:
        raise ValueError(
            f"No packaged nowcast for {year}. Available: {list(NOWCAST_YEARS)}"
        ) from None


def get_nowcast_years() -> list[int]:
    """Years with a packaged nowcast."""
    return list(NOWCAST_YEARS)


def nowcast_thresholds(year: int = 2025) -> dict[str, float]:
    """Nowcasted base thresholds by tenure for ``year``.

    Returns the packaged consumption-based nowcast (see module
    docstring for method and measured accuracy). When BLS has published
    the requested year, this emits a warning because these values exist
    only as a historical forecasting commitment. Use
    :func:`spm_calculator.forecast.get_thresholds` for published years;
    for years past the CE data horizon use
    :func:`spm_calculator.forecast.forecast_thresholds` (price-only).
    """
    doc = _nowcast_doc(year)
    if year in SUPERSEDED_BY:
        warnings.warn(
            NOWCAST_SUPERSEDED_WARNING,
            UserWarning,
            stacklevel=2,
        )
    return dict(doc["values"])


def nowcast_with_metadata(year: int = 2025) -> dict:
    """Full packaged nowcast document: values, per-tenure components
    (price ratio, replication ratio, blend), method, and caveats."""
    doc = json.loads(json.dumps(_nowcast_doc(year)))
    if year in SUPERSEDED_BY:
        doc["superseded_by"] = {
            **SUPERSEDED_BY[year],
            **doc.get("superseded_by", {}),
        }
    return doc


def _clear_cache_for_tests() -> None:
    _nowcast_doc.cache_clear()
