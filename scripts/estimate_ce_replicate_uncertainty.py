"""Replicate-weight standard errors for the 2019-2025 CE replication.

Reruns the out-of-pocket replication and the replication with the in-kind
stage under each of the CE's 44 replicate weights, for every target year
from 2019 to 2025, with the package's composite CPI and with BLS's
published FCSUti index (``spm_calculator.ce_replicates``). Each implicate's
imputed amounts stay as the full-sample imputation drew them. The receipt
reports standard errors for:

- threshold levels by tenure, beside BLS's published standard errors;
- 2022-2025 and 2024-2025 growth by tenure, with and without the stage,
  and the stage's change to growth;
- the band's imputed benefits per consumer unit, rental assistance per
  renter and school lunch, and their 2022-2025 rise.

The full-sample runs must reproduce
``spm_calculator/data/current/ce_inkind_replication_2019_2025.json`` and
the band amounts in
``spm_calculator/data/current/ce_inkind_bls_components_2019_2025.json``.

No network requests are made.

Run: uv run --no-sync python scripts/estimate_ce_replicate_uncertainty.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
from scipy import stats

from scripts.replicate_ce_inkind import IN_KIND_COLUMNS, KEEP
from spm_calculator.ce_bls_shares import BandComponents
from spm_calculator.ce_decomposition import BLS_FCSUTI_INDEX
from spm_calculator.ce_inkind import (
    InKindConfig,
    ce_unit_covariates,
    impute_in_kind,
    load_ce_unit_inputs,
)
from spm_calculator.ce_replicates import (
    IDENTITY_TOLERANCE,
    REPLICATES,
    STANDARD_BRR,
    STRATA,
    check_standard_brr,
    combine_replicated,
    replicate_estimates,
    replicate_variance,
    replicate_weight_matrix,
)
from spm_calculator.ce_threshold import (
    TENURES,
    bls_quarter_window,
    load_ce_quarter,
)
from spm_calculator.cps_asec import load_household_donors
from spm_calculator.fcsuti_cpi import CPI_SERIES
from spm_calculator.published_thresholds import (
    get_published_thresholds,
    get_standard_errors,
)

ROOT = Path(__file__).resolve().parent.parent
CURRENT = ROOT / "spm_calculator/data/current"
RECEIPT = CURRENT / "ce_replicate_uncertainty_2019_2025.json"
REPLICATION_RECEIPT = CURRENT / "ce_inkind_replication_2019_2025.json"
COMPONENTS_RECEIPT = CURRENT / "ce_inkind_bls_components_2019_2025.json"
TARGETS = tuple(range(2019, 2026))
#: 2022-2025, then every year over the year before.
GROWTH_SPANS = ((2022, 2025),) + tuple((t - 1, t) for t in TARGETS[1:])
AMOUNT_SPAN = (2022, 2025)
#: Band amounts the components receipt reports per implicate.
AMOUNTS = ("imputed_total", "rental_assistance_per_renter", "school_lunch")
#: The components receipt's per-implicate field for each amount.
AMOUNT_FIELDS = {name: f"{name}_by_implicate" for name in AMOUNTS}
#: Run name -> deflator, as in scripts/compare_ce_inkind_bls_shares.py.
RUNS = ("package", "fcsuti")
#: Largest relative gap from the replication receipt's thresholds.
REPLICATION_TOLERANCE = 1e-12
#: Largest relative gap from the components receipt's band amounts.
AMOUNT_TOLERANCE = 1e-12
CODE_PATHS = (
    "spm_calculator/ce_replicates.py",
    "spm_calculator/ce_threshold.py",
    "spm_calculator/ce_inkind.py",
    "spm_calculator/ce_inkind_stage.py",
    "spm_calculator/ce_bls_shares.py",
    "spm_calculator/ce_decomposition.py",
    "spm_calculator/cps_asec.py",
    "spm_calculator/fcsuti_cpi.py",
    "spm_calculator/equivalence_scale.py",
    "spm_calculator/published_thresholds.py",
    "scripts/replicate_ce_inkind.py",
    "scripts/estimate_ce_replicate_uncertainty.py",
)
METHOD = {
    "variance": "balanced repeated replication, standard form",
    "formula": "V = sum_r (theta_r - theta)^2 / (R (1 - k)^2)",
    "replicates": REPLICATES,
    "fay_coefficient": STANDARD_BRR,
    "strata": STRATA,
    "complete_data_df": STRATA,
    "combining": (
        "Rubin's rules: T = U + (1 + 1/M) B, with U the mean of the "
        "implicates' replicate variances and B the variance of their "
        "full-sample estimates (divisor M - 1)"
    ),
    "df": (
        "Barnard and Rubin (1999): 1 / (1 / nu_m + 1 / nu_obs), with "
        "nu_m = (M - 1) / lambda^2, nu_obs = nu_com (nu_com + 1) "
        "(1 - lambda) / (nu_com + 3), lambda = (1 + 1/M) B / T and "
        "nu_com = 43; figures without the stage use 43"
    ),
    "interval": "estimate +/- t_975 * standard_error, t on df",
    "sources": {
        "brr": "https://www.bls.gov/opub/hom/cex/calculation.htm",
        "standard_errors": "https://www.bls.gov/cex/ce-standarderrors.htm",
        "rubin": "Rubin, D. B. (1987). Multiple Imputation for Nonresponse in Surveys. Wiley.",
        "barnard_rubin": "Barnard, J. and Rubin, D. B. (1999). Small-sample degrees of freedom with multiple imputation. Biometrika 86(4): 948-955.",
    },
    "replicated": [
        "the sample: records whose replicate weight is zero drop out",
        "the package deflator's CPI component weights, which come from CE spending",
        "normalization to the reference family",
        "the 47th-53rd percentile band and the band means",
    ],
    "held_fixed": [
        "each implicate's imputed in-kind amounts, as the full-sample imputation drew them",
        "the CPS ASEC participation and amount models and the CE rent model, fit once with full-sample weights; each implicate draws their parameters from the inverse of the weighted information matrix, with weights scaled to mean one",
        "the CPI series and BLS's FCSUti index",
    ],
}
LIMITATIONS = [
    "Each implicate's imputed amounts stay fixed across replicates, so the replicates leave out the sampling variability of the CE rent model and of the CPS ASEC samples behind the participation models",
    "Implicates draw model parameters from covariances that ignore the CPS ASEC and CE designs' strata and clusters",
    "In 2015Q2 and 2017Q1, most consumer units interviewed in both that quarter and the one before changed their pattern of positive and zero replicate weights, so under one replicate number a unit's interviews on either side can fall in different half samples; the 2019-2021 windows span one or both quarters, and their replicates can miss part of the correlation between a unit's interviews",
    "The FCSUti-index run deflates every component by BLS's published index, so its price factors do not vary across replicates",
    "BLS's threshold workbooks do not say how BLS computes its published standard errors",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def growth(base: float, target: float) -> float:
    return 100 * (target / base - 1)


def amounts(band: BandComponents) -> dict[str, float]:
    """The band amounts the components receipt reports."""
    return {
        "imputed_total": band.imputed_total,
        "rental_assistance_per_renter": band.by_tenure["renter"][
            "rental_assistance"
        ],
        "school_lunch": band.pooled["nslp"],
    }


def t_975(df: float) -> float:
    return float(stats.t.ppf(0.975, df))


def brr_block(values: list[float]) -> dict:
    """BRR standard error; ``values[0]`` is the full-sample estimate."""
    variance = replicate_variance(values[0], values[1:])
    return {
        "estimate": values[0],
        "standard_error": math.sqrt(variance),
        "variance": variance,
        "df": STRATA,
        "t_975": t_975(STRATA),
    }


def rubin_block(by_implicate: list[list[float]]) -> dict:
    """Rubin's rules; ``by_implicate[m][0]`` is implicate m's full sample."""
    block = combine_replicated(by_implicate).to_dict()
    block["by_implicate"] = [values[0] for values in by_implicate]
    block["t_975"] = t_975(block["df"])
    return block


def half_sample_changes(records: pd.DataFrame) -> dict:
    """How often a unit's replicate pattern changes between interviews.

    ``records`` holds one row per interview: CUID, a quarter index and the
    interview's pattern of positive replicate weights.
    """
    records = records.sort_values(["cuid", "quarter_index"])
    previous = records.groupby("cuid")[["quarter_index", "pattern"]].shift()
    consecutive = (
        records["quarter_index"] - previous["quarter_index"]
    ).to_numpy() == 1
    kept = (
        records["pattern"].to_numpy() == previous["pattern"].to_numpy()
    ) & consecutive
    by_quarter = (
        pd.DataFrame(
            {
                "quarter": records["quarter"].to_numpy()[consecutive],
                "kept": kept[consecutive],
            }
        )
        .groupby("quarter")["kept"]
        .agg(["size", "mean"])
    )
    changed = by_quarter[by_quarter["mean"] < 1]
    return {
        "consecutive_interview_pairs": int(consecutive.sum()),
        "distinct_patterns": int(records["pattern"].nunique()),
        "quarters_with_changes": {
            quarter: {
                "pairs": int(row["size"]),
                "share_keeping_pattern": float(row["mean"]),
            }
            for quarter, row in changed.iterrows()
        },
        "quarters_without_changes": int((by_quarter["mean"] == 1).sum()),
    }


def compact_numbers(text: str) -> str:
    """Put each JSON array of numbers on one line."""
    number = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
    pattern = re.compile(rf"\[\s*({number}(?:,\s*{number})*)\s*\]")
    return pattern.sub(
        lambda match: (
            "["
            + ", ".join(part.strip() for part in match.group(1).split(","))
            + "]"
        ),
        text,
    )


def year_record(estimates, published, errors, imputed_terms: bool) -> dict:
    without = {t: [r[t] for r in estimates.without] for t in TENURES}
    with_stage = {
        t: [[r[t] for r in runs] for runs in estimates.with_stage]
        for t in TENURES
    }
    lift = {
        t: [
            [
                100 * (staged[t] / plain[t] - 1)
                for staged, plain in zip(runs, estimates.without)
            ]
            for runs in estimates.with_stage
        ]
        for t in TENURES
    }
    band_amounts = {
        name: [[amounts(b)[name] for b in bands] for bands in estimates.bands]
        for name in AMOUNTS
    }
    record = {
        "without_in_kind": {t: brr_block(without[t]) for t in TENURES},
        "with_in_kind": {t: rubin_block(with_stage[t]) for t in TENURES},
        "in_kind_lift_percent": {t: rubin_block(lift[t]) for t in TENURES},
        "amounts": {name: rubin_block(band_amounts[name]) for name in AMOUNTS},
        "bls": {"thresholds": published, "standard_errors": errors},
        "replicates": {
            "without_in_kind": without,
            "with_in_kind": with_stage,
            "amounts": band_amounts,
        },
    }
    if imputed_terms:
        record["replicates"]["imputed_terms"] = {
            t: [
                [b.imputed_term(t) for b in bands] for bands in estimates.bands
            ]
            for t in TENURES
        }
    record["ratio_to_bls_standard_error"] = {
        "without_in_kind": {
            t: record["without_in_kind"][t]["standard_error"] / errors[t]
            for t in TENURES
        },
        "with_in_kind": {
            t: record["with_in_kind"][t]["standard_error"] / errors[t]
            for t in TENURES
        },
        "with_in_kind_within": {
            t: record["with_in_kind"][t]["within_standard_error"] / errors[t]
            for t in TENURES
        },
    }
    return record


def growth_record(estimates: dict, base: int, target: int) -> dict:
    a, b = estimates[base], estimates[target]
    implicates = range(len(a.with_stage))
    without = {
        t: [growth(x[t], y[t]) for x, y in zip(a.without, b.without)]
        for t in TENURES
    }
    with_stage = {
        t: [
            [
                growth(x[t], y[t])
                for x, y in zip(a.with_stage[m], b.with_stage[m])
            ]
            for m in implicates
        ]
        for t in TENURES
    }
    change = {
        t: [
            [g - h for g, h in zip(with_stage[t][m], without[t])]
            for m in implicates
        ]
        for t in TENURES
    }
    record = {
        "without_in_kind": {t: brr_block(without[t]) for t in TENURES},
        "with_in_kind": {t: rubin_block(with_stage[t]) for t in TENURES},
        "stage_change_points": {t: rubin_block(change[t]) for t in TENURES},
        "bls_growth": {
            t: growth(
                get_published_thresholds(base)[t],
                get_published_thresholds(target)[t],
            )
            for t in TENURES
        },
    }
    for t in TENURES:
        start = float(np.mean([a.with_stage[m][0][t] for m in implicates]))
        end = float(np.mean([b.with_stage[m][0][t] for m in implicates]))
        record["with_in_kind"][t]["from_mean_thresholds"] = growth(start, end)
        record["stage_change_points"][t]["from_mean_thresholds"] = growth(
            start, end
        ) - growth(a.without[0][t], b.without[0][t])
    if (base, target) == AMOUNT_SPAN:
        record["growth_without_imputed_terms"] = without_imputed_terms(a, b)
    return record


def without_imputed_terms(a, b) -> dict:
    """Growth with each band's imputed terms taken out of its thresholds."""
    implicates = range(len(a.with_stage))

    def net(estimates, m, r, tenure):
        return estimates.with_stage[m][r][tenure] - estimates.bands[m][
            r
        ].imputed_term(tenure)

    out = {}
    for t in TENURES:
        draws = [
            [
                growth(net(a, m, r, t), net(b, m, r, t))
                for r in range(len(a.with_stage[m]))
            ]
            for m in implicates
        ]
        out[t] = rubin_block(draws)
        start = float(np.mean([net(a, m, 0, t) for m in implicates]))
        end = float(np.mean([net(b, m, 0, t) for m in implicates]))
        out[t]["from_mean_thresholds"] = growth(start, end)
    return out


def amount_rise_record(estimates: dict, base: int, target: int) -> dict:
    a, b = estimates[base], estimates[target]
    out = {}
    for name in AMOUNTS:
        rises = [
            [
                amounts(y)[name] - amounts(x)[name]
                for x, y in zip(a.bands[m], b.bands[m])
            ]
            for m in range(len(a.bands))
        ]
        out[name] = rubin_block(rises)
    return out


def largest_gap(
    ours: list[float], expected: list[float], what: str, tolerance: float
) -> float:
    if len(ours) != len(expected):
        raise RuntimeError(
            f"{what}: {len(ours)} values, {len(expected)} expected"
        )
    largest = 0.0
    for value, reference in zip(ours, expected):
        gap = abs(value / reference - 1)
        if not gap <= tolerance:
            raise RuntimeError(f"{what}: {value} != {reference}")
        largest = max(largest, gap)
    return largest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ce-cache",
        type=Path,
        default=Path.home() / ".cache/spm-calculator/ce-pumd",
    )
    parser.add_argument(
        "--cps-cache",
        type=Path,
        default=Path.home() / ".cache/spm-calculator/cps-asec",
    )
    parser.add_argument(
        "--cpi-input",
        type=Path,
        default=ROOT / "spm_calculator/data/bls/cpi_annual.json",
    )
    parser.add_argument("--implicates", type=int, default=5)
    parser.add_argument(
        "--targets",
        type=int,
        nargs="+",
        default=list(TARGETS),
        help="Target years to run (a smoke run may pick a subset)",
    )
    parser.add_argument(
        "--replicates",
        type=int,
        default=REPLICATES,
        help="Run replicates 1..N (a smoke run may pick fewer than 44)",
    )
    parser.add_argument("--receipt", type=Path, default=RECEIPT)
    args = parser.parse_args()
    complete = sorted(args.targets) == list(TARGETS) and (
        args.replicates == REPLICATES
    )
    if args.receipt.resolve() == RECEIPT.resolve() and not complete:
        parser.error("A partial run cannot overwrite the committed receipt")
    started = time.time()
    cpi_document = json.loads(args.cpi_input.read_text())
    cpi_series = {
        sid: pd.Series({int(y): v for y, v in values.items()})
        for sid, values in cpi_document["series"].items()
    }
    fcsuti_series = pd.Series(
        {year: float(level) for year, level in BLS_FCSUTI_INDEX.items()}
    )
    deflators = {
        "package": cpi_series,
        "fcsuti": {sid: fcsuti_series for sid in CPI_SERIES.values()},
    }
    replication = json.loads(REPLICATION_RECEIPT.read_text())
    components = json.loads(COMPONENTS_RECEIPT.read_text())

    # The imputation reads every quarter of 2019-2025, as in
    # scripts/replicate_ce_inkind.py, whatever --targets selects.
    quarters = sorted({q for t in TARGETS for q in bls_quarter_window(t)})
    raw, weights, bundles, patterns = {}, {}, {}, []
    weight_sum_gap = 0.0
    for quarter in quarters:
        frame = load_ce_quarter(
            *quarter, cache_dir=args.ce_cache, allow_download=False
        )
        source = frame.attrs["source"]
        bundle = Path(source["bundle_path"])
        bundles.setdefault(
            bundle.name, {"sha256": sha256(bundle), "url": source["url"]}
        )
        matrix = replicate_weight_matrix(frame)
        check_standard_brr(matrix)
        full = pd.to_numeric(frame["FINLWT21"]).to_numpy(dtype=float)
        weight_sum_gap = max(
            weight_sum_gap,
            float(np.abs(matrix.sum(axis=0) / full.sum() - 1).max()),
        )
        patterns.append(
            pd.DataFrame(
                {
                    "cuid": pd.to_numeric(frame["CUID"]).to_numpy(),
                    "quarter": f"{quarter[0]}Q{quarter[1]}",
                    "quarter_index": quarter[0] * 4 + quarter[1] - 1,
                    "pattern": [row.tobytes() for row in matrix > 0],
                }
            )
        )
        columns = [c for c in frame.columns if c in KEEP | IN_KIND_COLUMNS]
        raw[quarter] = frame[columns].copy()
        raw[quarter].attrs = {}
        weights[quarter] = matrix
    records = sum(len(m) for m in weights.values())
    print(f"Loaded {len(raw)} CE quarters, {records} records", flush=True)
    fmli = pd.concat(raw.values(), ignore_index=True)
    units = load_ce_unit_inputs(quarters, cache_dir=args.ce_cache)
    ce_units = ce_unit_covariates(fmli, units)
    reference_years = sorted(
        int(y) for y in ce_units["reference_year"].unique()
    )
    donors, cps_provenance = load_household_donors(
        [year + 1 for year in reference_years], args.cps_cache
    )
    config = InKindConfig(implicates=args.implicates)
    imputation = impute_in_kind(ce_units, donors, config)
    print(f"Imputed in {time.time() - started:.0f}s", flush=True)

    def window(target: int) -> tuple[pd.DataFrame, np.ndarray]:
        window_quarters = bls_quarter_window(target)
        frame = pd.concat([raw[q] for q in window_quarters], ignore_index=True)
        frame = frame[[c for c in frame.columns if c in KEEP]]
        return frame, np.vstack([weights[q] for q in window_quarters])

    targets = sorted(args.targets)
    replicate_numbers = list(range(1, args.replicates + 1))
    runs, identity_gap = {}, 0.0
    full_sample = {"thresholds": 0.0, "amounts": 0.0}
    for run in RUNS:
        estimates = {}
        for target in targets:
            frame, matrix = window(target)
            tables = [
                imputation.for_target(m, target)
                for m in range(config.implicates)
            ]
            estimates[target] = replicate_estimates(
                frame,
                target,
                tables,
                weights=matrix,
                replicates=replicate_numbers,
                youth_policy="exclude_unresolved",
                cpi_series=deflators[run],
            )
            identity_gap = max(identity_gap, estimates[target].identity_gap)
            expected = replication["results"][str(target)]
            if run == "fcsuti":
                expected = expected["fcsuti_deflated"]
            if estimates[target].without[0] != expected["without_in_kind"]:
                raise RuntimeError(f"{run} {target}: out-of-pocket run moved")
            for m in range(config.implicates):
                ours = estimates[target].with_stage[m][0]
                reference = expected["with_in_kind_by_implicate"][m]
                full_sample["thresholds"] = max(
                    full_sample["thresholds"],
                    largest_gap(
                        [ours[t] for t in TENURES],
                        [reference[t] for t in TENURES],
                        f"{run} {target} implicate {m} thresholds",
                        REPLICATION_TOLERANCE,
                    ),
                )
            recorded = components["runs"][run]["years"][str(target)][
                "with_in_kind"
            ]
            for name, field in AMOUNT_FIELDS.items():
                full_sample["amounts"] = max(
                    full_sample["amounts"],
                    largest_gap(
                        [
                            amounts(bands[0])[name]
                            for bands in estimates[target].bands
                        ],
                        recorded[field],
                        f"{run} {target} {name}",
                        AMOUNT_TOLERANCE,
                    ),
                )
            print(
                f"{run} {target}: {time.time() - started:.0f}s",
                flush=True,
            )
        years = {
            str(target): year_record(
                estimates[target],
                get_published_thresholds(target),
                get_standard_errors(target),
                target in AMOUNT_SPAN,
            )
            for target in targets
        }
        record = {"years": years, "growth": {}}
        for base, target in GROWTH_SPANS:
            if base in estimates and target in estimates:
                record["growth"][f"{base}-{target}"] = growth_record(
                    estimates, base, target
                )
        if all(year in estimates for year in AMOUNT_SPAN):
            record[f"amount_rise_{AMOUNT_SPAN[0]}_{AMOUNT_SPAN[1]}"] = (
                amount_rise_record(estimates, *AMOUNT_SPAN)
            )
        ratios = {
            stage: [
                years[y]["ratio_to_bls_standard_error"][stage][t]
                for y in years
                for t in TENURES
            ]
            for stage in ("without_in_kind", "with_in_kind")
        }
        record["ratio_to_bls_standard_error_range"] = {
            stage: [min(values), max(values)]
            for stage, values in ratios.items()
        }
        record["deflator"] = (
            "package composite CPI"
            if run == "package"
            else "BLS's published FCSUti index"
        )
        runs[run] = record

    git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    receipt = {
        "schema_version": 1,
        "classification": "current_retrospective_research",
        "generated_by": "scripts/estimate_ce_replicate_uncertainty.py",
        "generated_on": datetime.now(timezone.utc).date().isoformat(),
        "git_head": git_head,
        "complete": complete,
        "targets": targets,
        "replicates_run": len(replicate_numbers),
        "code_sha256": {path: sha256(ROOT / path) for path in CODE_PATHS},
        "inputs": {
            "ce_bundles": bundles,
            "cps_asec_files": cps_provenance,
            "cpi": {
                "path": str(args.cpi_input.relative_to(ROOT)),
                "sha256": sha256(args.cpi_input),
            },
            "replication_receipt": {
                "path": str(REPLICATION_RECEIPT.relative_to(ROOT)),
                "sha256": sha256(REPLICATION_RECEIPT),
            },
            "components_receipt": {
                "path": str(COMPONENTS_RECEIPT.relative_to(ROOT)),
                "sha256": sha256(COMPONENTS_RECEIPT),
            },
            "implicates": config.implicates,
            "imputation_seed": config.seed,
        },
        "method": METHOD,
        "checks": {
            "standard_brr": {
                "quarters": len(weights),
                "records": records,
                "positive_replicate_weights_per_record": REPLICATES // 2,
            },
            "replicate_weight_sum_largest_relative_gap": weight_sum_gap,
            "half_sample_patterns": half_sample_changes(
                pd.concat(patterns, ignore_index=True)
            ),
            "full_sample": {
                "out_of_pocket_matches_replication_receipt": True,
                "with_in_kind_largest_relative_gap": full_sample["thresholds"],
                "with_in_kind_tolerance": REPLICATION_TOLERANCE,
                "amounts_largest_relative_gap": full_sample["amounts"],
                "amounts_tolerance": AMOUNT_TOLERANCE,
            },
            "threshold_identity_largest_relative_gap": identity_gap,
            "threshold_identity_tolerance": IDENTITY_TOLERANCE,
        },
        "runs": runs,
        "limitations": LIMITATIONS,
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
        },
        "runtime_seconds": round(time.time() - started),
    }
    text = json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(compact_numbers(text) + "\n")
    print(f"Wrote {args.receipt} in {time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
