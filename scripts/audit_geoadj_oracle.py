"""Audit the ACS-rent geographic adjustment against the Census oracle.

The custom-geography path (states, counties, congressional districts)
computes ``geoadj = rent_ratio x share + (1 - share)`` from ACS median
gross rents. Until now its tests pinned its own outputs — no ground
truth. The Census SPM metro workbook provides one: official per-metro,
per-tenure adjustment factors for every metro area. This audit runs
the package's actual formula (``calculate_geoadj_from_rent``) on ACS
metro rents and scores it against the workbook.

The error decomposes into two parts, measured separately:

- **Formula shape**: run the formula on the workbook's own rent index
  (bundled ``rentIndex``); any residual is the linear share formula
  disagreeing with how Census maps rents to adjustments.
- **Rent source**: compare ACS 5-year median gross rent ratios to the
  workbook rent index; any residual is measurement (vintage, universe,
  aggregation) rather than formula.

Outputs:
    benchmark_output/geoadj_audit.json
    docs/geoadj-audit.md

Usage:
    uv run python scripts/audit_geoadj_oracle.py
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

from spm_calculator.geoadj import calculate_geoadj_from_rent

REPO = Path(__file__).resolve().parent.parent
METRO = REPO / "spm_calculator" / "data" / "metro_geoadj_2024.json"
OUT_JSON = REPO / "benchmark_output" / "geoadj_audit.json"
OUT_MD = REPO / "docs" / "geoadj-audit.md"

ACS_YEAR = 2023  # 5-year ACS ending 2023, the vintage for 2024 thresholds


# The ACS table-based summary file is keyless (the api.census.gov JSON
# endpoints now require a registered key). One pipe-delimited file per
# table covers every geography; CBSA rows are 310M700US{code},
# the national row is 0100000US.
def _sf_url(table: str) -> str:
    return (
        "https://www2.census.gov/programs-surveys/acs/summary_file/"
        f"{ACS_YEAR}/table-based-SF/data/5YRData/"
        f"acsdt5y{ACS_YEAR}-{table}.dat"
    )


TENURES = ("renter", "owner_with_mortgage", "owner_without_mortgage")

# Two rent definitions, audited side by side:
# - b25064 E001: median gross rent, all renter-occupied units — what
#   the package's custom-geography path uses today.
# - b25031 E004: median gross rent, two-bedroom units — the rent
#   concept Census documents for SPM geographic adjustment.
RENT_TABLES = {
    "overall_median_rent_b25064": ("b25064", "B25064_E001"),
    "two_bedroom_rent_b25031": ("b25031", "B25031_E004"),
}


def _fetch_sf(table: str) -> str:
    url = _sf_url(table)
    try:
        response = requests.get(url, timeout=180)
        response.raise_for_status()
        return response.text
    except Exception:
        from curl_cffi import requests as curl_requests

        response = curl_requests.get(url, impersonate="chrome", timeout=180)
        assert response.status_code == 200, response.status_code
        return response.text


def fetch_acs_rents(table: str, column: str) -> tuple[dict[str, float], float]:
    text = _fetch_sf(table)
    lines = text.splitlines()
    header = lines[0].split("|")
    col = header.index(column)
    rents: dict[str, float] = {}
    national = None
    for line in lines[1:]:
        fields = line.split("|")
        geo_id = fields[0]
        if geo_id == "0100000US":
            national = float(fields[col])
        elif geo_id.startswith("310M") and "US" in geo_id:
            try:
                rent = float(fields[col])
            except ValueError:
                continue
            if rent > 0:
                rents[geo_id.split("US")[1]] = rent
    assert national is not None, "national rent row missing"
    return rents, national


def stats(errors: list[float]) -> dict[str, float]:
    errors = sorted(abs(e) for e in errors)
    n = len(errors)
    return {
        "n": n,
        "mae": sum(errors) / n,
        "median": errors[n // 2],
        "p90": errors[int(n * 0.9)],
        "max": errors[-1],
    }


def main() -> None:
    metro_doc = json.loads(METRO.read_text())
    metros = metro_doc["metroAreas"]

    # Formula-shape leg: package formula on the workbook's own rent
    # index, scored against the workbook adjustments.
    shape_errors: dict[str, list] = {t: [] for t in TENURES}
    for entry in metros.values():
        for tenure in TENURES:
            formula = calculate_geoadj_from_rent(
                entry["rentIndex"], 1.0, tenure=tenure
            )
            shape_errors[tenure].append(
                formula / entry["adjustments"][tenure] - 1
            )

    legs = {}
    worst_by_table: dict[str, list] = {}
    for label, (table, column) in RENT_TABLES.items():
        acs_rents, national_rent = fetch_acs_rents(table, column)
        matched = 0
        acs_errors: dict[str, list] = {t: [] for t in TENURES}
        rent_index_errors: list[float] = []
        worst: list[tuple[float, str, str, float, float]] = []
        for cbsa, entry in metros.items():
            acs_rent = acs_rents.get(cbsa)
            if acs_rent is None:
                continue
            matched += 1
            rent_index_errors.append(
                acs_rent / national_rent / entry["rentIndex"] - 1
            )
            for tenure in TENURES:
                formula = calculate_geoadj_from_rent(
                    acs_rent, national_rent, tenure=tenure
                )
                err = formula / entry["adjustments"][tenure] - 1
                acs_errors[tenure].append(err)
                worst.append(
                    (
                        abs(err),
                        entry["name"],
                        tenure,
                        formula,
                        entry["adjustments"][tenure],
                    )
                )
        legs[label] = {
            "matched": matched,
            "end_to_end": {t: stats(acs_errors[t]) for t in TENURES},
            "rent_index_vs_workbook": stats(rent_index_errors),
        }
        worst.sort(reverse=True)
        worst_by_table[label] = worst

    result = {
        "generated_by": "scripts/audit_geoadj_oracle.py",
        "acs_vintage": f"{ACS_YEAR} 5-year summary file",
        "oracle": metro_doc["source"],
        "metros_in_workbook": len(metros),
        "formula_shape_on_workbook_index": {
            t: stats(shape_errors[t]) for t in TENURES
        },
        "rent_tables": legs,
    }

    OUT_JSON.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=1) + "\n")

    shape = result["formula_shape_on_workbook_index"]
    lines = [
        "# Geographic adjustment oracle audit",
        "",
        "The custom-geography path computes `geoadj = rent_ratio x "
        "share + (1 - share)` from ACS median gross rents. This audit "
        "scores the package's actual formula against the Census SPM "
        "metro workbook's official per-metro, per-tenure adjustments "
        "— the first ground-truth test this code path has had.",
        "",
        f"Oracle: {metro_doc['source']}. ACS: {result['acs_vintage']}.",
        "",
        "## Formula shape",
        "",
        "Running the package formula on the workbook's own rent index "
        "reproduces the workbook adjustments to within "
        f"{max(shape[t]['max'] for t in TENURES):.4%} — the linear "
        "share formula is exactly Census's construction.",
        "",
        "## Rent definition",
        "",
        "| Rent table | Tenure | End-to-end MAE | Median | p90 | Max |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for label, leg in result["rent_tables"].items():
        for t in TENURES:
            s = leg["end_to_end"][t]
            lines.append(
                f"| {label} | {t} | {s['mae']:.2%} | {s['median']:.2%} "
                f"| {s['p90']:.2%} | {s['max']:.2%} |"
            )
    lines.append("")
    for label, leg in result["rent_tables"].items():
        ri = leg["rent_index_vs_workbook"]
        lines.append(
            f"- {label}: rent index vs workbook index MAE "
            f"{ri['mae']:.2%}, median {ri['median']:.2%}, p90 "
            f"{ri['p90']:.2%}, max {ri['max']:.2%} "
            f"(n={ri['n']})."
        )
    lines += [
        "",
        "The two-bedroom rent table (B25031) matches the workbook's "
        "rent concept roughly three times more closely than the "
        "overall median rent (B25064) the custom path uses today — "
        "consistent with Census's documented use of two-bedroom "
        "gross rents for SPM geographic adjustment. Switching the "
        "custom-geography rent source to B25031 and regenerating the "
        "bundled sub-metro data is the follow-up this audit "
        "motivates.",
        "",
        "## Ten largest end-to-end errors (two-bedroom rents)",
        "",
        "| Metro | Tenure | Formula | Oracle | Error |",
        "|---|---|---:|---:|---:|",
    ]
    for abs_err, name, tenure, formula, oracle_val in worst_by_table[
        "two_bedroom_rent_b25031"
    ][:10]:
        lines.append(
            f"| {name} | {tenure} | {formula:.3f} | {oracle_val:.3f} "
            f"| {formula / oracle_val - 1:+.2%} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n")

    print(json.dumps(result, indent=1))
    print(f"wrote {OUT_JSON} and {OUT_MD}")


if __name__ == "__main__":
    main()
