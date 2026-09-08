"""Build the portable release from pinned, committed source snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from spm_calculator.release import DEFAULT_RELEASE, seal_release

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "spm_calculator" / "data"
OUT = DATA / "releases" / f"{DEFAULT_RELEASE}.json"


def source(identity, path, url, published=None):
    return {
        "id": identity,
        "url": url,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "publication_date": published,
        "available_on": "2026-09-08",
        "availability_basis": "Conservative date of this pinned snapshot; not a reconstructed historical information set",
        "snapshot_path": str(path.relative_to(DATA)),
    }


def build_document():
    series = json.loads((DATA / "bls/threshold_series.json").read_text())[
        "series"
    ]["bls-corrected-2026-07-17"]
    metro_path = DATA / "metro_geoadj_2024.json"
    cd_path = DATA / "cd_geoadj_2023.json"
    metro = json.loads(metro_path.read_text())
    cd = json.loads(cd_path.read_text())
    acs_path = DATA / "acs_rents_2023.json"
    acs = json.loads(acs_path.read_text())
    if date.fromisoformat(acs["retrieved_on"]) > date(2026, 9, 8):
        raise ValueError(
            "ACS snapshot was retrieved after this release information date; create a new dated release"
        )
    acs_tables = {}
    for kind, rows in acs["raw_tables"].items():
        acs_tables[kind] = [dict(zip(rows[0], row)) for row in rows[1:]]
    national_rent = float(acs_tables["national"][0][acs["variable"]])
    extra_geographies = {}
    for kind in ("state", "county"):
        areas = {}
        excluded = []
        for row in acs_tables[kind]:
            identity = row["state"] + (
                row["county"] if kind == "county" else ""
            )
            rent = float(row[acs["variable"]])
            if rent <= 0:
                excluded.append(identity)
                continue
            areas[identity] = {
                "name": row["NAME"],
                "rent_index": rent / national_rent,
            }
        extra_geographies[kind] = {
            "id": f"acs5-2023-{kind}",
            "year": 2023,
            "source_id": "acs-rents-2023-snapshot",
            "national_median_rent": national_rent,
            "areas": areas,
            "excluded_nonpositive_rent_ids": excluded,
        }
    years = {}
    for segment_id, segment in series["segments"].items():
        for year, measures in segment["years"].items():
            years[year] = {
                "status": "published",
                "methodology_id": f"bls/{segment_id}",
                "available_on": "2026-09-08",
                "source_ids": [
                    (
                        "bls-2025"
                        if int(year) == 2025
                        else "bls-corrected-2005-2024"
                    ),
                    "census-metro-2024-snapshot",
                ],
                "thresholds": {
                    tenure: item["threshold"]
                    for tenure, item in measures.items()
                },
                "housing_shares": metro["housingShares"],
                "housing_share_provenance": {
                    "source_id": "census-metro-2024-snapshot",
                    "reference_year": 2024,
                    "status": "published" if year == "2024" else "carried",
                    "note": "Fixed three-decimal 2024 Census metro housing shares. Other target years carry these values as an approximation; they are not official target-year shares. Geography uses the published rent index with these shares, not an assertion of exact revised metro threshold reproduction.",
                },
                "uncertainty": {
                    "kind": "published_standard_error",
                    "standard_errors": {
                        tenure: item["standard_error"]
                        for tenure, item in measures.items()
                    },
                    "scope": "National threshold estimation only; no uncertainty estimate for housing-share carry or geographic approximation",
                },
            }
    document = {
        "schema_version": 1,
        "release_id": DEFAULT_RELEASE,
        "created_on": "2026-09-08",
        "information_date": "2026-09-08",
        "units": "USD/year",
        "reference_family": {"adults": 2, "children": 2},
        "description": "Corrected BLS national thresholds through published 2025, with separately identified 2024 housing shares and pinned geographic rent indices. Historical entries reflect this release's revised information set.",
        "sources": [
            source(
                "bls-corrected-2005-2024",
                DATA / "bls/spm_threshold_200524_corrected.xlsx",
                "https://www.bls.gov/pir/spm/spm_threshold_200524_corrected.xlsx",
                "2026-07-17",
            ),
            source(
                "bls-2025",
                DATA / "bls/spm_thresholds.xlsx",
                "https://www.bls.gov/pir/spm/spm_thresholds.xlsx",
                "2026-08-24",
            ),
            source(
                "census-metro-2024-snapshot", metro_path, metro["sourceUrl"]
            ),
            source(
                "acs-cd-2023-snapshot",
                cd_path,
                "https://api.census.gov/data/2023/acs/acs5/groups/B25031.html",
            ),
            source("acs-rents-2023-snapshot", acs_path, acs["source_url"]),
        ],
        "years": years,
        "geographies": {
            **extra_geographies,
            "metro": {
                "id": "census-spm-metro-2024",
                "year": 2024,
                "source_id": "census-metro-2024-snapshot",
                "areas": {
                    key: {
                        "name": item["name"],
                        "rent_index": item["rentIndex"],
                    }
                    for key, item in metro["metroAreas"].items()
                },
            },
            "congressional_district": {
                "id": "acs5-2023-cd-118",
                "year": 2023,
                "source_id": "acs-cd-2023-snapshot",
                "national_median_rent": cd["national_median_2br_rent"],
                "areas": {
                    key: {
                        "name": item["name"],
                        "rent_index": item["median_2br_rent"]
                        / cd["national_median_2br_rent"],
                    }
                    for key, item in cd["congressional_districts"].items()
                },
            },
        },
    }
    return seal_release(document)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    encoded = (
        json.dumps(build_document(), indent=2, ensure_ascii=False) + "\n"
    ).encode()
    if args.check:
        if not OUT.exists() or OUT.read_bytes() != encoded:
            raise SystemExit(
                "Bundled release differs from its pinned source snapshots"
            )
        print("Bundled release matches pinned sources")
    else:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_bytes(encoded)
        print(OUT)


if __name__ == "__main__":
    main()
