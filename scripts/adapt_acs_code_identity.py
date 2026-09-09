"""Reproduce the approved AST-portability provenance adaptation, offline.

This operation inherits archived raw-reparse evidence. It never reparses PUMS
or rebuilds CE/ACS estimates. The original files are inputs, never outputs.
Run this, build_rolling_forecast.py, then finalize with --finalize (or check
the entire chain with --check --finalize). Export the web artifact separately.
"""

from __future__ import annotations

import argparse
import ast
import copy
import gzip
import hashlib
import json
from pathlib import Path

from spm_calculator.acs_forecast_sources import _normalization_ast_dump
from spm_calculator.release import canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
CURRENT = "spm_calculator/data/current/"
ARCHIVE = "spm_calculator/data/provenance/ast-portability-2026-09-09/"
MODULE = "spm_calculator/acs_forecast_sources.py"
OPERATION = CURRENT + "acs_code_identity_adaptation.json"
FORECAST = CURRENT + "rolling_forecast_2026_09_09.json"
OLD_SOURCE = "d96fb6556f3a019025c2bd7dfdef5b9f5d05a7a4d819ab568f3a8bc41bf2aed3"
NEW_SOURCE = "28d31b3db0caa26f457660f1be9618f63fb08573460c13c68de6cd01b3f7e4bc"
OLD_ARTIFACT = (
    "76ab8435f087f167ad01b8495ebd016415ba8086f32bfbd3dab961dcc8976c0a"
)
BASELINE = f"web/public/data/canonical/rolling-forecast-{OLD_ARTIFACT}.json"
ORIGINALS = {
    "source": ("acs_forecast_sources.py.txt", OLD_SOURCE),
    "manifest": (
        "acs_normalized_products.json",
        "7f9dd53454eeac90a83437643944e47d60d27d35cf3a99d2a988c39be25b99a8",
    ),
    "normalization_receipt": (
        "acs_2021_normalization_receipt.json",
        "925d0f4fcc06694f808afe7155b88924cb14e425f51cb0dac40363384ed3b5bf",
    ),
    "acs_component": (
        "acs_rolling_forecast.json.gz",
        "8ad5edcd82c9535e9a8170539f55ce21474245d69f09775d9c0cd9a49f0cda20",
    ),
    "scientific_refresh_receipt": (
        "scientific_refresh_receipt.json",
        "ea431cf183c80c8c0446f614ba355bddc6a30714906460bf1e8df54cd332af54",
    ),
}
VERIFICATION = (
    "Inherited exact raw-reparse evidence from the original receipt; "
    "current parser identity admitted by equivalent-code adaptation. "
    "No raw-source reparse performed by this adaptation."
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(document):
    return (
        json.dumps(
            document,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode()


def link(path, data=None):
    return {
        "path": path,
        "sha256": digest((ROOT / path).read_bytes() if data is None else data),
    }


def original_inputs():
    documents, links = {}, {}
    for key, (name, expected) in ORIGINALS.items():
        path = ARCHIVE + name
        stored = (ROOT / path).read_bytes()
        raw = gzip.decompress(stored) if name.endswith(".gz") else stored
        if digest(raw) != expected:
            raise ValueError(f"Original evidence changed: {path}")
        links[key] = link(path, stored)
        if name.endswith(".gz"):
            links[key].update(encoding="gzip", decoded_sha256=expected)
        documents[key] = raw if key == "source" else json.loads(raw)
    raw = (ROOT / BASELINE).read_bytes()
    if digest(raw) != OLD_ARTIFACT:
        raise ValueError("Original canonical download changed")
    documents["artifact"] = json.loads(raw)
    links["artifact"] = {
        **link(BASELINE, raw),
        "content_sha256": documents["artifact"]["content_sha256"],
        "assumption_sha256": documents["artifact"]["assumption_sha256"],
    }
    return documents, links


def verify_source_adaptation(original, current):
    """Bind real bytes and independently compare every scientific section."""
    if digest(original) != OLD_SOURCE or digest(current) != NEW_SOURCE:
        raise ValueError("Source bytes differ from the approved adaptation")
    old_text, new_text = original.decode(), current.decode()
    old_tree, new_tree = ast.parse(old_text), ast.parse(new_text)
    identity_functions = {
        "normalization_logic_sha256",
        "_normalization_ast_dump",
    }

    def scientific_sections(tree, source):
        return [
            ast.get_source_segment(source, node)
            for node in tree.body
            if getattr(node, "name", None) not in identity_functions
        ]

    if scientific_sections(old_tree, old_text) != scientific_sections(
        new_tree, new_text
    ):
        raise ValueError("Scientific source sections changed")
    functions = ["_universe", "normalize_housing", "apply_puma_update"]
    historical = ["_historical_housing", "_restore_historical_record_ids"]
    nodes = {
        node.name: node
        for node in old_tree.body
        if isinstance(node, ast.FunctionDef)
    }
    mapping = next(
        ast.literal_eval(node.value)
        for node in old_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "COMPONENTS"
            for t in node.targets
        )
    )
    hashes = {}
    for vintage in (2021, 2022, 2023, 2024):
        names = functions + (historical if vintage == 2021 else [])
        logic = "".join(
            _normalization_ast_dump(
                ast.parse(ast.get_source_segment(old_text, nodes[name]))
            )
            for name in names
        ) + json.dumps(mapping, sort_keys=True)
        hashes[str(vintage)] = digest(logic.encode())
    return {
        "scientific_top_level_sections_byte_equal": True,
        "normalization_function_source_sha256": {
            name: digest(
                ast.get_source_segment(old_text, nodes[name]).encode()
            )
            for name in functions + historical
        },
        "normalization_logic_sha256_by_vintage": hashes,
        "method": (
            "Compare original/current scientific source sections byte-for-byte; "
            "serialize unchanged original normalizer ASTs using the portable "
            "Python 3.13 spelling and compare with original cache pins."
        ),
    }


def build_adaptation():
    original, originals = original_inputs()
    evidence = verify_source_adaptation(
        original["source"], (ROOT / MODULE).read_bytes()
    )
    for vintage, receipt in original["manifest"].items():
        if (
            evidence["normalization_logic_sha256_by_vintage"][vintage]
            != (receipt["normalization_logic_sha256"])
        ):
            raise ValueError(
                "Original normalized-cache logic identity changed"
            )
    operation = {
        "schema_version": 1,
        "kind": "equivalent_code_provenance_adaptation",
        "date": "2026-09-09",
        "reason": "Portable AST serialization across Python 3.9–3.14",
        "raw_source_reparse_performed": False,
        "scientific_component_rebuild_performed": False,
        "normalized_cache_files_rewritten": False,
        "original": originals,
        "current_source": link(MODULE),
        "normalization_evidence": evidence,
        "builder": link("scripts/adapt_acs_code_identity.py"),
        "evidence_scope": (
            "The archived reparse and scientific-refresh receipts describe "
            "earlier runs under their original source/artifact identities. "
            "This operation admits equivalent code and reuses retained products; "
            "it does not repeat or relabel those historical runs."
        ),
    }
    operation_bytes = encoded(operation)
    chain = link(OPERATION, operation_bytes)
    manifest = copy.deepcopy(original["manifest"])
    manifest["2021"].update(
        parser_sha256=NEW_SOURCE, provenance_adaptation=chain
    )
    manifest_bytes = encoded(manifest)
    receipt = copy.deepcopy(original["normalization_receipt"])
    receipt.update(
        parser_sha256=NEW_SOURCE,
        manifest_sha256=digest(manifest_bytes),
        verification=VERIFICATION,
        provenance_adaptation=chain,
        original_reparse_evidence=originals["normalization_receipt"],
        raw_source_reparse_performed=False,
    )
    acs = copy.deepcopy(original["acs_component"])
    acs["metadata"]["generator_identity"][MODULE] = NEW_SOURCE
    acs["metadata"]["provenance_adaptation"] = chain
    source = next(
        s for s in acs["sources"] if s.get("id") == "acs-normalized-products"
    )
    source["sha256"] = digest(manifest_bytes)
    acs["sources"].append(
        {
            "id": "acs-code-identity-adaptation",
            "package_path": OPERATION,
            "sha256": chain["sha256"],
            "title": "Equivalent-code ACS provenance adaptation (no raw-source reparse)",
        }
    )
    return {
        OPERATION: operation_bytes,
        CURRENT + "acs_normalized_products.json": manifest_bytes,
        CURRENT + "acs_2021_normalization_receipt.json": encoded(receipt),
        CURRENT + "acs_rolling_forecast.json": encoded(acs),
    }


def finalize():
    from scripts.verify_provenance_equivalence import compare_forecasts

    original, originals = original_inputs()
    current = json.loads((ROOT / FORECAST).read_bytes())
    comparison = compare_forecasts(original["artifact"], current)
    # The original scientific-refresh numbers retain their historical scope
    # in the archived receipt; these are new comparisons against 76ab8435….
    return encoded(
        {
            "schema_version": 1,
            "kind": "equivalent_code_adaptation_verification",
            "status": "all_exact_equality_checks_passed",
            "raw_source_reparse_performed": False,
            "scientific_component_rebuild_performed": False,
            "previous_scientific_refresh": originals[
                "scientific_refresh_receipt"
            ],
            "provenance_adaptation": link(OPERATION),
            "baseline_artifact": originals["artifact"],
            "baseline_content_sha256": original["artifact"]["content_sha256"],
            "final_content_sha256": current["content_sha256"],
            "final_assumption_sha256": current["assumption_sha256"],
            "artifact_sha256": {
                name: digest((ROOT / name).read_bytes())
                for name in [
                    *original["scientific_refresh_receipt"]["artifact_sha256"],
                    CURRENT + "acs_2021_normalization_receipt.json",
                    OPERATION,
                ]
            },
            "scientific_equivalence": comparison,
            "normalized_cache_identity": {
                vintage: {
                    key: value
                    for key, value in receipt.items()
                    if key != "parser_sha256"
                }
                for vintage, receipt in original["manifest"].items()
            },
            "audit_script": link("scripts/verify_provenance_equivalence.py"),
        }
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    outputs = build_adaptation()
    if args.finalize:
        # Finalize only after current upstream bytes and lightweight assembly
        # have been reproduced, so an old forecast cannot acquire a new receipt.
        for name, data in outputs.items():
            if (ROOT / name).read_bytes() != data:
                raise ValueError(
                    f"Reproduce the upstream adaptation first: {name}"
                )
        from scripts.build_rolling_forecast import build_document

        if canonical_bytes(build_document()) != canonical_bytes(
            json.loads((ROOT / FORECAST).read_bytes())
        ):
            raise ValueError(
                "Reassemble the rolling forecast before finalizing"
            )
        outputs[CURRENT + "scientific_refresh_receipt.json"] = finalize()
    for name, data in outputs.items():
        path = ROOT / name
        if args.check:
            if not path.exists() or path.read_bytes() != data:
                raise ValueError(f"Adaptation output differs: {name}")
        else:
            path.write_bytes(data)
    print("Provenance adaptation " + ("verified" if args.check else "written"))


if __name__ == "__main__":
    main()
