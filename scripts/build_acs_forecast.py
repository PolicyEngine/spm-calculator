"""Build the ACS rolling-window research artifact from pinned cached sources.

This command is offline, including --check. Raw ACS archives stay outside the
repository; committed compact sources contain geography and topcoding inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from spm_calculator.acs_forecast import (
    add_index_topcode_diagnostics,
    build_window,
    evaluate_indices,
    project_acs_windows,
    summarize_window,
)
from spm_calculator.acs_forecast_sources import (
    BUNDLE_SHA256,
    CPI_RECEIPT_SHA256,
    load_pums_records,
    load_source_bundle,
    sha256_file,
    verify_file,
)
from spm_calculator.fcsuti_cpi import get_packaged_cpi_series
from spm_calculator.forecast import CPI_PROJECTIONS

ROOT = Path(__file__).resolve().parents[1]


def encode(result: dict) -> bytes:
    """Canonical readable JSON without clocks, machine paths or nonfinite floats."""
    return (
        json.dumps(
            result,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode()


def _price_paths() -> tuple[dict, dict]:
    receipt = ROOT / "spm_calculator/data/current/acs_cpi_verification.json"
    verify_file(receipt, CPI_RECEIPT_SHA256)
    source = json.loads(receipt.read_text())
    if source.get("status") != "REQUEST_SUCCEEDED":
        raise ValueError("Pinned BLS receipt is not a successful API response")
    values = {
        int(r["year"]): float(r["value"])
        for series in source["Results"]["series"]
        if series["seriesID"] == "CUUR0000SA0"
        for r in series["data"]
        if r["period"] == "M13"
    }
    if values != {2024: 313.689, 2025: 321.943}:
        raise ValueError(
            "Pinned observed BLS annual values need reconciliation"
        )
    cpi = get_packaged_cpi_series("CUUR0000SA0", 2022, 2025)
    if any(float(cpi[y]) != value for y, value in values.items()):
        raise ValueError(
            "Packaged CPI differs from directly verified BLS receipt"
        )
    rates = {
        2025: values[2025] / values[2024] - 1,
        **{year: float(CPI_PROJECTIONS[year]) for year in range(2026, 2031)},
    }
    details = {
        "series_id": "CUUR0000SA0",
        "observed_annual_values": {str(y): float(v) for y, v in cpi.items()},
        "observed_2025_note": "BLS M13 annual average uses eleven months; October is missing owing to the lapse in appropriations.",
        "forecast_source": "Explicit package inflation scenario, not an external forecast",
        "receipt_sha256": CPI_RECEIPT_SHA256,
        "receipt_url": "https://api.bls.gov/publicAPI/v2/timeseries/data/CUUR0000SA0?startyear=2024&endyear=2025&annualaverage=true",
    }
    return rates, details


def evaluate_frozen_prediction(
    frozen_prediction: dict, official_workbook: Path
) -> dict:
    """Score the frozen 2025 vector before any recalibration to a new workbook."""
    import openpyxl

    prediction = frozen_prediction["frozen_prediction_indices"]
    expected = hashlib.sha256(encode(prediction)).hexdigest()
    if frozen_prediction["frozen_prediction_sha256"] != expected:
        raise ValueError("Frozen prediction SHA256 mismatch")
    wb = openpyxl.load_workbook(official_workbook, data_only=True)
    sheet = wb["Thresholds 2025"]
    target = {
        str(int(row[0])): float(row[2])
        for row in sheet.iter_rows(min_row=3, values_only=True)
        if isinstance(row[0], (int, float))
        and isinstance(row[2], (int, float))
    }
    result = evaluate_indices(
        prediction, target, frozen_prediction["carry_indices"]
    )
    result.update(
        {
            "kind": "frozen_forward_prediction_evaluation",
            "target_spm_year": 2025,
            "prediction_sha256": expected,
            "official_workbook_sha256": sha256_file(official_workbook),
        }
    )
    return result


def build_result(
    cache_dir: Path, *, information_date: str = "2026-09-09", progress=None
) -> dict:
    """Build baseline, sensitivity and complete 341-area historical evaluation."""
    if information_date != "2026-09-09":
        raise ValueError(
            "This source vintage is pinned to information date 2026-09-09"
        )
    log = progress or (lambda message: None)
    bundle = load_source_bundle()
    area_codes = sorted(bundle["official_indices"]["2024"])
    if len(area_codes) != 341 or set(area_codes) != set(
        bundle["official_indices"]["2023"]
    ):
        raise ValueError("Required official 341-area anchor coverage differs")
    allocations = pd.DataFrame(bundle["area_allocations"])
    rates, price_details = _price_paths()
    observed = {}
    for vintage in (2023, 2024, 2022):
        log(f"Loading pinned ACS {vintage} five-year records")
        observed[vintage] = load_pums_records(cache_dir, vintage, bundle)
        log(
            f"ACS {vintage}: {len(observed[vintage]):,} eligible rental records"
        )
    log("Projecting pooled ACS windows and overlap vintage bridge")
    result = project_acs_windows(
        observed[2023],
        observed[2024],
        allocations,
        bundle["official_indices"]["2024"],
        nominal_rent_growth_by_year=rates,
        price_growth_by_year=rates,
    )
    log("Computing declared nominal-rent +2 percentage point sensitivity")
    sensitivity = project_acs_windows(
        observed[2023],
        observed[2024],
        allocations,
        bundle["official_indices"]["2024"],
        nominal_rent_growth_by_year={y: r + 0.02 for y, r in rates.items()},
        price_growth_by_year=rates,
    )
    sensitivity["index_difference_by_year"] = {
        year: {
            code: value - result["indices_by_year"][year][code]
            for code, value in indices.items()
        }
        for year, indices in sensitivity["indices_by_year"].items()
    }
    result["sensitivity"] = {"rent_plus_2pp": sensitivity}
    log("Evaluating 2023-origin donor mechanism against official 2024 indices")
    origin_summary = summarize_window(observed[2022], allocations, area_codes)
    cpi = get_packaged_cpi_series("CUUR0000SA0", 2022, 2023)
    historical_rate = {2023: float(cpi[2023] / cpi[2022] - 1)}
    target_window = build_window(
        observed[2022],
        2024,
        donor_year=2022,
        nominal_rent_growth_by_year=historical_rate,
        price_growth_by_year=historical_rate,
    )
    target_summary = summarize_window(target_window, allocations, area_codes)
    add_index_topcode_diagnostics(target_summary, {"origin": origin_summary})
    carry = bundle["official_indices"]["2023"]
    prediction = {
        code: carry[code]
        * target_summary["areas"][code]["model_rent_index"]
        / origin_summary["areas"][code]["model_rent_index"]
        for code in area_codes
    }
    backtest = evaluate_indices(
        prediction, bundle["official_indices"]["2024"], carry
    )
    if (
        backtest["status"] != "complete"
        or backtest["common_area_count"] != 341
    ):
        raise ValueError("Required historical ACS evaluation is incomplete")
    for code, row in backtest["areas"].items():
        row["thin_support"] = bool(
            origin_summary["areas"][code]["thin_support"]
            or target_summary["areas"][code]["thin_support"]
        )
        row["median_topcode_warning"] = bool(
            origin_summary["areas"][code]["median_topcode_warning"]
            or target_summary["areas"][code]["median_topcode_warning"]
        )
        row["local_median_topcode_warning"] = row["median_topcode_warning"]
        row["rent_index_topcode_warning"] = target_summary["areas"][code][
            "rent_index_topcode_warning"
        ]
        row["rent_index_topcode_sources"] = target_summary["areas"][code][
            "rent_index_topcode_sources"
        ]
    backtest.update(
        {
            "kind": "retrospective_conditional_donor_mechanism_holdout",
            "origin_spm_year": 2023,
            "target_spm_year": 2024,
            "origin_acs_window": [2018, 2022],
            "target_acs_window": [2019, 2023],
            "donor_year": 2022,
            "nominal_rent_growth_by_year": {"2023": historical_rate[2023]},
            "price_growth_by_year": {"2023": historical_rate[2023]},
            "evaluation_scope": "All 341 common published areas; equal-area MAPE; prices realized and source vintages current. Does not validate the later overlap bridge or prospective accuracy.",
            "origin_diagnostics": origin_summary,
            "target_diagnostics": target_summary,
        }
    )
    result["backtest"] = backtest
    frozen = result["indices_by_year"]["2025"]
    result["forward_test"] = {
        "status": "pending official data",
        "target_spm_year": 2025,
        "frozen_prediction_indices": frozen,
        "frozen_prediction_sha256": hashlib.sha256(encode(frozen)).hexdigest(),
        "carry_indices": bundle["official_indices"]["2024"],
        "information_date": information_date,
        "evaluator": "scripts.build_acs_forecast.evaluate_frozen_prediction",
    }
    result["schema_version"] = 1
    result["method"] = "acs_pums_rolling_window_research"
    result["metadata"].update(
        {
            "information_date": information_date,
            "source_vintages": bundle["source_vintages"],
            "puma_vintage": 2020,
            "cbsa_vintage": "2013-02-28",
            "county_vintage": 2020,
            "survey_year_extraction_rule": "First four digits of validated Census housing SERIALNO",
            "dollar_adjustment_rule": "GRNTP * source ADJHSG / 1000000 exactly once; donor nominal growth divided by its separately declared price path",
            "price_inputs": price_details,
            "topcode_method": bundle["topcode_method"],
            "geography_method": bundle["geography_method"],
            "source_bundle_sha256": BUNDLE_SHA256,
            "source_product_counts": {
                str(v): {
                    str(int(y)): int(n)
                    for y, n in records.groupby("cohort_year").size().items()
                }
                for v, records in observed.items()
            },
            "approximations": [
                bundle["geography_method"],
                "Discrete weighted PUMS medians approximate confidential Census grouped-data median interpolation; topcoding may affect medians.",
                "Four-year overlap subpools retain their product's five-year calibrated weights; the bridge removes their measured vintage shift but does not make future weights known.",
                "Donor households, housing stock and weights remain fixed; baseline assumes zero real rent growth for new cohorts.",
                "Neither Kish support nor OLS/price sensitivities constitute a survey-design variance or forecast confidence interval.",
            ],
            "generator_identity": {
                name: sha256_file(ROOT / name)
                for name in [
                    "spm_calculator/acs_forecast.py",
                    "spm_calculator/acs_forecast_sources.py",
                    "scripts/build_acs_forecast.py",
                ]
            },
        }
    )
    result["sources"] = bundle["sources"] + [
        {
            "id": "acs_forecast_inputs",
            "package_path": "spm_calculator/data/current/acs_forecast_inputs.json",
            "sha256": BUNDLE_SHA256,
        },
        {
            "id": "bls_cpi_verification",
            "package_path": "spm_calculator/data/current/acs_cpi_verification.json",
            "url": price_details["receipt_url"],
            "sha256": CPI_RECEIPT_SHA256,
            "acquired_at_utc": "2026-09-09",
        },
        {
            "id": "packaged_cpi_annual",
            "package_path": "spm_calculator/data/bls/cpi_annual.json",
            "sha256": sha256_file(
                ROOT / "spm_calculator/data/bls/cpi_annual.json"
            ),
        },
        {
            "id": "package_inflation_assumptions",
            "package_path": "spm_calculator/forecast.py",
            "sha256": sha256_file(ROOT / "spm_calculator/forecast.py"),
        },
    ]
    # Validate the full result can be serialized before returning partial work.
    encode(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache/spm-calculator/acs-pums",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--information-date", default="2026-09-09")
    args = parser.parse_args()
    result = build_result(
        args.cache_dir,
        information_date=args.information_date,
        progress=lambda message: print(message, flush=True),
    )
    encoded = encode(result)
    if args.check:
        if not args.output.exists() or args.output.read_bytes() != encoded:
            raise SystemExit(
                "ACS artifact differs from pinned offline rebuild"
            )
        print("ACS artifact matches pinned offline rebuild")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded)
        print(
            f"Wrote {len(encoded):,} bytes; SHA256 {hashlib.sha256(encoded).hexdigest()}"
        )
    print(
        json.dumps(
            {
                "candidate": result["backtest"]["candidate_metrics"],
                "carry": result["backtest"]["carry_metrics"],
            }
        )
    )


if __name__ == "__main__":
    main()
