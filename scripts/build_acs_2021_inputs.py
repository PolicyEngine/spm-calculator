"""Rebuild 2021 ACS geography/topcodes offline from retained Census sources.

This streams small geography products and source hashes, never housing CSVs.
County population fractions are a PUMS geography proxy, not household locations.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from collections import defaultdict
from pathlib import Path

from spm_calculator.acs_forecast_sources import (
    load_source_bundle,
    sha256_file,
    verify_file,
)
from spm_calculator.forecast_inputs import load_horizon_inputs
from spm_calculator.release import canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "spm_calculator/data/current"


def gazetteer(cache, name):
    with zipfile.ZipFile(cache / "geography" / name) as archive:
        if len(archive.namelist()) != 1:
            raise ValueError("Unexpected Gazetteer archive")
        with archive.open(archive.namelist()[0]) as handle:
            yield from csv.DictReader(
                io.TextIOWrapper(handle, encoding="latin1"), delimiter="\t"
            )


def validate_boundary_transfer(cache, tract_population):
    populations = {}
    totals = {}
    for tract in ("021304", "021322"):
        rows = json.loads(
            (
                cache
                / f"geography/2010-sf1-06061-{tract}-block-populations.json"
            ).read_text()
        )[1:]
        if any(r[1:4] != ["06", "061", tract] for r in rows):
            raise ValueError("Unexpected source block geography")
        parsed = {"".join(r[1:]): int(r[0]) for r in rows}
        if len(parsed) != len(rows):
            raise ValueError("Duplicate source block")
        populations.update(parsed)
        totals["06061" + tract] = sum(parsed.values())
        if totals["06061" + tract] != tract_population["06061" + tract]:
            raise ValueError(
                "Block totals do not match Census tract population"
            )
    affected = set()
    by_block = defaultdict(set)
    land = 0
    with zipfile.ZipFile(
        cache / "geography/TAB2010_TAB2020_ST06.zip"
    ) as archive:
        with archive.open(archive.namelist()[0]) as handle:
            for r in csv.DictReader(
                io.TextIOWrapper(handle, encoding="utf-8-sig"), delimiter="|"
            ):
                if r["COUNTY_2010"] == "061" and r["TRACT_2010"] in (
                    "021304",
                    "021322",
                ):
                    block = (
                        r["STATE_2010"]
                        + r["COUNTY_2010"]
                        + r["TRACT_2010"]
                        + r["BLK_2010"]
                    )
                    by_block[block].add(r["COUNTY_2020"])
                    if r["COUNTY_2020"] == "115":
                        affected.add(block)
                        land += int(r["AREALAND_INT"])
    if (
        len(affected) != 10
        or land != 457057
        or any(populations[b] != 0 for b in affected)
    ):
        raise ValueError(
            "Documented transfer is no longer verified zero population"
        )
    return {
        "status": "verified_zero_population_transfer",
        "affected_source_blocks": len(affected),
        "split_source_blocks": sum(len(by_block[b]) > 1 for b in affected),
        "affected_source_population_2010": 0,
        "transferred_land_square_meters": land,
        "population_variable": "2010 Census SF1 P001001",
        "population_imputed_by_area": False,
        "queried_tract_populations_match_gazetteer": totals,
        "scope_note": "Closes this documented legal transfer; no claim that every2010 and2020county polygon is geometrically identical.",
    }


def build_inputs(cache):
    manifest_path = CURRENT / "acs_2021_source_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for source in manifest["sources"]:
        verify_file(cache / source["cache_path"], source["sha256"])
    horizon = load_horizon_inputs()
    assignments = horizon["county_assignments"]["maps"]["2022"]
    county_to_area = {
        county: area
        for county, area in assignments.items()
        if area.startswith("modeled_residual_metro:")
    }
    if len(county_to_area) != 33 or len(set(county_to_area.values())) != 7:
        raise ValueError("Historical residual county coverage changed")
    tract_pop = {
        r["GEOID"]: int(r["POP10"])
        for r in gazetteer(cache, "Gaz_tracts_national.zip")
        if int(r["GEOID"][:2]) <= 56
    }
    expected = {
        r["GEOID"]: int(r["POP10"])
        for r in gazetteer(cache, "2010_Gaz_PUMAs_national.zip")
        if int(r["GEOID"][:2]) <= 56
    }
    total = defaultdict(int)
    allocated = defaultdict(int)
    seen = set()
    with (
        cache / "geography/2010_Census_Tract_to_2010_PUMA.txt"
    ).open() as handle:
        for row in csv.DictReader(handle):
            if int(row["STATEFP"]) > 56:
                continue
            county = row["STATEFP"] + row["COUNTYFP"]
            tract = county + row["TRACTCE"]
            puma = row["STATEFP"] + row["PUMA5CE"]
            if tract in seen:
                raise ValueError("Duplicate Census tract")
            seen.add(tract)
            population = tract_pop[tract]
            total[puma] += population
            allocated[puma, county_to_area.get(county)] += population
    if (
        seen != set(tract_pop)
        or dict(total) != expected
        or len(total) != 2351
        or sum(total.values()) != 308745538
    ):
        raise ValueError("2010 tract/PUMA population reconciliation failed")
    allocations = [
        {
            "puma_geoid": puma,
            "area_code": area,
            "fraction": population / total[puma],
        }
        for (puma, area), population in sorted(
            allocated.items(), key=lambda item: (item[0][0], item[0][1] or "")
        )
        if population > 0
    ]
    sums = defaultdict(float)
    for row in allocations:
        sums[row["puma_geoid"]] += row["fraction"]
    if set(sums) != set(total) or any(
        abs(value - 1) > 1e-12 for value in sums.values()
    ):
        raise ValueError("Incomplete historical PUMA allocation")
    pairs = {
        "RNTP": ("RNTTPCT", "T_RNT"),
        "ELEP": ("ELETPCT", "T_ELE"),
        "GASP": ("GASTPCT", "T_GAS"),
        "FULP": ("FULTPCT", "T_FUL"),
        "WATP": ("WATTPCT", "T_WAT"),
    }
    topcodes = {}
    with (
        cache
        / "methodology/topcodes/2017_pums_top_and_bottom_coded_values.csv"
    ).open() as handle:
        for row in csv.DictReader(handle):
            state = row["bst"].zfill(2)
            if not state.isdigit():
                continue
            if state in topcodes:
                raise ValueError("Duplicate topcode state")
            topcodes[state] = {
                variable: {
                    "threshold": float(row[t]) if row[t].strip() else None,
                    "replacement": float(row[r]) if row[r].strip() else None,
                }
                for variable, (t, r) in pairs.items()
            }
    if len(topcodes) != 52:
        raise ValueError("Incomplete2017topcodes")
    transfer = validate_boundary_transfer(cache, tract_pop)
    original = load_source_bundle()
    result = {
        "schema_version": 1,
        "kind": "acs_2021_historical_source_inputs",
        "information_date": "2026-09-09",
        "window_start": 2017,
        "window_end": 2021,
        "sources": manifest["sources"],
        "area_allocations": allocations,
        "topcodes": {**original["topcodes"], "2017": topcodes},
        "geography_method": {
            "puma_vintage": 2010,
            "county_vintage": 2010,
            "population_year": 2010,
            "county_lookup_vintage": 2020,
            "method": "Join Census2010tract POP10 to2010PUMAs, sum by county and PUMA, allocate each declared county group its share of totalPUMA population. Preserve unassigned mass for the national denominator.",
            "interpretation": "Population allocation approximates PUMS household geography; it does not identify actual household counties.",
            "documented_yuba_transfer": transfer,
        },
        "validation": {
            "puma_count": len(total),
            "tract_count": len(seen),
            "population_2010": sum(total.values()),
            "county_count": len(county_to_area),
            "modeled_group_count": 7,
            "all_puma_populations_match_independent_gazetteer": True,
            "maximum_allocation_sum_error": max(
                abs(v - 1) for v in sums.values()
            ),
        },
        "generator_sha256": sha256_file(Path(__file__)),
        "manifest_sha256": sha256_file(manifest_path),
        "county_assignment_sha256": horizon["county_assignments"]["sha256"],
    }
    result["content_sha256"] = hashlib.sha256(
        canonical_bytes(result)
    ).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache/spm-calculator/acs-pums",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = (
        json.dumps(
            build_inputs(args.cache_dir),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode()
    out = CURRENT / "acs_2021_source_inputs.json"
    if args.check:
        if out.read_bytes() != content:
            raise ValueError(
                "Historical source bundle differs from offline rebuild"
            )
    else:
        out.write_bytes(content)
    print(hashlib.sha256(content).hexdigest())


if __name__ == "__main__":
    main()
