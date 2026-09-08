"""Generate the browser's inputs from the same validated offline release."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from spm_calculator.equivalence_scale import REFERENCE_RAW_SCALE
from spm_calculator.release import load_release

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web/public/data/release_config.json"


def build_config():
    release = load_release()
    document = release.to_dict()
    archived = json.loads(
        (ROOT / "web/public/data/spm_config.json").read_text()
    )
    version = re.search(
        r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M
    ).group(1)
    metro = document["geographies"]["metro"]
    latest = release.latest_published_year
    lookup = {}
    for kind in ("state", "county", "congressional_district"):
        geo = document["geographies"][kind]
        national = geo["national_median_rent"]
        lookup[kind] = {
            "year": geo["year"],
            "sourceId": geo["source_id"],
            "nationalMedianRent": national,
            "options": [
                {
                    "id": (
                        identity.zfill(4)
                        if kind == "congressional_district"
                        else identity
                    ),
                    "label": area["name"],
                    "shortLabel": area["name"].split(",")[0],
                    "medianRent": area["rent_index"] * national,
                }
                for identity, area in geo["areas"].items()
            ],
        }
    return {
        "packageVersion": version,
        "releaseMetadata": {
            "id": release.release_id,
            "sha256": release.content_sha256,
            "informationDate": document["information_date"],
        },
        "baseThresholds": {
            year: entry["thresholds"]
            for year, entry in document["years"].items()
        },
        "housingSharesByYear": {
            year: entry["housing_shares"]
            for year, entry in document["years"].items()
        },
        "housingShareProvenanceByYear": {
            year: entry["housing_share_provenance"]
            for year, entry in document["years"].items()
        },
        "methodology": {
            "housingShares": release.entry(latest)["housing_shares"],
            "equivalenceScale": {
                "singleAdultFirstChild": 0.8,
                "additionalChild": 0.5,
                "economiesOfScale": 0.7,
                "twoAdultNoChild": 1.41,
                "referenceFamilyRaw": REFERENCE_RAW_SCALE,
            },
        },
        "forecast": {"latestPublishedYear": latest, "cpiProjections": {}},
        "nowcast": {},
        "nowcastEvaluation": archived.get("nowcastEvaluation", {}),
        "paperUrl": archived["paperUrl"],
        "metroData": {
            "availableYears": [metro["year"]],
            "earliestYear": metro["year"],
            "latestYear": metro["year"],
        },
        "metroAreas": {
            identity: {
                "name": area["name"],
                "rentIndex": area["rent_index"],
                "adjustments": {
                    tenure: release.geography_factor(
                        latest, tenure, kind="metro", geoid=identity
                    )["factor"]
                    for tenure in release.entry(latest)["thresholds"]
                },
            }
            for identity, area in metro["areas"].items()
        },
        "metroDataYear": metro["year"],
        "metroSource": "Census Bureau SPM Thresholds by Metro Area 2024",
        "metroSourceUrl": next(
            s["url"]
            for s in document["sources"]
            if s["id"] == metro["source_id"]
        ),
        "acsLookup": lookup,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    encoded = (
        json.dumps(build_config(), indent=2, ensure_ascii=False) + "\n"
    ).encode()
    if args.check:
        if not OUT.exists() or OUT.read_bytes() != encoded:
            raise SystemExit("Browser inputs differ from the pinned release")
        print("Browser inputs match pinned release")
    else:
        OUT.write_bytes(encoded)
        print(OUT)


if __name__ == "__main__":
    main()
