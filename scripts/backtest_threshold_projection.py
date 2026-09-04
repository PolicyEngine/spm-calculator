"""Backtest threshold-projection rules against the corrected series.

For each target year T in 2020-2024, stand at the corrected T-1 base
and project T four ways:

- ``cpi_u``: All-Items CPI-U annual-average ratio (what policyengine-us
  aging does today).
- ``fcsuti_cpi``: composite CPI ratio using the package's static FCSUti
  component weights (fixes the basket mismatch; shelter-heavy).
- ``replication_ratio``: replicated_T / replicated_{T-1} from the CE
  replication (include/quarter4 variant; the 82/83 anchor cancels in
  the ratio), applied to the official T-1 base.
- ``blend``: the 50/50 arithmetic mean of the FCSUti CPI factor and
  tenure-specific replication factor, applied to the official T-1 base.

Score: percent error vs the corrected actual, per tenure.

Both CPI rules use *realized* CPI — information not available when a
real projection is made — while the replication ratio uses CE data
that genuinely exists by the time BLS's own threshold for T is still
unpublished. The CPI rules therefore get a hindsight advantage; if the
replication ratio still wins, the conclusion is conservative.

Inputs (produced by scripts/benchmark_bls_replication.py):
    benchmark_output/replication_results.json

CPI inputs default to the tracked package store:
    spm_calculator/data/bls/cpi_annual.json

Pass ``--use-benchmark-cpi-store`` to explicitly use the older
``benchmark_output/bls_cpi_series.json`` diagnostic cache instead.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from spm_calculator.fcsuti_cpi import CPI_SERIES, FCSUTI_WEIGHTS
from spm_calculator.forecast import get_thresholds

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "benchmark_output"
TRACKED_CPI_STORE = (
    REPO / "spm_calculator" / "data" / "bls" / "cpi_annual.json"
)
BENCHMARK_CPI_STORE = OUT_DIR / "bls_cpi_series.json"
REPLICATION_RESULTS = OUT_DIR / "replication_results.json"
TRACKED_RESULTS = (
    REPO / "spm_calculator" / "data" / "nowcast" / "backtest_2020_2024.json"
)
BENCHMARK_RESULTS = OUT_DIR / "projection_backtest.json"

TENURES = ("owner_with_mortgage", "owner_without_mortgage", "renter")
TARGETS = range(2020, 2025)


def load_cpi_store(*, use_benchmark_store: bool = False) -> tuple[dict, Path]:
    """Return CPI series and their selected on-disk source."""
    cpi_path = (
        BENCHMARK_CPI_STORE if use_benchmark_store else TRACKED_CPI_STORE
    )
    cpi_doc = json.loads(cpi_path.read_text())
    cpi = cpi_doc if use_benchmark_store else cpi_doc["series"]
    return cpi, cpi_path


def load_inputs(*, use_benchmark_store: bool = False):
    results = json.loads(REPLICATION_RESULTS.read_text())
    replicated = {
        r["target_year"]: r["calculated"]
        for r in results
        if r["principal"] == "include"
        and r["annualization"] == "quarter4"
        and r["anchor"] == "82"
    }
    cpi, _ = load_cpi_store(use_benchmark_store=use_benchmark_store)
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


def calculate_backtest(replicated: dict, cpi: dict) -> tuple[list, dict]:
    """Execute all four projection rules and return rows plus MAEs."""
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
        projections["blend"] = {
            t: base[t]
            * (
                factors["fcsuti_cpi"]
                + replicated[target][t] / replicated[target - 1][t]
            )
            / 2
            for t in TENURES
        }

        for rule, projected in projections.items():
            errors = {t: projected[t] / actual[t] - 1.0 for t in TENURES}
            mean_abs = sum(abs(v) for v in errors.values()) / len(TENURES)
            rows.append(
                {
                    "target": target,
                    "rule": rule,
                    "errors": errors,
                    "mean_absolute_error": mean_abs,
                }
            )

    grouped: dict[str, list[float]] = {}
    for row in rows:
        grouped.setdefault(row["rule"], []).append(row["mean_absolute_error"])
    summary = {
        rule: {
            "mean_absolute_error": sum(values) / len(values),
            "mean_absolute_error_percent": 100 * sum(values) / len(values),
        }
        for rule, values in grouped.items()
    }
    return rows, summary


def build_results_document(
    replicated: dict,
    cpi: dict,
    cpi_path: Path,
) -> dict:
    """Build the tracked, provenance-bearing backtest result."""
    rows, summary = calculate_backtest(replicated, cpi)
    cpi_doc = json.loads(cpi_path.read_text())
    cpi_metadata = (
        {
            "generated_by": cpi_doc["generated_by"],
            "retrieved": cpi_doc["retrieved"],
            "note": cpi_doc["note"],
        }
        if "series" in cpi_doc
        else {"note": "Explicitly selected git-ignored benchmark cache."}
    )
    return {
        "generated_by": "scripts/backtest_threshold_projection.py",
        "description": (
            "Projection errors against corrected BLS SPM thresholds, "
            "standing at each prior-year corrected base."
        ),
        "target_years": list(TARGETS),
        "tenures": list(TENURES),
        "score": (
            "Mean absolute percentage error across three tenures, then "
            "equally across target years 2020-2024."
        ),
        "rules": {
            "cpi_u": "Prior-year base aged by realized All-Items CPI-U.",
            "fcsuti_cpi": (
                "Prior-year base aged by the realized static-weight "
                "FCSUti CPI composite."
            ),
            "replication_ratio": (
                "Prior-year base aged by the tenure-specific CE "
                "replicated-threshold growth ratio."
            ),
            "blend": (
                "Prior-year base aged by a 50/50 arithmetic blend of "
                "the FCSUti CPI and tenure-specific replication factors."
            ),
        },
        "provenance": {
            "thresholds": {
                "accessor": (
                    "spm_calculator.forecast.get_thresholds"
                    "(year, allow_forecast=False)"
                ),
                "series": "bls-corrected-2026-07-17",
                "years": [2019, 2024],
            },
            "cpi": {
                "path": str(cpi_path.relative_to(REPO)),
                "rebase_year": REBASE_YEAR,
                "component_series": {
                    component: CPI_SERIES[component]
                    for component in (*FCSUTI_WEIGHTS, "all_items")
                },
                **cpi_metadata,
            },
            "replication": {
                "source": "scripts/benchmark_bls_replication.py",
                "path": str(REPLICATION_RESULTS.relative_to(REPO)),
                "selection": {
                    "mortgage_principal": "include",
                    "annualization": "quarter4",
                    "anchor_percent": 82,
                },
                "selected_thresholds": {
                    str(year): replicated[year] for year in range(2019, 2025)
                },
            },
        },
        "annual_results": rows,
        "summary": summary,
    }


def render_markdown(doc: dict) -> str:
    """Render the human-readable benchmark table from the JSON result."""
    rows = doc["annual_results"]

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
    for row in rows:
        errs = row["errors"]
        mean_abs = row["mean_absolute_error"]
        err_text = " / ".join(f"{errs[t]:+.2%}" for t in TENURES)
        lines.append(
            f"| {row['target']} | {row['rule']} | {err_text} "
            f"| {mean_abs:.2%} |"
        )

    lines += ["", "| Rule | Mean abs error, 2020-2024 |", "|---|---|"]
    for rule, result in doc["summary"].items():
        overall = result["mean_absolute_error"]
        lines.append(f"| {rule} | {overall:.2%} |")
    return "\n".join(lines) + "\n"


def main(*, use_benchmark_store: bool = False) -> None:
    replicated, cpi = load_inputs(use_benchmark_store=use_benchmark_store)
    _, cpi_path = load_cpi_store(use_benchmark_store=use_benchmark_store)
    doc = build_results_document(replicated, cpi, cpi_path)

    for row in doc["annual_results"]:
        err_text = " / ".join(
            f"{row['errors'][tenure]:+.2%}" for tenure in TENURES
        )
        print(
            f"{row['target']} {row['rule']:18s} {err_text}  "
            f"mean|e| {row['mean_absolute_error']:.2%}"
        )
    print()
    for rule, result in doc["summary"].items():
        print(f"OVERALL {rule:18s} {result['mean_absolute_error']:.2%}")

    OUT_DIR.mkdir(exist_ok=True)
    markdown_path = OUT_DIR / "projection_backtest.md"
    markdown_path.write_text(render_markdown(doc))
    results_path = (
        BENCHMARK_RESULTS if use_benchmark_store else TRACKED_RESULTS
    )
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"\nWrote {markdown_path}")
    print(f"Wrote {results_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--use-benchmark-cpi-store",
        action="store_true",
        help=(
            "explicitly use benchmark_output/bls_cpi_series.json instead "
            "of the tracked packaged CPI store"
        ),
    )
    args = parser.parse_args()
    main(use_benchmark_store=args.use_benchmark_cpi_store)
