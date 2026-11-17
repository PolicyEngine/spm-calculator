"""Export the CE in-kind imputations, one row per interview and implicate.

Loads the cached CE Interview bundles and CPS ASEC public-use files that
``scripts/replicate_ce_inkind.py`` uses (2014Q2-2025Q1, reference years
2014-2024), runs ``spm_calculator.ce_inkind.impute_in_kind`` with the same
settings while recording each component's participation draws, checks the
run against the archived receipt
``spm_calculator/data/current/ce_inkind_replication_2019_2025.json``, and
writes to ``--out``:

- ``ce_inkind_by_interview_<first>_<last>.csv.gz``: the export
  (``docs/ce-inkind-export.md`` describes every column);
- ``ce_inkind_by_interview_dictionary.csv``: the data dictionary;
- ``ce_inkind_by_interview_manifest.json``: counts, sources, settings,
  checks and hashes;
- ``SHA256SUMS``.

After writing, the script reads the file back with pandas defaults and
checks it against the imputation. No network requests are made.

Run: uv run --no-sync python scripts/export_ce_inkind_by_interview.py \\
    --out <directory outside the repository>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import scipy

from spm_calculator.ce_inkind import (
    IN_KIND_COMPONENTS,
    InKindConfig,
    ce_unit_covariates,
    impute_in_kind,
    load_ce_unit_inputs,
)
from spm_calculator.ce_inkind_export import (
    COLUMNS,
    FMLI_COLUMNS,
    WIC_EXPORT_TARGET,
    diagnostics_difference,
    dictionary_csv,
    export_frames,
    observe_participation,
    verify_written,
    write_csv_gz,
)
from spm_calculator.ce_threshold import bls_quarter_window, load_ce_quarter
from spm_calculator.cps_asec import load_household_donors

ROOT = Path(__file__).resolve().parent.parent
RECEIPT = (
    ROOT / "spm_calculator/data/current/ce_inkind_replication_2019_2025.json"
)
STEM = "ce_inkind_by_interview"
#: Largest relative difference allowed between this run's imputation
#: diagnostics and the receipt's. Runs in the receipt's environment match
#: exactly; other builds of numpy or BLAS differ in the last bits.
DIAGNOSTICS_RTOL = 1e-9
WIC_ATTRIBUTION = (
    "U.S. Census Bureau SPM team, compiled from USDA FNS WIC program data "
    "(personal communication, November 16, 2026)"
)
CODE_PATHS = (
    "spm_calculator/ce_threshold.py",
    "spm_calculator/ce_inkind.py",
    "spm_calculator/ce_inkind_export.py",
    "spm_calculator/cps_asec.py",
    "scripts/export_ce_inkind_by_interview.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quarter_label(quarter) -> str:
    return f"{quarter[0]}Q{quarter[1]}"


def participation_summary(frames) -> dict:
    """Participant counts by component, implicate and reference year."""
    summary = {}
    for component in IN_KIND_COMPONENTS:
        participant = f"{component}_participant"
        amount = f"{component}_amount"
        by_year: dict = {}
        for m, frame in enumerate(frames):
            modeled = frame.loc[frame[participant].notna()]
            flag = modeled[participant].astype(int) == 1
            groups = modeled.assign(
                flag=flag, zero=flag & (modeled[amount] == 0)
            )
            for year, group in groups.groupby("reference_year"):
                entry = by_year.setdefault(
                    str(year),
                    {"participants": [], "participants_with_zero_amount": []},
                )
                entry["participants"].append(int(group["flag"].sum()))
                entry["participants_with_zero_amount"].append(
                    int(group["zero"].sum())
                )
        summary[component] = by_year
    return summary


def readme_text(name, coverage, counts) -> str:
    return f"""# CE in-kind imputations by interview

`{name}` holds the in-kind benefit imputations from the PolicyEngine SPM
calculator (https://github.com/PolicyEngine/spm-calculator), one row per CE
Interview record (FMLI `NEWID`) per implicate, for every interview collected
from {coverage[0]} to {coverage[1]}: {counts["interviews"]:,} interviews x
{counts["implicates"]} implicates = {counts["rows"]:,} rows.

Each row carries the participation flag and annual dollar amount of five
components: free or reduced-price school lunch, WIC, LIHEAP, broadband
subsidies and rental assistance. The values follow the threshold rules the
calculator's replication of BLS's Supplemental Poverty Measure thresholds
uses, not actual receipt.

Read https://github.com/PolicyEngine/spm-calculator/blob/main/docs/ce-inkind-export.md
before using the file. It explains each column, where the values follow
those rules rather than receipt, how to merge with the CE public-use
microdata, and how to combine implicates.

Files:

- `{name}`: the export (gzipped CSV)
- `{STEM}_dictionary.csv`: column, type and description
- `{STEM}_manifest.json`: counts, source files, settings, checks and hashes
- `SHA256SUMS`

Sources: BLS Consumer Expenditure Survey Interview public-use microdata;
Census Bureau CPS ASEC public-use files; USDA FNS school lunch rates and WIC
EBT dates; WIC state food costs from the {WIC_ATTRIBUTION}.

License: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Credit
"PolicyEngine SPM calculator".

Regenerate with `scripts/export_ce_inkind_by_interview.py` at the commit the
manifest names.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ce-cache",
        type=Path,
        default=Path.home() / ".cache/spm-calculator/ce-pumd",
    )
    parser.add_argument(
        "--cps-cache",
        type=Path,
        default=Path.home() / ".cache/spm-calculator/cps-asec",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if out == ROOT or ROOT in out.parents:
        parser.error("--out must be outside the repository")
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()

    receipt = json.loads(RECEIPT.read_text())
    targets = sorted(int(t) for t in receipt["results"])
    quarters = sorted({q for t in targets for q in bls_quarter_window(t)})
    raw, sources, bundles = [], [], {}
    for quarter in quarters:
        frame = load_ce_quarter(
            *quarter, cache_dir=args.ce_cache, allow_download=False
        )
        source = frame.attrs["source"]
        member = Path(source["member"]).name
        if member.lower().endswith("x.csv"):
            raise RuntimeError(
                f"{quarter_label(quarter)} came from overlap file {member}"
            )
        missing = sorted(set(FMLI_COLUMNS) - set(frame.columns))
        if missing:
            raise RuntimeError(
                f"{quarter_label(quarter)} lacks FMLI columns {missing}"
            )
        bundle = Path(source["bundle_path"])
        if bundle.name not in bundles:
            digest = sha256(bundle)
            if digest != receipt["ce_bundles"][bundle.name]["sha256"]:
                raise RuntimeError(
                    f"{bundle.name} differs from the receipt's bundle"
                )
            bundles[bundle.name] = {"sha256": digest, "url": source["url"]}
        sources.append(
            {
                "quarter": quarter_label(quarter),
                "bundle": bundle.name,
                "member": member,
                "interviews": int(len(frame)),
            }
        )
        piece = frame[list(FMLI_COLUMNS)].copy()
        piece.attrs = {}
        raw.append(piece)
    fmli = pd.concat(raw, ignore_index=True)
    del raw
    print(f"Loaded {len(quarters)} CE quarters", flush=True)
    units = load_ce_unit_inputs(quarters, cache_dir=args.ce_cache)
    ce_units = ce_unit_covariates(fmli, units)
    reference_years = sorted(
        int(y) for y in ce_units["reference_year"].unique()
    )
    donors, cps_provenance = load_household_donors(
        [year + 1 for year in reference_years], args.cps_cache
    )
    if json.loads(json.dumps(cps_provenance)) != receipt["cps_asec_files"]:
        raise RuntimeError("CPS ASEC files differ from the receipt's")

    config = InKindConfig(implicates=5)
    with observe_participation() as draws:
        imputation = impute_in_kind(ce_units, donors, config)
    print(f"Imputed in {time.time() - started:.0f}s", flush=True)
    methodology = json.loads(json.dumps(imputation.methodology))
    if methodology != receipt["in_kind_methodology"]:
        raise RuntimeError("Imputation settings differ from the receipt's")
    ours = json.loads(json.dumps(imputation.diagnostics, default=float))
    worst = diagnostics_difference(ours, receipt["imputation_diagnostics"])
    if not worst <= DIAGNOSTICS_RTOL:
        raise RuntimeError(
            f"Diagnostics differ from the receipt's (relative {worst:.3g})"
        )

    frames = export_frames(ce_units, imputation, draws, config)
    coverage = (quarter_label(quarters[0]), quarter_label(quarters[-1]))
    name = f"{STEM}_{coverage[0].lower()}_{coverage[1].lower()}.csv.gz"
    written = write_csv_gz(frames, out / name)
    checks = verify_written(
        out / name, frames, ce_units, imputation.diagnostics, config
    )
    print(f"Wrote and checked {name}: {written['rows']:,} rows", flush=True)

    dictionary = out / f"{STEM}_dictionary.csv"
    dictionary.write_text(dictionary_csv())
    counts = {
        "rows": written["rows"],
        "interviews": int(len(ce_units)),
        "implicates": config.implicates,
    }
    readme = out / "README.md"
    readme.write_text(readme_text(name, coverage, counts))
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ).strip()
    )
    manifest = {
        "schema_version": 1,
        "generated_by": "scripts/export_ce_inkind_by_interview.py",
        "generated_on": datetime.now(timezone.utc).date().isoformat(),
        "git_head": head,
        "git_dirty": dirty,
        "files": {
            name: {
                "sha256": written["csv_gz_sha256"],
                "bytes": written["csv_gz_bytes"],
                "uncompressed_sha256": written["csv_sha256"],
                "uncompressed_bytes": written["csv_bytes"],
            },
            dictionary.name: {"sha256": sha256(dictionary)},
            readme.name: {"sha256": sha256(readme)},
        },
        "columns": list(COLUMNS),
        **counts,
        "coverage": {
            "first_quarter": coverage[0],
            "last_quarter": coverage[1],
            "reference_years": reference_years,
        },
        "interviews_by_reference_year": {
            str(k): int(v)
            for k, v in ce_units["reference_year"]
            .value_counts()
            .sort_index()
            .items()
        },
        "ce_sources": sources,
        "ce_bundles": bundles,
        "cps_asec_files": cps_provenance,
        "in_kind_methodology": imputation.methodology,
        "rules": {
            "wic": (
                f"Values for targets before {WIC_EXPORT_TARGET + 1}: "
                f"InKindImputation.for_target(m, {WIC_EXPORT_TARGET})"
            ),
            "broadband_first_reference_year": config.broadband_first_reference_year,
            "wic_ebt_all_states_from_reference_year": config.wic_ebt_all_states_from_reference_year,
            "amounts": "annual, nominal dollars of the reference year, rounded to cents",
        },
        "wic_state_food_costs_source": WIC_ATTRIBUTION,
        "participation": participation_summary(frames),
        "checks": {
            "receipt": str(RECEIPT.relative_to(ROOT)),
            "receipt_git_head": receipt["git_head"],
            "diagnostics_max_relative_difference": worst,
            "participation_draws_recorded": len(draws),
            **checks,
        },
        "code_sha256": {path: sha256(ROOT / path) for path in CODE_PATHS},
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
        },
        "runtime_seconds": math.ceil(time.time() - started),
    }
    manifest_path = out / f"{STEM}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    sums = [
        f"{sha256(out / f)}  {f}"
        for f in sorted(
            [name, dictionary.name, readme.name, manifest_path.name]
        )
    ]
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    print(json.dumps({**counts, **written, **checks}, indent=2))


if __name__ == "__main__":
    main()
