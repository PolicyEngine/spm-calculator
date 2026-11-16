"""Tabulate the CE internet UCCs behind the home internet run's choices.

``spm_calculator.ce_internet`` takes home internet from CE Interview UCC
690114 alone. ``docs/ce-inkind-imputation.md`` gives the CE figures behind
that choice and the recording shifts it carries; this script records them:

- by collection quarter, the cost flags on UCC 690114's MTBI records, the
  share of units reporting UCC 690114 and UCC 270310 (cable and satellite
  television services), and UCC 690114's mean among reporters;
- by target year's collection window, UCC 690116 (internet services away
  from home) as a percent of UCC 690114, among all FMLI units with children
  and in the replication's estimation sample; the script stops unless that
  sample gives the replication receipt's thresholds without home internet or
  benefits;
- our in-band home internet over BLS's, from
  ``ce_inkind_bls_components_2019_2025.json``, in the bands without and with
  benefits.

Shares and means weight units by FINLWT21, except the record shares of
each cost flag, which count records, and the estimation sample's percents,
which use the replication's ``ce_weight``. Dollars are three-month MTBI
costs. The script reads cached CE bundles, makes no network requests, and
its receipt holds aggregates only, no CE records.

Run: uv run --no-sync python scripts/tabulate_ce_internet_uccs.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from spm_calculator.ce_inkind_stage import prepare_out_of_pocket
from spm_calculator.ce_internet import INTERNET_COLUMN, mtbi_member
from spm_calculator.ce_threshold import bls_quarter_window, load_ce_quarter

ROOT = Path(__file__).resolve().parent.parent
CURRENT = ROOT / "spm_calculator/data/current"
RECEIPT = CURRENT / "ce_internet_ucc_tabulations_2019_2025.json"
COMPONENTS_RECEIPT = CURRENT / "ce_inkind_bls_components_2019_2025.json"
REPLICATION_RECEIPT = CURRENT / "ce_inkind_replication_2019_2025.json"
CPI_INPUT = ROOT / "spm_calculator/data/bls/cpi_annual.json"
TARGETS = range(2019, 2026)
HOME_INTERNET = 690114
AWAY_INTERNET = 690116
CABLE_TV = 270310
UCCS = (HOME_INTERNET, AWAY_INTERNET, CABLE_TV)
#: Column holding each unit's three-month UCC 690116 cost.
AWAY_COLUMN = "away_internet_quarterly"
#: FMLI columns the out-of-pocket replication reads, as in
#: ``scripts/replicate_ce_inkind.py``.
KEEP = (
    "NEWID",
    "AGE_REF",
    "PERSLT18",
    "FAM_SIZE",
    "CUTENURE",
    "FINLWT21",
    "ce_year",
    "ce_quarter",
    "FOODPQ",
    "FOODCQ",
    "FDHOMEPQ",
    "FDHOMECQ",
    "FDAWAYPQ",
    "FDAWAYCQ",
    "GROCERPQ",
    "GROCERCQ",
    "APPARPQ",
    "APPARCQ",
    "SHELTPQ",
    "SHELTCQ",
    "UTILPQ",
    "UTILCQ",
    "TELEPHPQ",
    "TELEPHCQ",
    "EMRTPNOP",
    "EMRTPNOC",
    "MRTPRNOP",
    "MRTPRNOC",
)
CODE_PATHS = (
    "scripts/tabulate_ce_internet_uccs.py",
    "spm_calculator/ce_internet.py",
    "spm_calculator/ce_inkind_stage.py",
    "spm_calculator/ce_threshold.py",
    "spm_calculator/equivalence_scale.py",
    "spm_calculator/fcsuti_cpi.py",
    "spm_calculator/published_thresholds.py",
)
#: The components receipt's runs, by deflator.
RUNS = ("package", "fcsuti")
#: Bands in the components receipt: without and with benefits.
BANDS = {
    "without_benefits": "without_in_kind",
    "with_benefits": "with_in_kind",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_ucc_records(fmli: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """MTBI records for :data:`UCCS` beside an FMLI quarter, and the MTBI
    member they come from."""
    source = fmli.attrs["source"]
    member = mtbi_member(source["member"])
    with zipfile.ZipFile(source["bundle_path"]) as archive:
        with archive.open(member) as handle:
            columns = pd.read_csv(handle, nrows=0).columns
        flag = next(c for c in columns if c.upper() == "COST_")
        with archive.open(member) as handle:
            records = pd.read_csv(
                handle,
                usecols=["NEWID", "UCC", "COST", flag],
                low_memory=False,
            )
    records = records.rename(columns={flag: "flag"})
    records["UCC"] = pd.to_numeric(records["UCC"], errors="coerce")
    records = records.loc[records["UCC"].isin(UCCS)].copy()
    records["COST"] = pd.to_numeric(records["COST"], errors="raise")
    if not np.isfinite(records["COST"].to_numpy(dtype=float)).all():
        raise ValueError(f"{member}: costs must be finite")
    unknown = pd.Index(records["NEWID"]).difference(pd.Index(fmli["NEWID"]))
    if len(unknown):
        raise ValueError(f"{member}: {len(unknown)} NEWIDs not in FMLI")
    records["flag"] = records["flag"].astype(str).str.strip()
    return records, member


def unit_costs(fmli: pd.DataFrame, records: pd.DataFrame, ucc: int):
    """Each FMLI unit's three-month cost for ``ucc`` and whether it has a
    record, aligned to the FMLI rows."""
    rows = records.loc[records["UCC"] == ucc]
    newids = fmli["NEWID"].to_numpy()
    cost = rows.groupby("NEWID")["COST"].sum().reindex(newids, fill_value=0.0)
    reports = rows.groupby("NEWID").size().reindex(newids, fill_value=0) > 0
    return cost.to_numpy(dtype=float), reports.to_numpy()


def weighted_share(weight, mask, among) -> float:
    return float(weight[mask & among].sum() / weight[among].sum())


def quarter_record(fmli: pd.DataFrame, records: pd.DataFrame) -> dict:
    weight = fmli["FINLWT21"].to_numpy(dtype=float)
    everyone = np.ones(len(fmli), dtype=bool)
    children = fmli["PERSLT18"].to_numpy(dtype=float) > 0
    home, home_reports = unit_costs(fmli, records, HOME_INTERNET)
    away, _ = unit_costs(fmli, records, AWAY_INTERNET)
    _, cable_reports = unit_costs(fmli, records, CABLE_TV)
    home_rows = records.loc[records["UCC"] == HOME_INTERNET]
    row_weight = home_rows["NEWID"].map(
        pd.Series(weight, index=fmli["NEWID"].to_numpy())
    )
    by_flag = row_weight.groupby(home_rows["flag"].to_numpy()).sum()
    groups = {"all_units": everyone, "units_with_children": children}
    return {
        "units": int(len(fmli)),
        "ucc_690114_records": int(len(home_rows)),
        "ucc_690114_flag_share_of_records": {
            flag: float(share)
            for flag, share in home_rows["flag"]
            .value_counts(normalize=True)
            .sort_index()
            .items()
        },
        "ucc_690114_flag_share_weighted": {
            flag: float(value / by_flag.sum())
            for flag, value in by_flag.sort_index().items()
        },
        "ucc_690114_share_reporting": {
            name: weighted_share(weight, home_reports, among)
            for name, among in groups.items()
        },
        "ucc_270310_share_reporting": {
            name: weighted_share(weight, cable_reports, among)
            for name, among in groups.items()
        },
        "ucc_690114_mean_among_reporters": {
            name: float(
                np.average(
                    home[home_reports & among],
                    weights=weight[home_reports & among],
                )
            )
            for name, among in groups.items()
        },
        "ucc_690116_percent_of_690114_units_with_children": float(
            100
            * np.sum(away[children] * weight[children])
            / np.sum(home[children] * weight[children])
        ),
    }


def home_internet_against_bls(components: dict) -> dict:
    """Our band's mean home internet over BLS's, by run, band and year."""
    out = {}
    for run in RUNS:
        out[run] = {}
        for band, key in BANDS.items():
            out[run][band] = {}
            for target in TARGETS:
                year = str(target)
                ours = components["runs"][run]["years"][year][key]["band"]
                bls = components["bls"]["years"][year]["band"]
                out[run][band][year] = (
                    ours["pooled"]["internet"] / bls["pooled"]["internet"]
                )
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ce-cache",
        type=Path,
        default=Path.home() / ".cache/spm-calculator/ce-pumd",
    )
    parser.add_argument("--receipt", type=Path, default=RECEIPT)
    args = parser.parse_args()
    started = time.time()
    cpi_document = json.loads(CPI_INPUT.read_text())
    cpi_series = {
        sid: pd.Series({int(y): v for y, v in values.items()})
        for sid, values in cpi_document["series"].items()
    }

    all_quarters = sorted({q for t in TARGETS for q in bls_quarter_window(t)})
    raw, quarters, bundles = {}, {}, {}
    totals = {}
    for quarter in all_quarters:
        fmli = load_ce_quarter(
            *quarter, cache_dir=args.ce_cache, allow_download=False
        )
        source = fmli.attrs["source"]
        bundle = Path(source["bundle_path"])
        bundles.setdefault(
            bundle.name, {"sha256": sha256(bundle), "url": source["url"]}
        )
        if not fmli["NEWID"].is_unique:
            raise ValueError(f"{source['member']}: NEWID repeats")
        records, member = read_ucc_records(fmli)
        name = f"{quarter[0]}Q{quarter[1]}"
        quarters[name] = {
            "fmli_member": source["member"],
            "mtbi_member": member,
            **quarter_record(fmli, records),
        }
        frame = fmli[[c for c in KEEP if c in fmli.columns]].copy()
        frame[INTERNET_COLUMN], _ = unit_costs(fmli, records, HOME_INTERNET)
        frame[AWAY_COLUMN], _ = unit_costs(fmli, records, AWAY_INTERNET)
        frame.attrs = {}
        raw[quarter] = frame
        weight = frame["FINLWT21"].to_numpy(dtype=float)
        children = frame["PERSLT18"].to_numpy(dtype=float) > 0
        totals[quarter] = {
            column: float(
                np.sum(frame[column].to_numpy()[children] * weight[children])
            )
            for column in (INTERNET_COLUMN, AWAY_COLUMN)
        }
        print(f"{name} at {time.time() - started:.0f}s", flush=True)

    replication = json.loads(REPLICATION_RECEIPT.read_text())["results"]
    windows = {}
    for target in TARGETS:
        window = bls_quarter_window(target)
        all_units = (
            100
            * sum(totals[q][AWAY_COLUMN] for q in window)
            / sum(totals[q][INTERNET_COLUMN] for q in window)
        )
        frame = pd.concat([raw[q] for q in window], ignore_index=True)
        run = prepare_out_of_pocket(
            frame,
            target,
            youth_policy="exclude_unresolved",
            cpi_series=cpi_series,
        )
        if (
            run.result["thresholds"]
            != (replication[str(target)]["without_home_internet"])
        ):
            raise RuntimeError(
                f"{target}: the sample is not the replication's"
            )
        sample = run.expenditures
        weight = sample["ce_weight"].to_numpy(dtype=float)
        estimation = (
            100
            * np.sum(sample[AWAY_COLUMN].to_numpy(dtype=float) * weight)
            / np.sum(sample[INTERNET_COLUMN].to_numpy(dtype=float) * weight)
        )
        windows[str(target)] = {
            "first_quarter": "{}Q{}".format(*window[0]),
            "last_quarter": "{}Q{}".format(*window[-1]),
            "ucc_690116_percent_of_690114": {
                "fmli_units_with_children": all_units,
                "estimation_sample": float(estimation),
            },
            "estimation_sample_units": int(len(sample)),
        }
        print(f"Window {target} at {time.time() - started:.0f}s", flush=True)

    components = json.loads(COMPONENTS_RECEIPT.read_text())
    receipt = {
        "schema_version": 1,
        "generated_by": "scripts/tabulate_ce_internet_uccs.py",
        "generated_on": datetime.now(timezone.utc).date().isoformat(),
        "classification": "current_retrospective_research",
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "code_sha256": {p: sha256(ROOT / p) for p in CODE_PATHS},
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
        "inputs": {
            "ce_bundles": dict(sorted(bundles.items())),
            "cpi_input": {
                "path": str(CPI_INPUT.relative_to(ROOT)),
                "sha256": sha256(CPI_INPUT),
            },
            "components_receipt": {
                "path": str(COMPONENTS_RECEIPT.relative_to(ROOT)),
                "sha256": sha256(COMPONENTS_RECEIPT),
            },
            "replication_receipt": {
                "path": str(REPLICATION_RECEIPT.relative_to(ROOT)),
                "sha256": sha256(REPLICATION_RECEIPT),
            },
        },
        "uccs": {
            str(HOME_INTERNET): "Computer information services",
            str(AWAY_INTERNET): "Internet services away from home",
            str(CABLE_TV): "Cable and satellite television services",
        },
        "notes": [
            "Shares reporting count units with at least one MTBI record for "
            "the UCC in the quarter, weighted by FINLWT21",
            "Flag shares of records count UCC 690114 records; weighted flag "
            "shares weight each record by its unit's FINLWT21",
            "Means among reporters are three-month dollars",
            "The estimation sample is the out-of-pocket replication's, with "
            "youth_policy='exclude_unresolved', weighted by its ce_weight",
            "home_internet_against_bls divides each band's pooled mean "
            "internet in the components receipt by BLS's",
        ],
        "quarters": quarters,
        "windows": windows,
        "home_internet_against_bls": home_internet_against_bls(components),
        "runtime_seconds": round(time.time() - started),
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Wrote {args.receipt}", flush=True)


if __name__ == "__main__":
    main()
