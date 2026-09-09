"""Verify a bounded code-identity adaptation without rebuilding science.

Compare every document field against the retained original, admitting only
the declared provenance changes. The default also executes both canonical
consumers over the complete declared household-composition grid.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import struct
from pathlib import Path

from spm_calculator.release import TENURES, SPMUnit, canonical_bytes
from spm_calculator.rolling_forecast import SPMForecast

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_FILE_SHA256 = (
    "76ab8435f087f167ad01b8495ebd016415ba8086f32bfbd3dab961dcc8976c0a"
)
ORIGINAL_CONTENT_SHA256 = (
    "b9dbf5ae49697e3bf3abee2fa22b7429703412cb1e58478938a682a0dfddc821"
)
ORIGINAL_SOURCE_SHA256 = (
    "d96fb6556f3a019025c2bd7dfdef5b9f5d05a7a4d819ab568f3a8bc41bf2aed3"
)
CURRENT_SOURCE_SHA256 = (
    "28d31b3db0caa26f457660f1be9618f63fb08573460c13c68de6cd01b3f7e4bc"
)
SOURCE_MODULE = "spm_calculator/acs_forecast_sources.py"
MANIFEST = "spm_calculator/data/current/acs_normalized_products.json"
ACS_COMPONENT = "spm_calculator/data/current/acs_rolling_forecast.json"
ADAPTATION = "spm_calculator/data/current/acs_code_identity_adaptation.json"
AMOUNT_FIELDS = (
    "threshold",
    "housing_portion",
    "reference_threshold",
    "unadjusted_threshold",
    "geographic_factor",
)


def _digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)


def _same(original, current, label):
    _require(
        canonical_bytes(original) == canonical_bytes(current),
        f"Scientific or undeclared provenance difference: {label}",
    )


def compare_documents(original, current):
    """Validate precisely enumerated provenance edits and no other changes.

    Artifact validation and full calculations are performed by
    ``compare_forecasts``. This helper also supports focused mutation tests.
    """
    _require(
        original["content_sha256"] == ORIGINAL_CONTENT_SHA256,
        "Expected the independently pinned pre-adaptation artifact",
    )
    _same(original["scenarios"], current["scenarios"], "complete scenarios")
    candidate = copy.deepcopy(current)
    changed_paths = []

    for field in ("content_sha256", "assumption_sha256"):
        _require(
            _hash(candidate[field]) and candidate[field] != original[field],
            f"Expected a new derived {field}",
        )
        candidate[field] = original[field]
        changed_paths.append(field)

    for container in (
        ("code_sha256",),
        ("assumptions", "acs", "generator_identity"),
    ):
        before, after = original, candidate
        for key in container:
            before, after = before[key], after[key]
        _require(
            before[SOURCE_MODULE] == ORIGINAL_SOURCE_SHA256
            and after[SOURCE_MODULE] == CURRENT_SOURCE_SHA256,
            "Unexpected original/current normalization source identity",
        )
        after[SOURCE_MODULE] = before[SOURCE_MODULE]
        changed_paths.append("/".join((*container, SOURCE_MODULE)))

    for path in (ACS_COMPONENT, MANIFEST):
        before = original["component_sha256"][path]
        after = candidate["component_sha256"][path]
        _require(_hash(after) and before != after, f"Expected adapted {path}")
        candidate["component_sha256"][path] = before
        changed_paths.append(f"component_sha256/{path}")

    _require(
        "provenance_adaptation" not in original["assumptions"]["acs"],
        "Original must precede this provenance adaptation",
    )
    chain = candidate["assumptions"]["acs"].pop("provenance_adaptation")
    _require(
        set(chain) == {"path", "sha256"}
        and chain["path"] == ADAPTATION
        and _hash(chain["sha256"]),
        "Malformed adaptation receipt link",
    )
    changed_paths.append("assumptions/acs/provenance_adaptation")

    additions = [
        source
        for source in candidate["sources"]
        if source["id"] == "acs-code-identity-adaptation"
    ]
    _require(len(additions) == 1, "Expected one adaptation source")
    expected_source = {
        "id": "acs-code-identity-adaptation",
        "package_path": chain["path"],
        "sha256": chain["sha256"],
        "title": (
            "Equivalent-code ACS provenance adaptation (no raw-source reparse)"
        ),
        "url": "https://github.com/PolicyEngine/spm-calculator",
        "available_on": original["information_date"],
        "availability_note": (
            "Exact source bytes retained by the research build; this date "
            "does not reconstruct historical availability."
        ),
    }
    _same(expected_source, additions[0], "adaptation source")
    candidate["sources"].remove(additions[0])
    changed_paths.append("sources/id=acs-code-identity-adaptation")
    _require(
        len(candidate["sources"]) == len(original["sources"]),
        "Unexpected source addition or removal",
    )
    manifest_count = 0
    for before, after in zip(original["sources"], candidate["sources"]):
        if before["id"] == "acs-normalized-products":
            _require(
                after["id"] == before["id"]
                and before["sha256"] == original["component_sha256"][MANIFEST]
                and after["sha256"] == current["component_sha256"][MANIFEST],
                "Normalized manifest source does not bind its component",
            )
            after["sha256"] = before["sha256"]
            manifest_count += 1
    _require(manifest_count == 1, "Expected one normalized manifest source")
    changed_paths.append("sources/id=acs-normalized-products/sha256")

    # Reversing only the enumerated edits preserves scientific metadata,
    # source order, numeric types and signed zero as well as all arrays.
    _same(original, candidate, "all remaining document fields")
    return {
        "complete_scenarios_sha256": _digest(original["scenarios"]),
        "scientific_fields_exactly_equal": True,
        "allowed_provenance_changes": changed_paths,
    }


def compare_calculations(original, current):
    """Run the actual scalar API for every declared composition and area."""
    original_digest, current_digest = hashlib.sha256(), hashlib.sha256()
    calculations = 0
    area_counts = {}
    scenarios = sorted(original.to_dict()["scenarios"])
    _require(scenarios == ["ce_trend", "zero_real"], "Unexpected scenarios")
    _require(
        original.years == current.years == tuple(range(2022, 2036)),
        "Unexpected calculation year coverage",
    )
    for scenario in scenarios:
        for year in original.years:
            areas = sorted(original.areas_for_year(year, scenario=scenario))
            _require(
                areas
                == sorted(current.areas_for_year(year, scenario=scenario)),
                "Calculation area coverage changed",
            )
            area_counts[f"{scenario}/{year}"] = len(areas)
            for area in areas:
                for tenure in sorted(TENURES):
                    for adults in range(1, 9):
                        for children in range(9):
                            unit = SPMUnit(
                                unit_id="provenance-equivalence",
                                num_adults=adults,
                                num_children=children,
                                tenure=tenure,
                                year=year,
                                resources=40_000,
                                geography_kind="metro",
                                geography_id=area,
                            )
                            before = original.calculate_unit(
                                unit, scenario=scenario
                            )
                            after = current.calculate_unit(
                                unit, scenario=scenario
                            )
                            _require(
                                before.pop("forecast_sha256")
                                == original.content_sha256
                                and after.pop("forecast_sha256")
                                == current.content_sha256,
                                "Calculation failed to identify its artifact",
                            )
                            _require(
                                before == after,
                                "Calculation output changed at "
                                f"{scenario}/{year}/{area}/{tenure}/"
                                f"{adults}/{children}",
                            )
                            before_bytes = struct.pack(
                                ">5d", *(before[key] for key in AMOUNT_FIELDS)
                            )
                            after_bytes = struct.pack(
                                ">5d", *(after[key] for key in AMOUNT_FIELDS)
                            )
                            _require(
                                before_bytes == after_bytes,
                                "Calculation float64 bit pattern changed",
                            )
                            original_digest.update(before_bytes)
                            current_digest.update(after_bytes)
                            calculations += 1
    _require(
        original_digest.digest() == current_digest.digest(),
        "Calculation amount digests differ",
    )
    return {
        "calculations": calculations,
        "exact_field_comparisons": calculations * len(AMOUNT_FIELDS),
        "fields": list(AMOUNT_FIELDS),
        "all_result_fields_equal_except": ["forecast_sha256"],
        "max_absolute_difference": 0,
        "original_sha256_big_endian_float64": original_digest.hexdigest(),
        "current_sha256_big_endian_float64": current_digest.hexdigest(),
        "scenario_count": len(scenarios),
        "years": list(original.years),
        "area_counts": area_counts,
        "composition_grid": {
            "adults": list(range(1, 9)),
            "children": list(range(9)),
        },
        "resources": 40_000,
        "ordering": (
            "scenario, year, area, tenure, adults, children ascending; "
            "fields in recorded order"
        ),
    }


def compare_forecasts(original: dict, current: dict, *, calculate=True):
    """Return exact comparison evidence or reject any undeclared difference.

    ``calculate=False`` only omits the exhaustive API grid; it still validates
    both complete artifacts and every scientific document field.
    """
    before = SPMForecast.from_dict(
        original, expected_sha256=ORIGINAL_CONTENT_SHA256
    )
    after = SPMForecast.from_dict(current)
    evidence = compare_documents(original, current)
    evidence.update(
        {
            "status": "all_exact_equality_checks_passed",
            "original_content_sha256": before.content_sha256,
            "current_content_sha256": after.content_sha256,
            "calculation_grid_executed": calculate,
        }
    )
    if calculate:
        evidence["amount_comparison"] = compare_calculations(before, after)
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--original",
        type=Path,
        default=ROOT
        / "web/public/data/canonical"
        / f"rolling-forecast-{ORIGINAL_FILE_SHA256}.json",
    )
    parser.add_argument(
        "--current",
        type=Path,
        default=ROOT
        / "spm_calculator/data/current/rolling_forecast_2026_09_09.json",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    original_bytes = args.original.read_bytes()
    current_bytes = args.current.read_bytes()
    _require(
        hashlib.sha256(original_bytes).hexdigest() == ORIGINAL_FILE_SHA256,
        "Original artifact file does not match the immutable baseline pin",
    )
    evidence = compare_forecasts(
        json.loads(original_bytes), json.loads(current_bytes)
    )
    evidence["original_file_sha256"] = ORIGINAL_FILE_SHA256
    evidence["current_file_sha256"] = hashlib.sha256(current_bytes).hexdigest()
    encoded = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.write_text(encoded)
        print(args.output)


if __name__ == "__main__":
    main()
