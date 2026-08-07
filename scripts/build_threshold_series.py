"""Regenerate ``spm_calculator/data/bls/threshold_series.json`` from the
bundled BLS workbook.

The packaged threshold series must never be hand-edited: this script is
the only writer. It parses the official BLS SPM-thresholds workbook
(bundled next to the output, with its SHA-256 recorded in the output's
provenance block) and emits the full-precision series — thresholds,
standard errors, and tenure population shares — for every year BLS
publishes.

Usage:
    uv run --with openpyxl python scripts/build_threshold_series.py

To ingest a future BLS release, drop the new workbook into
``spm_calculator/data/bls/``, update ``WORKBOOK`` and the provenance
constants below, and re-run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import openpyxl

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "spm_calculator" / "data" / "bls"
WORKBOOK = DATA_DIR / "spm_threshold_200524_corrected.xlsx"
OUTPUT = DATA_DIR / "threshold_series.json"

SOURCE_URL = "https://www.bls.gov/pir/spm/spm_threshold_200524_corrected.xlsx"
LANDING_URL = "https://www.bls.gov/pir/spm/spm_thresholds_2024_correction.htm"
RETRIEVED = "2026-07-17"
PUBLISHED = "2026-07-17"

TENURES = {
    "Owners with mortgages": "owner_with_mortgage",
    "Owners without mortgages": "owner_without_mortgage",
    "Renters": "renter",
}
MEASURES = {
    "Threshold": "threshold",
    "Standard error": "standard_error",
    "Percentage of Weighted Sample": "tenure_share",
}

# Pre-correction thresholds as Census published them, transcribed from
# the P60 annual poverty reports (each year cross-verified against two
# consecutive reports, which print prior- and current-year columns).
# Superseded by the corrected series for analysis; retained because
# every SPM statistic Census published for 2019-2024 used these.
PUBLISHED_PRE_CORRECTION = {
    2019: {
        "owner_with_mortgage": {"threshold": 29080, "standard_error": 210},
        "owner_without_mortgage": {"threshold": 24413, "standard_error": 344},
        "renter": {"threshold": 29194, "standard_error": 179},
    },
    2020: {
        "owner_with_mortgage": {"threshold": 29959, "standard_error": 241},
        "owner_without_mortgage": {"threshold": 25222, "standard_error": 402},
        "renter": {"threshold": 30150, "standard_error": 255},
    },
    2021: {
        "owner_with_mortgage": {"threshold": 31107, "standard_error": 280},
        "owner_without_mortgage": {"threshold": 26279, "standard_error": 284},
        "renter": {"threshold": 31453, "standard_error": 231},
    },
    2022: {
        "owner_with_mortgage": {"threshold": 34235, "standard_error": 307},
        "owner_without_mortgage": {"threshold": 28909, "standard_error": 525},
        "renter": {"threshold": 34518, "standard_error": 303},
    },
    2023: {
        "owner_with_mortgage": {"threshold": 36915, "standard_error": 316},
        "owner_without_mortgage": {"threshold": 30870, "standard_error": 612},
        "renter": {"threshold": 37482, "standard_error": 415},
    },
    2024: {
        "owner_with_mortgage": {"threshold": 39068, "standard_error": 320},
        "owner_without_mortgage": {"threshold": 32586, "standard_error": 638},
        "renter": {"threshold": 39430, "standard_error": 327},
    },
}

PUBLISHED_PRE_CORRECTION_SOURCES = [
    "P60-275 (The Supplemental Poverty Measure: 2020, Sept 2021): "
    "2019 revised + 2020",
    "P60-277 (Poverty in the United States: 2021, Sept 2022): 2020 + 2021",
    "P60-280 (Poverty in the United States: 2022, Sept 2023): 2021 + 2022",
    "P60-283 (Poverty in the United States: 2023, Sept 2024): 2022 + 2023",
    "P60-287 (Poverty in the United States: 2024, Sept 2025): 2023 + 2024",
]

# Values shipped in spm-calculator <= 0.3.1, retained verbatim so prior
# results stay reproducible. Only 2024 matches the Census-published
# series above; 2019-2020 and 2022-2023 are off by 2-8% and appear to
# mix misattributed vintages (see docs/bls-2026-correction.md). Do not
# extend.
PACKAGE_LEGACY_0_3 = {
    2015: {
        "renter": 25155,
        "owner_with_mortgage": 24859,
        "owner_without_mortgage": 20639,
    },
    2016: {
        "renter": 25558,
        "owner_with_mortgage": 25248,
        "owner_without_mortgage": 20943,
    },
    2017: {
        "renter": 26213,
        "owner_with_mortgage": 25897,
        "owner_without_mortgage": 21527,
    },
    2018: {
        "renter": 26905,
        "owner_with_mortgage": 26565,
        "owner_without_mortgage": 22095,
    },
    2019: {
        "renter": 27515,
        "owner_with_mortgage": 27172,
        "owner_without_mortgage": 22600,
    },
    2020: {
        "renter": 28881,
        "owner_with_mortgage": 28533,
        "owner_without_mortgage": 23948,
    },
    2021: {
        "renter": 31453,
        "owner_with_mortgage": 31089,
        "owner_without_mortgage": 26022,
    },
    2022: {
        "renter": 33402,
        "owner_with_mortgage": 32949,
        "owner_without_mortgage": 27679,
    },
    2023: {
        "renter": 36606,
        "owner_with_mortgage": 36192,
        "owner_without_mortgage": 30347,
    },
    2024: {
        "renter": 39430,
        "owner_with_mortgage": 39068,
        "owner_without_mortgage": 32586,
    },
}


def parse_workbook(path: Path) -> tuple[dict, dict]:
    """Return (published_2005_2019, revised_2019_2024) year dicts."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.worksheets[0]
    rows = [[c for c in row] for row in ws.iter_rows(values_only=True)]

    header = next(r for r in rows if r[0] == "Housing Tenure and Data Type")
    # Columns are labeled 2005..2018, "2019 Published", "2019 Revised",
    # 2020..2024. Keep the label so the two 2019 columns stay distinct.
    columns: list[tuple[int, str]] = []
    for idx, label in enumerate(header):
        if idx == 0 or label is None:
            continue
        columns.append((idx, str(label).strip()))

    published: dict[str, dict] = {}
    revised: dict[str, dict] = {}
    for row in rows:
        label = row[0]
        if not isinstance(label, str):
            continue
        for tenure_label, tenure_key in TENURES.items():
            if not label.startswith(tenure_label):
                continue
            measure_label = label[len(tenure_label) :].strip()
            measure = MEASURES.get(measure_label)
            if measure is None:
                continue
            for idx, col_label in columns:
                value = row[idx]
                if value is None:
                    continue
                value = float(value)
                if col_label == "2019 Published":
                    bucket, year = published, "2019"
                elif col_label == "2019 Revised":
                    bucket, year = revised, "2019"
                else:
                    year = col_label
                    bucket = published if int(year) <= 2018 else revised
                bucket.setdefault(year, {}).setdefault(tenure_key, {})[
                    measure
                ] = value

    return published, revised


def main() -> None:
    sha256 = hashlib.sha256(WORKBOOK.read_bytes()).hexdigest()
    published, revised = parse_workbook(WORKBOOK)

    expected_published = set(str(y) for y in range(2005, 2020))
    expected_revised = set(str(y) for y in range(2019, 2025))
    assert set(published) == expected_published, sorted(published)
    assert set(revised) == expected_revised, sorted(revised)
    for bucket in (published, revised):
        for year, tenures in bucket.items():
            assert set(tenures) == set(TENURES.values()), (year, tenures)
            for measures in tenures.values():
                assert set(measures) == set(MEASURES.values())

    doc = {
        "generated_by": "scripts/build_threshold_series.py",
        "default_series": "bls-corrected-2026-07-17",
        "series": {
            "bls-corrected-2026-07-17": {
                "label": (
                    "BLS SPM thresholds, corrected series published 2026-07-17"
                ),
                "provenance": {
                    "source_url": SOURCE_URL,
                    "landing_url": LANDING_URL,
                    "sha256": sha256,
                    "retrieved": RETRIEVED,
                    "published": PUBLISHED,
                    "note": (
                        "BLS reissued 2019-2024 thresholds on 2026-07-17 "
                        "after finding errors in the code that produced "
                        "them (introduced with the 2021 methodology "
                        "change) and re-anchored the revised-methodology "
                        "series at 82% (previously 83%) of the 47th-53rd "
                        "percentile FCSUti average to minimize the series "
                        "break. Workbook footnote 1: these are the "
                        "thresholds Census uses to produce SPM poverty "
                        "statistics."
                    ),
                },
                "segments": {
                    "published_2005_2019": {
                        "methodology": {
                            "expenditures": "FCSU out-of-pocket",
                            "anchor": "30th-36th percentile range",
                            "price_index": "All-Items CPI-U",
                            "ce_window": "(T-4)Q2 through (T+1)Q1",
                        },
                        "years": published,
                    },
                    "revised_2019_2024": {
                        "methodology": {
                            "expenditures": (
                                "FCSUti out-of-pocket plus imputed "
                                "in-kind benefits (broadband, LIHEAP, "
                                "NSLP, WIC, rental assistance)"
                            ),
                            "anchor": (
                                "82% of mean FCSUti within the 47th-53rd "
                                "percentile range (83% before the "
                                "2026-07-17 correction)"
                            ),
                            "median_share": 0.82,
                            "price_index": "FCSUti composite CPI-U",
                            "ce_window": "(T-5)Q2 through (T)Q1",
                        },
                        "years": revised,
                    },
                },
            },
            "census-published-pre-correction": {
                "label": (
                    "Thresholds as published before the 2026-07-17 "
                    "correction (Census P60 reports)"
                ),
                "provenance": {
                    "sources": PUBLISHED_PRE_CORRECTION_SOURCES,
                    "note": (
                        "Every SPM statistic Census published for "
                        "2019-2024 used these thresholds; superseded by "
                        "the corrected series on 2026-07-17. Census will "
                        "re-release 2019-2024 SPM estimates before the "
                        "September 2026 poverty report. P60-280 notes "
                        "the 2022 thresholds already reflected an "
                        "earlier round of computer-code corrections to "
                        "in-kind benefit estimation."
                    ),
                },
                "years": {
                    str(year): tenures
                    for year, tenures in PUBLISHED_PRE_CORRECTION.items()
                },
            },
            "package-legacy-0.3": {
                "label": "Values shipped in spm-calculator <= 0.3.1",
                "provenance": {
                    "note": (
                        "Hand-entered values retained verbatim for "
                        "reproducibility of results produced with "
                        "spm-calculator <= 0.3.1. 2022 and 2023 match "
                        "no BLS or Census publication; superseded by "
                        "the corrected series."
                    ),
                },
                "years": {
                    str(year): {
                        tenure: {"threshold": float(value)}
                        for tenure, value in tenures.items()
                    }
                    for year, tenures in PACKAGE_LEGACY_0_3.items()
                },
            },
        },
    }

    OUTPUT.write_text(json.dumps(doc, indent=2, sort_keys=False) + "\n")
    n_years = len(published) + len(revised)
    print(f"Wrote {OUTPUT} ({n_years} year-columns, sha256 {sha256[:12]}...)")


if __name__ == "__main__":
    main()
