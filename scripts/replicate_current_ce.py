"""Replay cached CE 2019–2025 windows with explicit sample policies.

This writes a CURRENT retrospective source replication against published
thresholds. No network requests are made. Every zip/member and CPI input
is hashed, and original CE availability dates remain explicitly unknown.
Output defaults to benchmark_output/ce_source_replication_2019_2025.json;
the archived package receipt is immutable.
Run: uv run --no-sync python scripts/replicate_current_ce.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from spm_calculator.ce_threshold import (
    bls_quarter_window,
    load_ce_quarter,
    normalize_ce_sample,
    replicate_thresholds,
)
from spm_calculator.published_thresholds import get_published_thresholds

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "benchmark_output/ce_source_replication_2019_2025.json"
ARCHIVED_RECEIPT = (
    ROOT / "spm_calculator/data/current/ce_replication_2019_2025.json"
)
KEEP = {
    "NEWID",
    "AGE_REF",
    "PERSLT18",
    "FAM_SIZE",
    "CUTENURE",
    "FINLWT21",
    "ce_year",
    "ce_quarter",
    "FOODPQ",
    "FOODCQ",
    "FDHOMEPQ",
    "FDHOMECQ",
    "FDAWAYPQ",
    "FDAWAYCQ",
    "GROCERPQ",
    "GROCERCQ",
    "APPARPQ",
    "APPARCQ",
    "SHELTPQ",
    "SHELTCQ",
    "UTILPQ",
    "UTILCQ",
    "TELEPHPQ",
    "TELEPHCQ",
    "EMRTPNOP",
    "EMRTPNOC",
    "MRTPRNOP",
    "MRTPRNOC",
}
VARIANTS = {
    "exclude_unresolved": {},
    "legacy_youth_recode_sensitivity": {"youth_policy": "legacy_recode"},
    "code3_no_mortgage_sensitivity": {
        "tenure_policy": "exclude_5_6_code3_no_mortgage"
    },
    "include_5_6_as_renter_sensitivity": {
        "tenure_policy": "include_5_6_as_renter"
    },
}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache/spm-calculator/ce-pumd",
    )
    parser.add_argument(
        "--cpi-input",
        type=Path,
        default=ROOT / "spm_calculator/data/bls/cpi_annual.json",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.output.resolve() == ARCHIVED_RECEIPT.resolve():
        parser.error("--output cannot overwrite the archived package receipt")
    as_of = datetime.now(timezone.utc).date().isoformat()
    cpi_document = json.loads(args.cpi_input.read_text())
    cpi_series = {
        sid: pd.Series({int(year): value for year, value in values.items()})
        for sid, values in cpi_document["series"].items()
    }
    quarters, sources, bundles, results = {}, {}, {}, {}
    for year in range(2019, 2026):
        print(f"Loading cached CE window for {year}", flush=True)
        window = bls_quarter_window(year)
        for quarter in window:
            if quarter in quarters:
                continue
            raw = load_ce_quarter(
                *quarter, cache_dir=args.cache_dir, allow_download=False
            )
            source = raw.attrs["source"]
            bundle = Path(source["bundle_path"])
            if bundle.name not in bundles:
                bundles[bundle.name] = {
                    "sha256": sha256(bundle),
                    "url": source["url"],
                    "size_bytes": bundle.stat().st_size,
                    "original_publication_date": None,
                    "publication_date_status": "unknown",
                    "verified_present_on": as_of,
                }
            with zipfile.ZipFile(bundle) as archive:
                member_sha = hashlib.sha256(
                    archive.read(source["member"])
                ).hexdigest()
            key = f"{quarter[0]}Q{quarter[1]}"
            sources[key] = {
                "bundle": bundle.name,
                "member": source["member"],
                "sha256": member_sha,
                "raw_rows": len(raw),
            }
            quarters[quarter] = raw[
                [column for column in raw.columns if column in KEEP]
            ].copy()
            quarters[quarter].attrs = {}
        ce = pd.concat(
            [quarters[quarter] for quarter in window], ignore_index=True
        )
        try:
            normalize_ce_sample(ce)
        except ValueError as error:
            exact_error = str(error)
        else:
            exact_error = None
        variants = {}
        for name, settings in VARIANTS.items():
            options = {"youth_policy": "exclude_unresolved", **settings}
            result = replicate_thresholds(
                ce, year, cpi_series=cpi_series, **options
            )
            variants[name] = result
        baseline = variants["exclude_unresolved"]["thresholds"]
        actual = get_published_thresholds(year)
        sensitivity = {
            name: {
                tenure: 100
                * (result["thresholds"][tenure] / baseline[tenure] - 1)
                for tenure in baseline
            }
            for name, result in variants.items()
            if name != "exclude_unresolved"
        }
        results[str(year)] = {
            "quarters": [f"{y}Q{q}" for y, q in window],
            "exact_mode_error": exact_error,
            "variants": variants,
            "published": actual,
            "replication_deviation_percent": {
                tenure: 100 * (baseline[tenure] / actual[tenure] - 1)
                for tenure in baseline
            },
            "sensitivity_change_percent_from_exclusion": sensitivity,
        }
        if year == 2024:
            duplicate = pd.concat([quarters[q] for q in window])
            duplicate_result = replicate_thresholds(
                duplicate,
                year,
                youth_policy="exclude_unresolved",
                cpi_series=cpi_series,
            )
            if duplicate_result["thresholds"] != baseline:
                raise RuntimeError(
                    "Duplicate-index regression on real CE failed"
                )
            results[str(year)]["duplicate_index_check"] = {
                "index_unique": duplicate.index.is_unique,
                "identical_thresholds": True,
            }
        print(
            json.dumps(
                {
                    "year": year,
                    "thresholds": baseline,
                    "youth_rows": variants["exclude_unresolved"]["sample"][
                        "unresolved_youth"
                    ]["rows"],
                    "sensitivity_percent": sensitivity,
                }
            ),
            flush=True,
        )
    code_paths = [
        "spm_calculator/ce_threshold.py",
        "spm_calculator/fcsuti_cpi.py",
        "spm_calculator/equivalence_scale.py",
        "spm_calculator/published_thresholds.py",
        "scripts/replicate_current_ce.py",
    ]
    doc = {
        "schema_version": 2,
        "generated_by": "scripts/replicate_current_ce.py",
        "generated_on": as_of,
        "classification": "current_retrospective_research",
        "frozen_commitments_modified": False,
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "code_sha256": {path: sha256(ROOT / path) for path in code_paths},
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
        "cpi_input": {
            "path": (
                "spm_calculator/data/bls/cpi_annual.json"
                if args.cpi_input.resolve()
                == (ROOT / "spm_calculator/data/bls/cpi_annual.json").resolve()
                else args.cpi_input.name
            ),
            "sha256": sha256(args.cpi_input),
            "retrieved": cpi_document.get("retrieved"),
            "sources": cpi_document.get("sources"),
            "note": cpi_document.get("note"),
        },
        "published_threshold_input": {
            "path": "spm_calculator/data/bls/threshold_series.json",
            "sha256": sha256(
                ROOT / "spm_calculator/data/bls/threshold_series.json"
            ),
            "series_id": "bls-corrected-2026-07-17",
            "selection": "published source splice with 2025 continuation",
        },
        "source_bundles": bundles,
        "source_quarters": sources,
        "sample_policy_sources": [
            {
                "url": "https://www.bls.gov/cex/csxgloss.htm",
                "finding": "CU membership can include financially independent minors; does not establish SPM A=0 treatment",
            },
            {
                "url": "https://www.bls.gov/pir/spmhome.htm",
                "finding": "Child-CU sample and adult-count formulas described; exact minor-only classification not established",
            },
            {
                "url": "https://www.bls.gov/cex/pumd/ce-pumd-interview-diary-dictionary.xlsx",
                "finding": "CUTENURE six-code definitions; exact SPM sample treatment for 3/5/6 not established",
            },
        ],
        "results": results,
        "limitations": [
            "Youth sensitivity compares explicit assumptions; it does not identify the correct BLS classification",
            "Tenure sensitivity changes assignment/exclusion policy; official BLS handling remains unverified",
            "Annual CPI treatment, post-redesign food allocation, internet/benefit omissions and percentile convention remain approximations",
            "No sampling replicate weights or imputation uncertainty estimated",
            "CE original publication/revision dates are unknown; these are current cached vintages, not reconstructed real-time inputs",
            "Raw weight sums are CU-interview mass over overlapping windows, not unique national population totals",
            "Source replication only; this receipt does not construct forecasts or commitments",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(doc, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(f"Saved {args.output} sha256={sha256(args.output)}", flush=True)


if __name__ == "__main__":
    main()
