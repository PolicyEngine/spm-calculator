"""Backtest threshold-projection rules against the corrected series.

For each target year T in 2020-2024, stand at the corrected T-1 base
and project T three ways:

- ``cpi_u``: All-Items CPI-U annual-average ratio (what policyengine-us
  aging does today).
- ``fcsuti_cpi``: composite CPI ratio using the package's static FCSUti
  component weights (fixes the basket mismatch; shelter-heavy).
- ``replication_ratio``: replicated_T / replicated_{T-1} from the CE
  replication (include/quarter4 variant; the 82/83 anchor cancels in
  the ratio), applied to the official T-1 base.

Score: percent error vs the corrected actual, per tenure.

Both CPI rules use *realized* CPI — information not available when a
real projection is made — while the replication ratio uses CE data
that genuinely exists by the time BLS's own threshold for T is still
unpublished. The CPI rules therefore get a hindsight advantage; if the
replication ratio still wins, the conclusion is conservative.

Inputs (produced by scripts/benchmark_bls_replication.py):
    benchmark_output/replication_results.json
    benchmark_output/bls_cpi_series.json
"""

from __future__ import annotations

import json
from pathlib import Path

from spm_calculator.fcsuti_cpi import CPI_SERIES, FCSUTI_WEIGHTS
from spm_calculator.forecast import get_thresholds

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "benchmark_output"

TENURES = ("owner_with_mortgage", "owner_without_mortgage", "renter")
TARGETS = range(2020, 2025)


def load_inputs():
    results = json.loads((OUT_DIR / "replication_results.json").read_text())
    replicated = {
        r["target_year"]: r["calculated"]
        for r in results
        if r["principal"] == "include"
        and r["annualization"] == "quarter4"
        and r["anchor"] == "82"
    }
    cpi = json.loads((OUT_DIR / "bls_cpi_series.json").read_text())
    return replicated, cpi


def annual(cpi: dict, series_key: str, year: int) -> float:
    return cpi[CPI_SERIES[series_key]][str(year)]


REBASE_YEAR = 2019


def fcsuti_composite(cpi: dict, year: int) -> float:
    """Static-weight composite over the components in the store.

    Each component is rebased to REBASE_YEAR = 100 before weighting —
    raw CPI levels carry different reference bases, and summing them
    directly weights components by level as well as share (a
    construction error caught by cross-model review 2026-07-18).
    Renormalizes over available components (mirrors get_fcsuti_cpi).
    """
    available = {
        c: w
        for c, w in FCSUTI_WEIGHTS.items()
        if c in CPI_SERIES
        and str(year) in cpi.get(CPI_SERIES[c], {})
        and str(REBASE_YEAR) in cpi.get(CPI_SERIES[c], {})
    }
    total_weight = sum(available.values())
    return (
        sum(
            w * annual(cpi, c, year) / annual(cpi, c, REBASE_YEAR) * 100
            for c, w in available.items()
        )
        / total_weight
    )


def main() -> None:
    replicated, cpi = load_inputs()

    rows = []
    for target in TARGETS:
        base = get_thresholds(target - 1, allow_forecast=False)
        actual = get_thresholds(target, allow_forecast=False)

        factors = {
            "cpi_u": annual(cpi, "all_items", target)
            / annual(cpi, "all_items", target - 1),
            "fcsuti_cpi": fcsuti_composite(cpi, target)
            / fcsuti_composite(cpi, target - 1),
        }
        projections = {
            rule: {t: base[t] * f for t in TENURES}
            for rule, f in factors.items()
        }
        projections["replication_ratio"] = {
            t: base[t] * replicated[target][t] / replicated[target - 1][t]
            for t in TENURES
        }

        for rule, projected in projections.items():
            errors = {t: projected[t] / actual[t] - 1.0 for t in TENURES}
            rows.append({"target": target, "rule": rule, "errors": errors})

    lines = [
        "# Threshold projection backtest",
        "",
        "Percent error vs corrected actual (owner w/ mortgage / owner",
        "w/o mortgage / renter), projecting each year from the prior",
        "corrected base.",
        "",
        "| Year | Rule | Errors | Mean abs |",
        "|---|---|---|---|",
    ]
    summary: dict[str, list[float]] = {}
    for row in rows:
        errs = row["errors"]
        mean_abs = sum(abs(v) for v in errs.values()) / 3
        summary.setdefault(row["rule"], []).append(mean_abs)
        err_text = " / ".join(f"{errs[t]:+.2%}" for t in TENURES)
        lines.append(
            f"| {row['target']} | {row['rule']} | {err_text} "
            f"| {mean_abs:.2%} |"
        )
        print(
            f"{row['target']} {row['rule']:18s} {err_text}  "
            f"mean|e| {mean_abs:.2%}"
        )

    lines += ["", "| Rule | Mean abs error, 2020-2024 |", "|---|---|"]
    print()
    for rule, vals in summary.items():
        overall = sum(vals) / len(vals)
        lines.append(f"| {rule} | {overall:.2%} |")
        print(f"OVERALL {rule:18s} {overall:.2%}")

    (OUT_DIR / "projection_backtest.md").write_text("\n".join(lines) + "\n")
    print(f"\nWrote {OUT_DIR}/projection_backtest.md")


if __name__ == "__main__":
    main()
