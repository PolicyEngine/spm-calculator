"""Regenerate ``spm_calculator/data/bls/threshold_series.json`` from BLS.

The packaged threshold series must never be hand-edited: this script is
the only writer. It parses the frozen corrected 2005--2024 workbook and
the current workbook (both bundled next to the output, with their
SHA-256 digests recorded in provenance) and emits the full-precision
series -- thresholds, standard errors, and tenure population shares --
for every year BLS publishes. A small checked-in JSON source records the
rounded values and growth rates on BLS's 2025 publication page; the
generator verifies those against the full-precision workbook values.

Usage:
    uv run --with openpyxl python scripts/build_threshold_series.py

To ingest a future BLS release, replace the bundled current workbook,
update its page metadata source, and re-run. Never replace the frozen
correction workbook: it is an immutable source for 2005--2024.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import openpyxl

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "spm_calculator" / "data" / "bls"
WORKBOOK = DATA_DIR / "spm_threshold_200524_corrected.xlsx"
CURRENT_WORKBOOK = DATA_DIR / "spm_thresholds.xlsx"
PAGE_2025_SOURCE = DATA_DIR / "spm_thresholds_2025_page.json"
OUTPUT = DATA_DIR / "threshold_series.json"

SOURCE_URL = "https://www.bls.gov/pir/spm/spm_threshold_200524_corrected.xlsx"
LANDING_URL = "https://www.bls.gov/pir/spm/spm_thresholds_2024_correction.htm"
RETRIEVED = "2026-07-17"
PUBLISHED = "2026-07-17"

CURRENT_WORKBOOK_URL = "https://www.bls.gov/pir/spm/spm_thresholds.xlsx"
CURRENT_WORKBOOK_LANDING_URL = "https://www.bls.gov/pir/spmhome.htm"
CURRENT_WORKBOOK_RETRIEVED = "2026-09-04"

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


def _validate_complete(bucket: dict, expected_years: set[str]) -> None:
    """Validate the years, tenures, and measures parsed from a workbook."""
    assert set(bucket) == expected_years, sorted(bucket)
    for year, tenures in bucket.items():
        assert set(tenures) == set(TENURES.values()), (year, tenures)
        for measures in tenures.values():
            assert set(measures) == set(MEASURES.values())


def build_document() -> dict:
    """Build and validate the generated threshold-series document.

    Keeping construction separate from :func:`main` lets tests regenerate
    the document in memory and compare every workbook-derived value with
    the committed artifact.
    """
    sha256 = hashlib.sha256(WORKBOOK.read_bytes()).hexdigest()
    published, revised = parse_workbook(WORKBOOK)
    current_sha256 = hashlib.sha256(CURRENT_WORKBOOK.read_bytes()).hexdigest()
    current_published, current_revised = parse_workbook(CURRENT_WORKBOOK)
    page_2025 = json.loads(PAGE_2025_SOURCE.read_text())

    expected_published = set(str(y) for y in range(2005, 2020))
    expected_revised = set(str(y) for y in range(2019, 2025))
    _validate_complete(published, expected_published)
    _validate_complete(revised, expected_revised)
    _validate_complete(current_published, expected_published)
    _validate_complete(current_revised, set(str(y) for y in range(2019, 2026)))

    # The permanent 2005--2024 source remains the correction-vintage
    # workbook. Refuse to regenerate if BLS's rolling workbook disagrees;
    # this guarantees those already-published values remain byte-identical.
    assert current_published == published
    assert {
        year: current_revised[year] for year in expected_revised
    } == revised

    published_2025 = {"2025": current_revised["2025"]}
    for tenure, page_value in page_2025["thresholds"].items():
        workbook_value = published_2025["2025"][tenure]["threshold"]
        assert round(workbook_value) == page_value, (
            tenure,
            workbook_value,
            page_value,
        )
        growth = (
            workbook_value / revised["2024"][tenure]["threshold"] - 1
        ) * 100
        assert (
            round(growth, 3) == page_2025["bls_stated_growth_percent"][tenure]
        ), (tenure, growth)

    doc = {
        "generated_by": "scripts/build_threshold_series.py",
        "default_series": "bls-corrected-2026-07-17",
        "series": {
            "bls-corrected-2026-07-17": {
                "label": (
                    "BLS SPM thresholds: corrected 2005-2024 series "
                    "and published 2025 continuation"
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
                    "splice": (
                        "Published-methodology workbook values through 2018; "
                        "2019-2024 from the corrected workbook's revised "
                        "segment; 2025 from the current BLS workbook, "
                        "cross-checked against the 2025 publication page."
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
                    "bls-published-2025": {
                        "provenance": {
                            "source_url": CURRENT_WORKBOOK_URL,
                            "landing_url": CURRENT_WORKBOOK_LANDING_URL,
                            "sha256": current_sha256,
                            "retrieved": CURRENT_WORKBOOK_RETRIEVED,
                            "page_source_url": page_2025["source_url"],
                            "page_retrieved": page_2025["retrieved"],
                            "page_last_modified": page_2025[
                                "page_last_modified"
                            ],
                            "precision": page_2025["precision"],
                            "bls_stated_growth_percent": page_2025[
                                "bls_stated_growth_percent"
                            ],
                            "page_whole_dollar_thresholds": page_2025[
                                "thresholds"
                            ],
                            "note": (
                                "The current BLS workbook supplies full-"
                                "precision thresholds, standard errors, and "
                                "tenure shares. Its values round to the "
                                "whole-dollar values on BLS's 2025 page."
                            ),
                        },
                        "methodology": {
                            "expenditures": (
                                "FCSUti out-of-pocket plus imputed in-kind "
                                "benefits"
                            ),
                            "anchor": (
                                "82% of mean FCSUti within the 47th-53rd "
                                "percentile range"
                            ),
                            "median_share": 0.82,
                            "price_index": "FCSUti composite CPI-U",
                            "ce_window": "(T-5)Q2 through (T)Q1",
                        },
                        "years": published_2025,
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

    return doc


def main() -> None:
    doc = build_document()
    OUTPUT.write_text(json.dumps(doc, indent=2, sort_keys=False) + "\n")
    segments = doc["series"]["bls-corrected-2026-07-17"]["segments"]
    n_years = sum(len(segment["years"]) for segment in segments.values())
    print(f"Wrote {OUTPUT} ({n_years} year-columns across all segments)")


if __name__ == "__main__":
    main()
