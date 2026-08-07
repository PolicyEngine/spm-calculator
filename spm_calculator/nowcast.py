"""Consumption-based threshold nowcasts for years BLS has not published.

BLS does not age thresholds by a price index — each year is re-estimated
from the rolling five-year CE window, so the published series moves with
consumption as well as prices. Pure CPI aging therefore under-projects
whenever real FCSUti spending grows or the shelter-heavy FCSUti basket
outruns headline CPI (it missed by 2.2%/yr on average over 2020-2024).

For a year whose CE window and CPI are already published but whose BLS
thresholds are not (2025, as of mid-2026), a nowcast can use realized
data instead of assumptions. The packaged method — selected by backtest
over 2020-2024 (``scripts/backtest_threshold_projection.py``, results
in docs/bls-2026-correction.md) — blends two independent signals 50/50
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

Nowcasts are PolicyEngine model output, NOT BLS publications; each
packaged nowcast records its method, components, and caveats, and is
superseded the day BLS publishes the actual year.
"""

import json
from functools import lru_cache
from importlib import resources

NOWCAST_YEARS = (2025,)


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
    docstring for method and measured accuracy). For published years
    use :func:`spm_calculator.forecast.get_thresholds`; for years past
    the CE data horizon use
    :func:`spm_calculator.forecast.forecast_thresholds` (price-only).
    """
    return dict(_nowcast_doc(year)["values"])


def nowcast_with_metadata(year: int = 2025) -> dict:
    """Full packaged nowcast document: values, per-tenure components
    (price ratio, replication ratio, blend), method, and caveats."""
    return json.loads(json.dumps(_nowcast_doc(year)))


def _clear_cache_for_tests() -> None:
    _nowcast_doc.cache_clear()
