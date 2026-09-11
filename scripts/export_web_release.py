"""Export compact UI inputs and a byte-identical pinned scientific download.

The browser needs calculation inputs, provenance and displayed warning/fit
summaries, not scientific fold records, donor records or county assignments.
Publication is explicit: only set SPM_PUBLISHED_PACKAGE_VERSION (or the CLI
flag) after that exact version is on PyPI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

from spm_calculator.equivalence_scale import REFERENCE_RAW_SCALE
from spm_calculator.rolling_forecast import SPMForecast

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web/public/data/release_config.json"
FORECAST = (
    ROOT / "spm_calculator/data/current/rolling_forecast_2026_09_09.json"
)

# These fields are consumed by CalculatorWorkbench and ForecastDiagnostics.
# Keep numeric values verbatim; add newly displayed diagnostics here explicitly.
MEDIAN_FIELDS = (
    "thin_support",
    "rent_index_topcode_warning",
    "material_topcoding",
    "material_topcoding_flag",
    "materialTopcoding",
    "materialTopcodingFlag",
    "topcoding_material",
    "topcoding_material_flag",
    "topcoded_weight_share",
    "unique_records",
    "kish_effective_count",
)
METRIC_FIELDS = (
    "mean_absolute_percentage_error",
    "horizon_balanced_mean_absolute_percentage_error",
    "beats_baseline",
    "beats_horizon_balanced_baseline",
)
GEOGRAPHY_FIELDS = ("rent_indices", "geography_by_area", "median_diagnostics")


def pick(mapping, fields):
    return {key: mapping[key] for key in fields if key in mapping}


def package_distribution(version, published_package_version=None):
    """Never advertise an unrelated or unconfirmed package as this build."""
    if published_package_version is not None:
        if published_package_version != version:
            raise ValueError(
                "Published package version must match pyproject.toml "
                f"({version})"
            )
        return {
            "status": "published",
            "version": version,
            "publishedVersion": version,
            "pypiUrl": f"https://pypi.org/project/spm-calculator/{version}/",
        }
    return {
        "status": "local_preview",
        "version": version,
        "publishedVersion": None,
        "pypiUrl": None,
    }


def compact_entry(entry):
    result = pick(
        entry,
        (
            "thresholds",
            "housing_shares",
            "rent_indices",
            "geography_by_area",
            "national_status",
            "national_source_ids",
            "geography_status",
            "housing_share_status",
            "housing_share_source_ids",
        ),
    )
    result["ce_window"] = pick(
        entry["ce_window"],
        (
            "start",
            "end",
            "observed_quarters",
            "projected_quarters",
        ),
    )
    result["acs_window"] = pick(
        entry["acs_window"],
        (
            "start",
            "end",
            "observed_years",
            "projected_years",
        ),
    )
    # Metadata is small and includes source IDs, vintages and series breaks.
    # Remove embedded scientific diagnostics if a future artifact puts them here.
    result["geography_by_area"] = {
        area_id: {
            key: value for key, value in area.items() if key != "diagnostics"
        }
        for area_id, area in entry["geography_by_area"].items()
    }
    result["median_diagnostics"] = {}
    for area_id, area in entry["geography_by_area"].items():
        if area["status"] == "published_anchor":
            continue
        diagnostic = area.get(
            "diagnostics", entry.get("median_diagnostics", {}).get(area_id, {})
        )
        compact = pick(diagnostic, MEDIAN_FIELDS)
        share = compact.get("topcoded_weight_share")
        has_share = isinstance(share, (int, float)) and 0 < share <= 1
        if has_share or any(
            compact.get(key) is True for key in MEDIAN_FIELDS[:8]
        ):
            result["median_diagnostics"][area_id] = compact
    return result


def compact_validation(validation):
    ce = validation["ce"]
    return {
        "ce": {
            **pick(ce, ("status", "unvalidated", "metric")),
            "baseline": pick(ce["baseline"], METRIC_FIELDS),
            "scenarios": {
                key: pick(value, METRIC_FIELDS)
                for key, value in ce["scenarios"].items()
            },
            "by_horizon": {
                key: {
                    "fold_count": value["fold_count"],
                    "baseline": pick(value["baseline"], METRIC_FIELDS),
                    "scenarios": {
                        identity: pick(score, METRIC_FIELDS)
                        for identity, score in value["scenarios"].items()
                    },
                }
                for key, value in ce["by_horizon"].items()
            },
        },
        "acs": validation["acs"],
    }


def build_forecast_config(document):
    """Select actual UI inputs without re-estimating any scientific values."""
    return {
        "schemaVersion": document["schema_version"],
        "id": document["forecast_id"],
        "method": document["method"],
        "baseYear": document["national_anchor_year"],
        "latestPublishedYear": document["national_anchor_year"],
        "geographyAnchorYear": document["assumptions"]["acs"][
            "anchor_spm_year"
        ],
        "baseReleaseSha256": document["base_release_sha256"],
        "contentSha256": document["content_sha256"],
        "assumptionSha256": document["assumption_sha256"],
        "componentSha256": document["component_sha256"],
        "codeSha256": document["code_sha256"],
        "informationDate": document["information_date"],
        "createdOn": document["created_on"],
        "cpiProjections": document["assumptions"]["price_projections"],
        "defaultScenario": document["default_scenario"],
        "scenarios": {
            identity: {
                "label": scenario["label"],
                "realGrowthRate": scenario["real_growth_rate"],
                "years": {
                    year: compact_entry(entry)
                    for year, entry in scenario["years"].items()
                },
            }
            for identity, scenario in document["scenarios"].items()
        },
        "sources": [
            pick(source, ("id", "title", "label", "url", "sha256"))
            for source in document["sources"]
        ],
        "realGrowthDiagnostics": {
            "fits": [
                pick(
                    fit,
                    ("label", "realGrowthRate", "olsSlopeStandardError", "n"),
                )
                for fit in document["real_growth_diagnostics"]["fits"]
            ],
        },
        "validation": compact_validation(document["validation"]),
    }


def build_config(*, published_package_version=None, source_bytes=None):
    """Build the expanded UI contract from one hash-validated source snapshot."""
    if source_bytes is None:
        source_bytes = FORECAST.read_bytes()
    projection = SPMForecast.from_dict(json.loads(source_bytes))
    document = projection.to_dict()
    version_match = re.search(
        r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M
    )
    if version_match is None:
        raise ValueError("pyproject.toml must identify the package version")
    version = version_match.group(1)
    forecast = build_forecast_config(document)
    file_hash = hashlib.sha256(source_bytes).hexdigest()
    audit_name = f"rolling-forecast-{file_hash}.json"
    forecast["auditArtifact"] = {
        "name": audit_name,
        "url": f"/data/canonical/{audit_name}",
        "sha256": file_hash,
        "bytes": len(source_bytes),
    }
    return {
        "schemaVersion": 2,
        "packageVersion": version,
        "packageDistribution": package_distribution(
            version, published_package_version
        ),
        "availableYears": list(projection.years),
        "areasByYear": {
            str(year): {
                area_id: pick(area, ("name", "area_type"))
                for area_id, area in projection.areas_for_year(year).items()
            }
            for year in projection.years
        },
        "methodology": {
            "equivalenceScale": {
                "singleAdultFirstChild": 0.8,
                "additionalChild": 0.5,
                "economiesOfScale": 0.7,
                "twoAdultNoChild": 1.41,
                "referenceFamilyRaw": REFERENCE_RAW_SCALE,
            },
        },
        "forecast": forecast,
    }


def encode_config(config):
    """Intern only exactly equal geography/menu records, with no rounding.

    The small pools are expanded once after fetch by loadCalculatorData.js.
    Scenario/year calculation inputs stay explicit; future differing geography
    gets its own pool entry instead of assuming scenarios always share indices.
    """
    pools = {"areaMenus": [], "geographies": []}
    identities = {key: {} for key in pools}

    def intern(pool, value):
        key = json.dumps(value, sort_keys=True, separators=(",", ":"))
        if key not in identities[pool]:
            identities[pool][key] = len(pools[pool])
            pools[pool].append(value)
        return identities[pool][key]

    result = {
        key: value
        for key, value in config.items()
        if key not in ("areasByYear", "forecast")
    }
    result["uiSchemaVersion"] = 1
    result["areaMenuByYear"] = {
        year: intern("areaMenus", areas)
        for year, areas in config["areasByYear"].items()
    }
    result["forecast"] = {
        **config["forecast"],
        "scenarios": {
            identity: {
                **scenario,
                "years": {
                    year: {
                        **{
                            key: value
                            for key, value in entry.items()
                            if key not in GEOGRAPHY_FIELDS
                        },
                        "geographyRef": intern(
                            "geographies", pick(entry, GEOGRAPHY_FIELDS)
                        ),
                    }
                    for year, entry in scenario["years"].items()
                },
            }
            for identity, scenario in config["forecast"]["scenarios"].items()
        },
    }
    result.update(pools)
    return (
        json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode()


def export(*, check=False, published_package_version=None):
    source_bytes = FORECAST.read_bytes()
    config = build_config(
        published_package_version=published_package_version,
        source_bytes=source_bytes,
    )
    encoded = encode_config(config)
    # Another lane regenerates this artifact. Never mix revisions or copy a
    # different revision than the one used to derive the UI payload.
    if FORECAST.read_bytes() != source_bytes:
        raise SystemExit(
            "Canonical artifact changed during export; regenerate after it stabilizes"
        )
    audit = (
        OUT.parent / "canonical" / config["forecast"]["auditArtifact"]["name"]
    )
    if check:
        if not OUT.exists() or OUT.read_bytes() != encoded:
            raise SystemExit(
                "Browser inputs differ from the canonical forecast"
            )
        if not audit.exists() or audit.read_bytes() != source_bytes:
            raise SystemExit(
                "Pinned audit download differs from the canonical forecast"
            )
        print(
            "Browser inputs and pinned audit download match the canonical forecast"
        )
        return
    audit.parent.mkdir(parents=True, exist_ok=True)
    # Content-addressed downloads are immutable; never delete older pins.
    if audit.exists() and audit.read_bytes() != source_bytes:
        raise SystemExit("Existing pinned audit download is corrupt")
    if not audit.exists():
        audit.write_bytes(source_bytes)
    temporary = OUT.with_suffix(".json.tmp")
    temporary.write_bytes(encoded)
    temporary.replace(OUT)
    print(OUT)
    print(audit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--published-package-version",
        default=os.environ.get("SPM_PUBLISHED_PACKAGE_VERSION"),
        help="Confirm that the matching pyproject.toml version is on PyPI",
    )
    args = parser.parse_args()
    export(
        check=args.check,
        published_package_version=args.published_package_version,
    )


if __name__ == "__main__":
    main()
