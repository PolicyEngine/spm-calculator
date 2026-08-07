"""Benchmark the CE-based threshold replication against BLS series.

For each target year 2019-2024, computes base thresholds from CE PUMD
under a grid of methodology variants and compares them against:

- ``census-published-pre-correction``: what BLS/Census published before
  the 2026-07-17 correction (the series containing BLS's code errors).
- ``bls-corrected-2026-07-17``: the corrected series.

The question the grid answers: does our independent replication sit
systematically closer to the corrected series than to the published one
in the years BLS says were affected by its errors (2019-2020)?

Measured answer (docs/bls-2026-correction.md): no — the correction
moved thresholds by at most 1.6% while the replication's noise floor is
2-4%, so neither reference fits systematically better. The exercise
instead surfaced four bugs in our own replication code and confirmed
BLS's 83%→82% re-anchoring preserved series continuity.

Fairness note: the corrected series uses an 82% anchor, the
pre-correction series 83%. Each comparison uses the matching anchor
(82% vs corrected, 83% vs published) so anchor choice cannot manufacture
a fit. In-kind benefit imputations (broadband, LIHEAP, NSLP, WIC,
rental assistance) are not replicated, which biases replicated levels
downward in all years; the diagnostic therefore emphasizes year-to-year
*patterns* — in particular whether the replication residual vs the
published series jumps in the error-affected years and vanishes against
the corrected series.

Usage:
    uv run --with curl-cffi python scripts/benchmark_bls_replication.py

Outputs (git-ignored, summarized into docs/bls-2026-correction.md):
    benchmark_output/replication_results.json
    benchmark_output/replication_results.md
"""

from __future__ import annotations

import json
import warnings
from itertools import product
from pathlib import Path

import pandas as pd

import spm_calculator.fcsuti_cpi as fcsuti_cpi
from spm_calculator.ce_threshold import (
    MEDIAN_SHARE,
    MEDIAN_SHARE_PRE_CORRECTION,
    bls_quarter_window,
    calculate_base_thresholds,
    load_ce_quarter,
)
from spm_calculator.forecast import get_thresholds

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "benchmark_output"
CPI_STORE = OUT_DIR / "bls_cpi_series.json"

TARGET_YEARS = range(2019, 2025)
TENURES = ("owner_with_mortgage", "owner_without_mortgage", "renter")

PRINCIPAL_MODES = ("include", "exclude")
ANNUALIZATION_MODES = ("quarter4", "pqcq2")

CPI_RANGE = (2005, 2025)


def install_cpi_disk_cache() -> None:
    """Serve BLS CPI series from a one-shot disk cache.

    The unauthenticated BLS API allows 25 queries/IP/day; the variant
    grid would otherwise re-fetch each component series once per
    (target-year, weights) combination. Fetch each series once across
    a wide year range, persist, and serve slices from disk.
    """
    OUT_DIR.mkdir(exist_ok=True)
    store: dict[str, dict[str, float]] = (
        json.loads(CPI_STORE.read_text()) if CPI_STORE.exists() else {}
    )
    original = fcsuti_cpi.fetch_bls_cpi_series

    def cached(series_id, start_year=2010, end_year=2024, **kwargs):
        if series_id not in store:
            series = original(
                series_id,
                start_year=CPI_RANGE[0],
                end_year=CPI_RANGE[1],
                **kwargs,
            )
            store[series_id] = {str(y): v for y, v in series.items()}
            CPI_STORE.write_text(json.dumps(store, indent=1))
        series = pd.Series(
            {int(y): v for y, v in store[series_id].items()},
            name=series_id,
        ).sort_index()
        return series[
            (series.index >= start_year) & (series.index <= end_year)
        ]

    fcsuti_cpi.fetch_bls_cpi_series = cached


def load_quarter_store() -> dict[tuple[int, int], pd.DataFrame]:
    """Load every CE quarter needed by any target-year window, once."""
    needed: set[tuple[int, int]] = set()
    for target in TARGET_YEARS:
        needed.update(bls_quarter_window(target))
    store: dict[tuple[int, int], pd.DataFrame] = {}
    for year, quarter in sorted(needed):
        store[(year, quarter)] = load_ce_quarter(year, quarter)
        print(f"loaded {year}Q{quarter}: {len(store[(year, quarter)]):,} CUs")
    return store


def reference_series(year: int) -> dict[str, dict[str, float]]:
    return {
        "published": get_thresholds(
            year, series="census-published-pre-correction"
        ),
        "corrected": get_thresholds(year, allow_forecast=False),
    }


def pct_dev(calculated: dict, reference: dict) -> dict[str, float]:
    return {
        tenure: calculated[tenure] / reference[tenure] - 1.0
        for tenure in TENURES
    }


def main() -> None:
    install_cpi_disk_cache()
    store = load_quarter_store()

    results = []
    for target in TARGET_YEARS:
        window = bls_quarter_window(target)
        ce = pd.concat([store[q] for q in window], ignore_index=True)
        refs = reference_series(target)
        for principal, annualization in product(
            PRINCIPAL_MODES, ANNUALIZATION_MODES
        ):
            for anchor_name, anchor in (
                ("82", MEDIAN_SHARE),
                ("83", MEDIAN_SHARE_PRE_CORRECTION),
            ):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    calc = calculate_base_thresholds(
                        target_year=target,
                        ce=ce,
                        median_share=anchor,
                        mortgage_principal=principal,
                        annualization=annualization,
                        use_published_fallback=False,
                    )
                row = {
                    "target_year": target,
                    "principal": principal,
                    "annualization": annualization,
                    "anchor": anchor_name,
                    "calculated": calc,
                    "dev_vs_published": pct_dev(calc, refs["published"]),
                    "dev_vs_corrected": pct_dev(calc, refs["corrected"]),
                }
                results.append(row)
                mean_pub = (
                    sum(abs(v) for v in row["dev_vs_published"].values()) / 3
                )
                mean_cor = (
                    sum(abs(v) for v in row["dev_vs_corrected"].values()) / 3
                )
                print(
                    f"{target} {principal:7s} {annualization:5s} "
                    f"a{anchor_name}: "
                    f"|dev| pub {mean_pub:6.2%}  cor {mean_cor:6.2%}"
                )

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "replication_results.json").write_text(
        json.dumps(results, indent=1)
    )

    # Matched-anchor comparison: 83% variants judge fit to the published
    # (83%-anchored) series, 82% variants to the corrected (82%) series.
    lines = [
        "# CE replication vs BLS series",
        "",
        "Mean absolute deviation across the three tenure thresholds.",
        "Anchor matched to each reference series (83% vs published,",
        "82% vs corrected).",
        "",
        "| Variant | Year | vs published (83%) | vs corrected (82%) |",
        "|---|---|---|---|",
    ]
    for principal, annualization in product(
        PRINCIPAL_MODES, ANNUALIZATION_MODES
    ):
        for target in TARGET_YEARS:
            pub_row = next(
                r
                for r in results
                if r["target_year"] == target
                and r["principal"] == principal
                and r["annualization"] == annualization
                and r["anchor"] == "83"
            )
            cor_row = next(
                r
                for r in results
                if r["target_year"] == target
                and r["principal"] == principal
                and r["annualization"] == annualization
                and r["anchor"] == "82"
            )
            mean_pub = (
                sum(abs(v) for v in pub_row["dev_vs_published"].values()) / 3
            )
            mean_cor = (
                sum(abs(v) for v in cor_row["dev_vs_corrected"].values()) / 3
            )
            lines.append(
                f"| {principal}/{annualization} | {target} "
                f"| {mean_pub:.2%} | {mean_cor:.2%} |"
            )
    (OUT_DIR / "replication_results.md").write_text("\n".join(lines) + "\n")
    print(f"\nWrote {OUT_DIR}/replication_results.{{json,md}}")


if __name__ == "__main__":
    main()
