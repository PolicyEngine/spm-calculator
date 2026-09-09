"""Export release inputs for official Census SPM areas to the browser."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from spm_calculator.equivalence_scale import REFERENCE_RAW_SCALE
from spm_calculator.release import load_release
from spm_calculator.rolling_forecast import load_forecast

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web/public/data/release_config.json"


def build_forecast_config(projection, *, base_release_sha256):
    """Export the same complete scenario entries as the offline consumer."""
    document = projection.to_dict()
    if document["base_release_sha256"] != base_release_sha256:
        raise ValueError("Forecast and published release anchors differ")
    latest = document["national_anchor_year"]
    default = document["default_scenario"]
    return {
        "method": document["method"],
        "baseYear": latest,
        "latestPublishedYear": latest,
        "baseReleaseSha256": base_release_sha256,
        "contentSha256": document["content_sha256"],
        "assumptionSha256": document["assumption_sha256"],
        "informationDate": document["information_date"],
        "cpiProjections": document["assumptions"]["price_projections"],
        "defaultScenario": default,
        "source": "CE and ACS rolling-window research projection",
        "uncertainty": "not estimated",
        "scenarios": {
            identity: {
                "label": scenario["label"],
                "realGrowthRate": scenario["real_growth_rate"],
                "years": scenario["years"],
            }
            for identity, scenario in document["scenarios"].items()
        },
        "thresholdsByYear": {
            year: entry["thresholds"]
            for year, entry in document["scenarios"][default]["years"].items()
            if int(year) > latest
        },
        "realGrowthDiagnostics": document["real_growth_diagnostics"],
        "validation": document["validation"],
        "rentSensitivity": document["rent_sensitivity"],
        "methodologyUrl": "https://github.com/PolicyEngine/spm-calculator/blob/ba808adc7e452ddc2411bbcb82c7f6dab3198c0f/docs/rolling-forecasts.md",
    }


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
    projection = load_forecast()
    # Census's workbook includes named MSAs and state residual Metro/Nonmetro
    # areas. Custom ACS rent estimates remain in the immutable Python release
    # for research replay but are not official SPM areas or browser inputs.
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
        "forecast": build_forecast_config(
            projection, base_release_sha256=release.content_sha256
        ),
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
