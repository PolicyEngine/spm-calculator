"""Rebuild the step 1 reproduction of Census's 2025 SPM estimates.

Reads the 2026 CPS ASEC public-use zip, after checking it against its
pinned SHA-256, and the P60-290 Tables 4 and 5 bundled with the package,
after checking them against their receipt. Recomputes every estimate in
``docs/census-spm-reproduction.md``, writes them with the published values
to ``spm_calculator/data/census_spm/reproduction_2025.json``, and rewrites
the note's generated blocks from that file.

The zip comes from the package's ASEC cache
(``$SPM_CALCULATOR_CPS_CACHE`` or ``~/.cache/spm-calculator/cps-asec``).
``--download`` fetches it from Census when it is missing. No other network
requests are made.

Run:
    uv run --no-sync python scripts/reproduce_census_spm.py [--download]
Check the committed results and note without writing anything:
    uv run --no-sync python scripts/reproduce_census_spm.py --check
Rewrite only the note from the committed results (no microdata needed):
    uv run --no-sync python scripts/reproduce_census_spm.py --render-only
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from spm_calculator import census_spm
from spm_calculator.census_spm_report import (
    apply_blocks,
    render_blocks,
    round_floats,
)

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "spm_calculator/data/census_spm/reproduction_2025.json"
NOTE = ROOT / "docs/census-spm-reproduction.md"


def package_version() -> str:
    try:
        from importlib.metadata import version

        return version("spm-calculator")
    except Exception:  # pragma: no cover - only without an install
        return "unknown"


def input_provenance(zip_path: Path) -> dict:
    """Checksums of every input, verified on this run."""
    receipt = census_spm.load_receipt()
    tables = {}
    for name, entry in receipt["tables"].items():
        census_spm.verified_table(name)  # Raises on a digest mismatch.
        tables[name] = {
            "file": entry["file"],
            "url": entry["url"],
            "sha256": entry["sha256"],
        }
    return {
        "microdata": {
            "file": census_spm.ZIP_NAME,
            "url": census_spm.ZIP_URL,
            "bytes": zip_path.stat().st_size,
            "sha256": census_spm.ZIP_SHA256,
        },
        "published_tables": {
            "source": receipt["source"],
            "report_url": receipt["report_url"],
            "accessed": receipt["accessed"],
            "tables": tables,
        },
        "software": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "spm_calculator": package_version(),
        },
    }


def without_software(results: dict) -> dict:
    out = json.loads(json.dumps(results))
    out.get("inputs", {}).pop("software", None)
    return out


def rebuild(zip_path: Path, download: bool) -> dict:
    started = time.time()
    path = census_spm.ensure_zip(zip_path, download=download)
    print(f"Verified {path} (SHA-256 {census_spm.ZIP_SHA256[:12]}...)")
    persons = census_spm.load_persons(path)
    print(f"Loaded {len(persons):,} people in {time.time() - started:.0f}s")
    results = census_spm.reproduce(persons, input_provenance(path))
    print(f"Computed every estimate in {time.time() - started:.0f}s")
    return round_floats(results)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--zip", type=Path, default=None)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--output", type=Path, default=RESULTS)
    parser.add_argument("--note", type=Path, default=NOTE)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--render-only", action="store_true")
    args = parser.parse_args(argv)

    if args.render_only:
        results = json.loads(args.output.read_text())
    else:
        results = rebuild(
            args.zip or census_spm.default_zip_path(), args.download
        )

    note = args.note.read_text()
    rendered = apply_blocks(note, render_blocks(results))

    if args.check:
        committed = json.loads(args.output.read_text())
        problems = []
        if without_software(committed) != without_software(results):
            problems.append(f"{args.output} differs from the rebuild")
        if rendered != note:
            problems.append(f"{args.note} differs from its rendered blocks")
        for problem in problems:
            print(f"FAIL: {problem}")
        if problems:
            return 1
        print("The committed results and note match the rebuild.")
    else:
        if not args.render_only:
            args.output.write_text(json.dumps(results, indent=2) + "\n")
            print(f"Wrote {args.output}")
        args.note.write_text(rendered)
        print(f"Wrote {args.note}")

    failures = census_spm.tolerance_failures(results)
    for failure in failures:
        print(f"OUTSIDE TOLERANCE: {failure}")
    summary = results["comparison"]
    print(
        "Table 5: {exact} of {cells} published cells match exactly; "
        "largest effect gap {gap:.2f} pp.".format(
            exact=summary["table5_cells_exact"],
            cells=summary["table5_cells"],
            gap=summary["table5_effect_max_gap"],
        )
    )
    print(
        "Table 4: {within} of {rows} identifiable rows within the "
        "published margin.".format(
            within=summary["table4_percent_within_moe"],
            rows=summary["table4_rows_identifiable"],
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
