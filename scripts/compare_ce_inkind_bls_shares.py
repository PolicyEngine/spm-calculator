"""Compare the replication's threshold components with BLS's published ones.

BLS publishes each threshold component's share of each threshold, by tenure
and year, and the band's tenure distribution
(``spm_calculator.ce_bls_shares`` shows how those give in-band dollars). This
script computes the same components for the in-kind replication, with the
package composite CPI and with BLS's FCSUti index, and records:

- in-band amounts of each imputed benefit, ours and BLS's;
- each threshold term's part of the level gap to BLS;
- 2022-2025 growth of the imputed amounts and their part in threshold growth;
- the same replication with the shelter, utilities and food definitions in
  BLS's papers.

The in-band means must reproduce every threshold. The runs with the
replication's own definitions must match
``ce_inkind_replication_2019_2025.json``: exactly without the stage, and
within rounding with it, since the numeric runtime can move the last bits.
Otherwise the script stops. It makes no network requests, and its receipt
holds band means and counts, no CE or CPS records.

``scripts/render_ce_inkind_bls_tables.py`` prints the docs tables from the
receipt.

Run: uv run --no-sync python scripts/compare_ce_inkind_bls_shares.py
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.replicate_ce_inkind import (
    CODE_PATHS as REPLICATION_CODE_PATHS,
)
from scripts.replicate_ce_inkind import (
    IN_KIND_COLUMNS,
    KEEP,
    TARGETS,
    sha256,
)
from spm_calculator.ce_bls_shares import (
    COMPONENTS,
    DEFINITION_COLUMNS,
    IMPUTED,
    TENURES,
    BandComponents,
    apply_bls_paper_definition,
    band_components,
    band_definition_pieces,
    band_fixed_growth_effect,
    bls_band_components,
    growth_percent,
    growth_without_imputed,
    imputed_share_beyond_inflation,
    level_gap,
    mean_components,
    read_threshold_shares,
    removed_by_bls_paper_definition,
    unit_components,
)
from spm_calculator.ce_decomposition import BLS_FCSUTI_INDEX
from spm_calculator.ce_inkind import (
    InKindConfig,
    ce_unit_covariates,
    impute_in_kind,
    load_ce_unit_inputs,
)
from spm_calculator.ce_inkind_stage import (
    add_in_kind,
    prepare_out_of_pocket,
)
from spm_calculator.ce_threshold import (
    bls_quarter_window,
    estimate_thresholds,
    load_ce_quarter,
)
from spm_calculator.cps_asec import load_household_donors
from spm_calculator.equivalence_scale import REFERENCE_RAW_SCALE
from spm_calculator.fcsuti_cpi import CPI_SERIES
from spm_calculator.published_thresholds import (
    get_published_thresholds,
    get_tenure_shares,
)

DATA = ROOT / "spm_calculator/data/current"
REPLICATION_RECEIPT = DATA / "ce_inkind_replication_2019_2025.json"
RECEIPT = DATA / "ce_inkind_bls_components_2019_2025.json"
WORKBOOK = DATA / "bls_spm_shares.xlsx"
WORKBOOK_URL = "https://www.bls.gov/pir/spm/spm_shares.xlsx"
THRESHOLD_SERIES = ROOT / "spm_calculator/data/bls/threshold_series.json"
CODE_PATHS = (
    *REPLICATION_CODE_PATHS,
    "spm_calculator/ce_bls_shares.py",
    "spm_calculator/published_thresholds.py",
    "scripts/compare_ce_inkind_bls_shares.py",
)
BASE_YEAR, TARGET_YEAR = 2022, 2025
CPI_U = "CUUR0000SA0"
#: Relative disagreement accepted between the band means and the estimator.
COMPONENT_TOLERANCE = 1e-9
#: Relative disagreement accepted with the in-kind replication receipt.
REPLICATION_TOLERANCE = 1e-12
#: Run name -> (deflator, BLS's written definitions applied).
RUNS = {
    "package": ("package", False),
    "fcsuti": ("fcsuti", False),
    "package_bls_definition": ("package", True),
    "fcsuti_bls_definition": ("fcsuti", True),
}
LIMITATIONS = [
    "BLS's band means come from its shares of its thresholds; BLS has published neither its code nor unit-level values",
    "BLS's written definitions come from Garner and Munoz (2021); BLS's current code may differ, and its thresholds also carry later refinements and corrections",
    "FMLI's vacation-home utility summaries leave out coal, wood and other fuels for vacation homes (UCCs 250913 and 250914), so the definition runs keep those fuels",
    "Removing imputed terms holds each band as it stands; the replication's own with-and-without runs show how far rank shifts move that",
    "The replication still omits home internet spending, which BLS's FCSUti includes",
    "The runs estimate imputation uncertainty (implicate spread) but not sampling uncertainty",
]


def _recorded_path(path: Path) -> str:
    """``path`` relative to the repository when it lies inside it."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def spread(values) -> float:
    return float(np.std(values, ddof=1)) if len(values) > 1 else 0.0


def largest_difference(ours, expected, what: str, tolerance: float) -> float:
    """The largest relative difference; raises when one exceeds tolerance
    or is not finite."""
    largest = 0.0
    for tenure in TENURES:
        difference = abs(ours[tenure] / expected[tenure] - 1.0)
        if not np.isfinite(difference) or difference > tolerance:
            raise RuntimeError(
                f"{what}: {tenure} {ours[tenure]} != {expected[tenure]}"
            )
        largest = max(largest, difference)
    return largest


def definition_check(window: pd.DataFrame, target: int, cpi: dict) -> dict:
    """Largest unit errors of BLS's written definitions against what they name.

    With one price index for every component, each unit keeps its price
    factor under both definitions, so its shelter, utilities and food must
    fall by exactly the amounts the definitions remove.
    """
    options = {"youth_policy": "exclude_unresolved", "cpi_series": cpi}
    before = prepare_out_of_pocket(window, target, **options).expenditures
    after = prepare_out_of_pocket(
        apply_bls_paper_definition(window), target, **options
    ).expenditures
    if not before["NEWID"].equals(after["NEWID"]):
        raise RuntimeError(f"{target}: the definitions changed the sample")
    removed = removed_by_bls_paper_definition(before)
    factor = (
        4.0
        * before["inflation_factor"].to_numpy(dtype=float)
        * (REFERENCE_RAW_SCALE / before["equiv_scale"]).to_numpy(dtype=float)
    )
    units_before, units_after = unit_components(before), unit_components(after)
    expected_shelter = (
        removed["other_lodging"]
        + removed["rent_as_pay"]
        + removed["vacation_home_principal"]
    ).to_numpy() * factor
    expected_food = removed["meals_as_pay"].to_numpy() * factor
    expected_utilities = removed["vacation_utilities"].to_numpy() * factor
    errors = {
        "shelter": float(
            np.abs(
                (units_before["shelter"] - units_after["shelter"]).to_numpy()
                - expected_shelter
            ).max()
        ),
        "food": float(
            np.abs(
                (units_before["food"] - units_after["food"]).to_numpy()
                - expected_food
            ).max()
        ),
        "utilities": float(
            np.abs(
                (
                    units_before["utilities"] - units_after["utilities"]
                ).to_numpy()
                - expected_utilities
            ).max()
        ),
    }
    if not all(np.isfinite(e) and e <= 1e-6 for e in errors.values()):
        raise RuntimeError(f"{target}: definitions miss by {errors}")
    return {
        "largest_unit_error_dollars": errors,
        "units": len(before),
        "units_with_amount_removed": {
            piece: int((removed[piece] > 0).sum()) for piece in removed
        },
        "units_with_negative_amount": {
            piece: int((removed[piece] < 0).sum()) for piece in removed
        },
        "units_with_utilities_below_zero": {
            "before": int((units_before["utilities"] < 0).sum()),
            "after": int((units_after["utilities"] < 0).sum()),
        },
    }


def gap_record(
    band: BandComponents, bls: BandComponents, published: dict
) -> dict:
    """Each term's part of the level gap, in percent of BLS's threshold."""
    out = {}
    for tenure in TENURES:
        terms = level_gap(band, bls, tenure)
        percent = {c: 100 * terms[c] / published[tenure] for c in COMPONENTS}
        out[tenure] = {
            "terms": percent,
            "imputed": sum(percent[c] for c in IMPUTED),
            "total": sum(percent.values()),
        }
    return out


def year_record(
    window: pd.DataFrame,
    target: int,
    cpi: dict,
    imputation,
    implicates: int,
    bls: BandComponents,
    published: dict,
    expected: dict | None,
) -> tuple[dict, BandComponents, list[BandComponents]]:
    prepared = prepare_out_of_pocket(
        window, target, youth_policy="exclude_unresolved", cpi_series=cpi
    )
    without_thresholds = prepared.result["thresholds"]
    without = band_components(prepared.expenditures, prepared.median_share)
    largest_difference(
        {t: without.threshold(t) for t in TENURES},
        without_thresholds,
        f"{target} components without the stage",
        COMPONENT_TOLERANCE,
    )
    if expected is not None and without_thresholds != expected["without"]:
        raise RuntimeError(f"{target}: out-of-pocket run != receipt")
    bands, thresholds, pieces = [], [], []
    from_receipt = 0.0
    for implicate in range(implicates):
        frame, _ = add_in_kind(
            prepared.expenditures, imputation.for_target(implicate, target)
        )
        estimated, _ = estimate_thresholds(frame, prepared.median_share)
        band = band_components(frame, prepared.median_share)
        largest_difference(
            {t: band.threshold(t) for t in TENURES},
            estimated,
            f"{target} implicate {implicate} components",
            COMPONENT_TOLERANCE,
        )
        if expected is not None:
            from_receipt = max(
                from_receipt,
                largest_difference(
                    estimated,
                    expected["with"][implicate],
                    f"{target} implicate {implicate} against the receipt",
                    REPLICATION_TOLERANCE,
                ),
            )
        bands.append(band)
        thresholds.append(estimated)
        pieces.append(band_definition_pieces(frame))
    mean = mean_components(bands)
    mean_thresholds = {t: mean.threshold(t) for t in TENURES}
    mean_pieces = {
        group: {
            piece: float(np.mean([p[group][piece] for p in pieces]))
            for piece in pieces[0][group]
        }
        for group in pieces[0]
    }
    record = {
        "without_in_kind": {
            "thresholds": without_thresholds,
            "gap_percent": {
                t: 100 * (without_thresholds[t] / published[t] - 1)
                for t in TENURES
            },
            "band": without.to_dict(),
            "band_rows": prepared.result["estimation"]["band_rows"],
        },
        "with_in_kind": {
            "thresholds": mean_thresholds,
            "thresholds_by_implicate": thresholds,
            "between_implicate_sd": {
                t: spread([r[t] for r in thresholds]) for t in TENURES
            },
            "gap_percent": {
                t: 100 * (mean_thresholds[t] / published[t] - 1)
                for t in TENURES
            },
            "band": mean.to_dict(),
            "imputed_total": mean.imputed_total,
            "imputed_total_by_implicate": [b.imputed_total for b in bands],
            "rental_assistance_per_renter_by_implicate": [
                b.by_tenure["renter"]["rental_assistance"] for b in bands
            ],
            "school_lunch_by_implicate": [b.pooled["nslp"] for b in bands],
            "band_pieces": mean_pieces,
        },
        "level_gap_percent_of_bls": gap_record(mean, bls, published),
        "shelter_excess_dollars": {
            t: mean.by_tenure[t]["shelter"] - bls.by_tenure[t]["shelter"]
            for t in TENURES
        },
        "largest_relative_difference_from_receipt": from_receipt,
    }
    return record, without, bands


def growth_record(
    without: dict[int, BandComponents],
    bands: dict[int, list[BandComponents]],
    bls: dict[int, BandComponents],
    price_ratio: float,
) -> dict:
    """2022-2025 growth of the imputed amounts and of the thresholds."""
    base_mean = mean_components(bands[BASE_YEAR])
    target_mean = mean_components(bands[TARGET_YEAR])
    a0, b0 = without[BASE_YEAR], without[TARGET_YEAR]
    pairs = list(zip(bands[BASE_YEAR], bands[TARGET_YEAR]))
    a_bls, b_bls = bls[BASE_YEAR], bls[TARGET_YEAR]
    by_tenure = {}
    for tenure in TENURES:
        growth_without = growth_percent(
            a0.threshold(tenure), b0.threshold(tenure)
        )
        growth_with = growth_percent(
            base_mean.threshold(tenure), target_mean.threshold(tenure)
        )
        change = growth_with - growth_without
        change_by_implicate = [
            growth_percent(a.threshold(tenure), b.threshold(tenure))
            - growth_without
            for a, b in pairs
        ]
        band_fixed = band_fixed_growth_effect(base_mean, target_mean, tenure)
        without_imputed = growth_without_imputed(
            base_mean, target_mean, tenure
        )
        bls_growth = growth_percent(
            a_bls.threshold(tenure), b_bls.threshold(tenure)
        )
        by_tenure[tenure] = {
            "growth_without_stage": growth_without,
            "growth_with_stage": growth_with,
            "stage_change_points": change,
            "stage_change_between_implicate_sd": spread(change_by_implicate),
            "stage_change_by_implicate": change_by_implicate,
            "growth_less_bls_points": growth_with - bls_growth,
            "band_fixed_effect_points": band_fixed,
            "band_fixed_effect_between_implicate_sd": spread(
                [band_fixed_growth_effect(a, b, tenure) for a, b in pairs]
            ),
            "rank_shift_points": change - band_fixed,
            "growth_without_imputed_terms": without_imputed,
            "growth_without_imputed_terms_by_implicate": [
                growth_without_imputed(a, b, tenure) for a, b in pairs
            ],
            "growth_without_imputed_terms_less_bls_points": without_imputed
            - growth_without_imputed(a_bls, b_bls, tenure),
            "imputed_share_of_growth_beyond_cpi_u_percent": 100
            * imputed_share_beyond_inflation(
                base_mean, target_mean, tenure, price_ratio
            ),
            "imputed_term_dollars": {
                str(BASE_YEAR): base_mean.imputed_term(tenure),
                str(TARGET_YEAR): target_mean.imputed_term(tenure),
            },
        }
    return {
        "imputed_total": {
            str(BASE_YEAR): base_mean.imputed_total,
            str(TARGET_YEAR): target_mean.imputed_total,
            "rise": target_mean.imputed_total - base_mean.imputed_total,
            "rise_by_implicate": [
                b.imputed_total - a.imputed_total for a, b in pairs
            ],
        },
        "rental_assistance_per_renter": {
            str(BASE_YEAR): base_mean.by_tenure["renter"]["rental_assistance"],
            str(TARGET_YEAR): target_mean.by_tenure["renter"][
                "rental_assistance"
            ],
            "rise": target_mean.by_tenure["renter"]["rental_assistance"]
            - base_mean.by_tenure["renter"]["rental_assistance"],
        },
        "school_lunch": {
            str(BASE_YEAR): base_mean.pooled["nslp"],
            str(TARGET_YEAR): target_mean.pooled["nslp"],
            "rise": target_mean.pooled["nslp"] - base_mean.pooled["nslp"],
        },
        "by_tenure": by_tenure,
    }


def bls_growth_record(
    bls: dict[int, BandComponents], price_ratio: float
) -> dict:
    a, b = bls[BASE_YEAR], bls[TARGET_YEAR]
    return {
        "imputed_total": {
            str(BASE_YEAR): a.imputed_total,
            str(TARGET_YEAR): b.imputed_total,
            "rise": b.imputed_total - a.imputed_total,
        },
        "rental_assistance_per_renter": {
            str(BASE_YEAR): a.by_tenure["renter"]["rental_assistance"],
            str(TARGET_YEAR): b.by_tenure["renter"]["rental_assistance"],
            "rise": b.by_tenure["renter"]["rental_assistance"]
            - a.by_tenure["renter"]["rental_assistance"],
        },
        "school_lunch": {
            str(BASE_YEAR): a.pooled["nslp"],
            str(TARGET_YEAR): b.pooled["nslp"],
            "rise": b.pooled["nslp"] - a.pooled["nslp"],
        },
        "by_tenure": {
            t: {
                "growth": growth_percent(a.threshold(t), b.threshold(t)),
                "band_fixed_effect_points": band_fixed_growth_effect(a, b, t),
                "growth_without_imputed_terms": growth_without_imputed(
                    a, b, t
                ),
                "imputed_share_of_growth_beyond_cpi_u_percent": 100
                * imputed_share_beyond_inflation(a, b, t, price_ratio),
                "imputed_term_dollars": {
                    str(BASE_YEAR): a.imputed_term(t),
                    str(TARGET_YEAR): b.imputed_term(t),
                },
            }
            for t in TENURES
        },
    }


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
    parser.add_argument("--receipt", type=Path, default=RECEIPT)
    args = parser.parse_args()
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
    price_ratio = float(cpi_series[CPI_U][TARGET_YEAR]) / float(
        cpi_series[CPI_U][BASE_YEAR]
    )
    replication = json.loads(REPLICATION_RECEIPT.read_text())

    shares = read_threshold_shares(WORKBOOK)
    published = {t: get_published_thresholds(t) for t in TARGETS}
    bls, bls_checks = {}, {}
    for target in TARGETS:
        bls[target], bls_checks[target] = bls_band_components(
            shares[target], published[target], get_tenure_shares(target)
        )
        if (
            published[target]
            != replication["results"][str(target)]["published"]
        ):
            raise RuntimeError(f"{target}: published thresholds changed")

    quarters = sorted({q for t in TARGETS for q in bls_quarter_window(t)})
    wanted = KEEP | IN_KIND_COLUMNS | set(DEFINITION_COLUMNS)
    raw = {}
    for quarter in quarters:
        frame = load_ce_quarter(
            *quarter, cache_dir=args.ce_cache, allow_download=False
        )
        missing = sorted(set(DEFINITION_COLUMNS) - set(frame.columns))
        if missing:
            raise RuntimeError(f"{quarter}: FMLI lacks {missing}")
        raw[quarter] = frame[[c for c in frame.columns if c in wanted]].copy()
        raw[quarter].attrs = {}
    print(f"Loaded {len(raw)} CE quarters", flush=True)
    fmli = pd.concat(raw.values(), ignore_index=True)
    units = load_ce_unit_inputs(quarters, cache_dir=args.ce_cache)
    ce_units = ce_unit_covariates(fmli, units)
    reference_years = sorted(
        int(y) for y in ce_units["reference_year"].unique()
    )
    donors, _ = load_household_donors(
        [year + 1 for year in reference_years], args.cps_cache
    )
    config = InKindConfig(implicates=args.implicates)
    imputation = impute_in_kind(ce_units, donors, config)
    print(f"Imputed in {time.time() - started:.0f}s", flush=True)

    keep = KEEP | set(DEFINITION_COLUMNS)

    def window(target: int, definition: bool) -> pd.DataFrame:
        frame = pd.concat(
            [raw[q] for q in bls_quarter_window(target)], ignore_index=True
        )
        frame = frame[[c for c in frame.columns if c in keep]]
        return apply_bls_paper_definition(frame) if definition else frame

    def expected_for(run: str, target: int) -> dict | None:
        result = replication["results"][str(target)]
        if run == "package":
            return {
                "without": result["without_in_kind"],
                "with": result["with_in_kind_by_implicate"],
            }
        if run == "fcsuti":
            return {
                "without": result["fcsuti_deflated"]["without_in_kind"],
                "with": result["fcsuti_deflated"]["with_in_kind_by_implicate"],
            }
        return None

    runs = {}
    for run, (deflator, definition) in RUNS.items():
        years, without_bands, implicate_bands = {}, {}, {}
        for target in TARGETS:
            (
                years[str(target)],
                without_bands[target],
                implicate_bands[target],
            ) = year_record(
                window(target, definition),
                target,
                deflators[deflator],
                imputation,
                config.implicates,
                bls[target],
                published[target],
                expected_for(run, target),
            )
        runs[run] = {
            "deflator": deflator,
            "bls_written_definitions": definition,
            "years": years,
            "growth_2022_2025": growth_record(
                without_bands, implicate_bands, bls, price_ratio
            ),
        }
        print(f"Finished {run} at {time.time() - started:.0f}s", flush=True)

    definition_checks = {
        str(target): definition_check(
            window(target, False), target, deflators["fcsuti"]
        )
        for target in TARGETS
    }

    receipt = {
        "schema_version": 1,
        "generated_by": "scripts/compare_ce_inkind_bls_shares.py",
        "generated_on": datetime.now(timezone.utc).date().isoformat(),
        "classification": "current_retrospective_research",
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "code_sha256": {p: sha256(ROOT / p) for p in CODE_PATHS},
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
        "inputs": {
            "bls_shares_workbook": {
                "path": str(WORKBOOK.relative_to(ROOT)),
                "sha256": sha256(WORKBOOK),
                "url": WORKBOOK_URL,
            },
            "threshold_series": {
                "path": str(THRESHOLD_SERIES.relative_to(ROOT)),
                "sha256": sha256(THRESHOLD_SERIES),
            },
            "replication_receipt": {
                "path": str(REPLICATION_RECEIPT.relative_to(ROOT)),
                "sha256": sha256(REPLICATION_RECEIPT),
            },
            "cpi": {
                "path": _recorded_path(args.cpi_input),
                "sha256": sha256(args.cpi_input),
                "cpi_u_ratio_2022_2025": price_ratio,
            },
        },
        "replication_receipt_check": {
            run: {
                "out_of_pocket_thresholds_identical": True,
                "with_in_kind_largest_relative_difference": max(
                    record["largest_relative_difference_from_receipt"]
                    for record in runs[run]["years"].values()
                ),
                "with_in_kind_tolerance": REPLICATION_TOLERANCE,
            }
            for run in ("package", "fcsuti")
        },
        "definition_check": definition_checks,
        "bls": {
            "years": {
                str(t): {
                    "published_thresholds": published[t],
                    "band": bls[t].to_dict(),
                    "imputed_total": bls[t].imputed_total,
                    "checks": bls_checks[t],
                }
                for t in TARGETS
            },
            "growth_2022_2025": bls_growth_record(bls, price_ratio),
        },
        "runs": runs,
        "limitations": LIMITATIONS,
        "runtime_seconds": round(time.time() - started),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(f"Saved {args.receipt} in {time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
