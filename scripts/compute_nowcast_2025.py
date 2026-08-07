"""Compute the packaged 2025 threshold nowcast.

Method (committed via scripts/backtest_threshold_projection.py — mean
absolute error 0.76%/yr over 2020-2024, vs 2.23% for All-Items CPI-U
aging; the repaired backtest ranks the replication ratio alone first
at 0.41%, and the blend stays the committed primary): apply to the
corrected 2024 base, per tenure, the 50/50 blend of

- the realized FCSUti-composite CPI ratio (static package weights,
  renormalized over available components; 2025 annual averages are
  11-month means because BLS canceled the October 2025 CPI release
  during the federal shutdown), and
- the CE replication growth ratio: replicated 2025 / replicated 2024
  thresholds, both computed with identical code over their BLS windows
  (2020Q2-2025Q1 and 2019Q2-2024Q1) so level biases largely cancel.

Writes spm_calculator/data/nowcast/nowcast_2025.json.

Usage:
    uv run --with curl-cffi python scripts/compute_nowcast_2025.py
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pandas as pd

import spm_calculator.fcsuti_cpi as fcsuti_cpi
from spm_calculator.ce_threshold import (
    bls_quarter_window,
    calculate_base_thresholds,
    load_ce_quarters,
)
from spm_calculator.fcsuti_cpi import CPI_SERIES, FCSUTI_WEIGHTS
from spm_calculator.forecast import get_thresholds

REPO = Path(__file__).resolve().parent.parent
CPI_STORE = REPO / "benchmark_output" / "bls_cpi_series.json"
OUT = REPO / "spm_calculator" / "data" / "nowcast" / "nowcast_2025.json"

TENURES = ("owner_with_mortgage", "owner_without_mortgage", "renter")


def install_cpi_disk_cache() -> None:
    store = json.loads(CPI_STORE.read_text())
    original = fcsuti_cpi.fetch_bls_cpi_series

    def cached(series_id, start_year=2010, end_year=2024, **kwargs):
        if series_id not in store:
            return original(series_id, start_year, end_year, **kwargs)
        series = pd.Series(
            {int(y): v for y, v in store[series_id].items()},
            name=series_id,
        ).sort_index()
        return series[
            (series.index >= start_year) & (series.index <= end_year)
        ]

    fcsuti_cpi.fetch_bls_cpi_series = cached


def price_ratio(store: dict, year: int, base_year: int) -> float:
    """Composite ratio with each component rebased to base_year = 100
    before weighting (raw CPI levels have different reference bases;
    summing them directly distorts the effective weights — caught by
    cross-model review 2026-07-18)."""

    def composite(y: int) -> float:
        available = {
            c: w
            for c, w in FCSUTI_WEIGHTS.items()
            if c in CPI_SERIES
            and str(y) in store.get(CPI_SERIES[c], {})
            and str(base_year) in store.get(CPI_SERIES[c], {})
        }
        return sum(
            w
            * store[CPI_SERIES[c]][str(y)]
            / store[CPI_SERIES[c]][str(base_year)]
            for c, w in available.items()
        ) / sum(available.values())

    return composite(year) / composite(base_year)


def main() -> None:
    install_cpi_disk_cache()
    store = json.loads(CPI_STORE.read_text())

    replicated = {}
    for target in (2024, 2025):
        ce = load_ce_quarters(bls_quarter_window(target))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            replicated[target] = calculate_base_thresholds(
                target_year=target,
                ce=ce,
                use_published_fallback=False,
            )
        print(
            f"replicated {target}:",
            {k: round(v) for k, v in replicated[target].items()},
        )

    p_ratio = price_ratio(store, 2025, 2024)
    print(f"FCSUti price ratio 2025/2024: {p_ratio:.5f}")

    base = get_thresholds(2024, allow_forecast=False)
    values = {}
    components = {}
    for tenure in TENURES:
        r_ratio = replicated[2025][tenure] / replicated[2024][tenure]
        blend = (p_ratio + r_ratio) / 2
        values[tenure] = base[tenure] * blend
        components[tenure] = {
            "replication_ratio": r_ratio,
            "price_ratio": p_ratio,
            "blend_ratio": blend,
        }
        print(
            f"{tenure:24s} repl {r_ratio:.5f}  blend {blend:.5f}  "
            f"nowcast ${values[tenure]:,.2f}"
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "generated_by": "scripts/compute_nowcast_2025.py",
                "label": (
                    "PolicyEngine nowcast of 2025 SPM thresholds — "
                    "NOT a BLS publication"
                ),
                "method": (
                    "50/50 blend of realized FCSUti-composite CPI "
                    "aging and CE replication growth ratio, applied "
                    "to the corrected 2024 base. Committed via the "
                    "2020-2024 backtest (see "
                    "docs/bls-2026-correction.md): mean absolute "
                    "error 0.76%/yr vs 2.23% for All-Items CPI-U "
                    "aging after the 2026-07-18 composite repair, "
                    "which ranks the replication ratio alone first "
                    "(0.41%); the blend remains the committed "
                    "primary."
                ),
                "caveats": [
                    "BLS publishes actual 2025 thresholds ~September "
                    "2026; this nowcast is superseded the day they do.",
                    "2025 CPI annual averages are 11-month means "
                    "(October 2025 release canceled during the federal "
                    "shutdown).",
                    "Both price rules ran low in nearly every "
                    "backtest year (real FCSUti consumption growth "
                    "and in-kind benefit changes are not fully "
                    "captured by prices); the replication ratio is "
                    "near-unbiased (+0.1%/yr signed mean), and the "
                    "blend's annual signed errors ranged -0.1% to "
                    "-1.4%.",
                ],
                "base_year": 2024,
                "base_series": "bls-corrected-2026-07-17",
                "values": values,
                "components": components,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
