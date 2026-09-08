"""Record actual Axiom execution of public, synthetic SPM-unit fixtures.

The thresholds are from the real bundled SPM release. The households are
synthetic. This is development integration evidence, not legal validation.
"""

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from spm_calculator.axiom_adapter import (
    POVERTY_ID,
    THRESHOLD_ID,
    AxiomSPMAdapter,
    export_build_spec,
)
from spm_calculator.release import SPMUnit, load_release


def write(path, data):
    with path.open("x", encoding="utf-8") as output:
        json.dump(data, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--core-checkout", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    release = load_release()
    adapter = AxiomSPMAdapter(release, binary=args.binary)
    units = [
        SPMUnit(
            f"synthetic:{year}:{tenure}",
            adults,
            children,
            tenure,
            year,
            geographic_adjustment=factor,
        )
        for year in (2024, 2025)
        for tenure, adults, children, factor in (
            ("owner_with_mortgage", 2, 2, 1.1),
            ("owner_without_mortgage", 1, 0, 0.9),
            ("renter", 1, 2, 1.0),
        )
    ]
    base = release.entry(2025)["thresholds"]["renter"]
    units.extend(
        SPMUnit(
            f"synthetic:boundary:{label}",
            2,
            2,
            "renter",
            2025,
            resources=base + delta,
        )
        for label, delta in (("below", -0.01), ("equal", 0), ("above", 0.01))
    )
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    spec = export_build_spec(release, years=[2024, 2025])
    write(out / "build-spec.json", spec)
    identity = adapter.build_bundle(
        out / "spm.bundle.json", years=[2024, 2025]
    )
    write(out / "expected-identity.json", identity)
    result = adapter.execute_bundle(
        out / "spm.bundle.json", identity["bundle_sha256"], units
    )
    write(out / "request.json", result["request"])
    write(out / "native-receipt.json", result["receipt"])
    write(out / "spm-input-provenance.json", result["spm_inputs"])
    comparisons = []
    for unit, native in zip(units, result["receipt"]["result"]["results"]):
        threshold = native["outputs"][THRESHOLD_ID]["value"]["value"]
        independent = release.calculate_unit(unit)
        if not math.isclose(
            float(threshold),
            independent["threshold"],
            rel_tol=1e-12,
            abs_tol=1e-8,
        ):
            raise AssertionError(
                "Actual Axiom threshold differs from standalone release result"
            )
        outcome = native["outputs"].get(POVERTY_ID, {}).get("outcome")
        if unit.resources is not None:
            expected = "holds" if independent["is_in_poverty"] else "not_holds"
            if outcome != expected:
                raise AssertionError("Actual Axiom poverty comparison differs")
        comparisons.append(
            {
                "unit_id": unit.unit_id,
                "year": unit.year,
                "native_threshold_decimal": threshold,
                "standalone_threshold": independent["threshold"],
                "native_poverty_outcome": outcome,
            }
        )
    code_files = (
        "spm_calculator/axiom_adapter.py",
        "spm_calculator/release.py",
        "spm_calculator/equivalence_scale.py",
        "scripts/validate_axiom_integration.py",
    )
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Partial Axiom bridge with declared external equivalence/geography and supplied resources",
        "fixture_kind": "synthetic SPM units; actual published threshold release",
        "release_id": release.release_id,
        "release_sha256": release.content_sha256,
        "package_version": version("spm-calculator"),
        "source_checkout_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "source_checkout_dirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=REPO, text=True
            ).strip()
        ),
        "source_file_sha256": {
            name: hashlib.sha256((REPO / name).read_bytes()).hexdigest()
            for name in code_files
        },
        "capabilities": adapter.capabilities(),
        "binary_sha256": hashlib.sha256(
            adapter.binary.read_bytes()
        ).hexdigest(),
        "expected_bundle_sha256": identity["bundle_sha256"],
        "artifact_sha256": identity["artifact_sha256"],
        "date_policy": "inclusive January 1 through December 31; no assessment_date; release validates information cutoff",
        "comparisons": comparisons,
        "all_comparisons_passed": True,
        "limits": [
            "Not full Axiom SPM classification, equivalence, taxes, benefits or resource construction",
            "Unsigned development evidence; not source authentication or legal validation",
            "Bundle requires original executable bytes; distribute build-spec source for portability",
        ],
    }
    if args.core_checkout:
        core = args.core_checkout.resolve()
        summary["declared_core_source_checkout"] = {
            "git_head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=core, text=True
            ).strip(),
            "dirty": bool(
                subprocess.check_output(
                    ["git", "status", "--porcelain"], cwd=core, text=True
                ).strip()
            ),
            "cargo_lock_sha256": hashlib.sha256(
                (core / "Cargo.lock").read_bytes()
            ).hexdigest(),
            "rustc": subprocess.check_output(
                ["rustc", "--version"], cwd=core, text=True
            ).strip(),
            "cargo": subprocess.check_output(
                ["cargo", "--version"], cwd=core, text=True
            ).strip(),
        }
    write(out / "validation.json", summary)
    print(
        json.dumps(
            {
                "output_dir": str(out),
                "comparisons": len(comparisons),
                "all_passed": True,
            }
        )
    )


if __name__ == "__main__":
    main()
