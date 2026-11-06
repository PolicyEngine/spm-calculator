"""Print the docs tables from the replicate-weight standard error receipt.

``docs/ce-inkind-imputation.md`` holds these tables verbatim, and
``tests/test_ce_replicates.py`` checks that. This script only formats the
receipt that ``scripts/estimate_ce_replicate_uncertainty.py`` writes.

Run: uv run --no-sync python scripts/render_ce_replicate_tables.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECEIPT = (
    ROOT
    / "spm_calculator/data/current/ce_replicate_uncertainty_2019_2025.json"
)
COMPONENTS_RECEIPT = (
    ROOT
    / "spm_calculator/data/current/ce_inkind_bls_components_2019_2025.json"
)
TENURES = ("renter", "owner_with_mortgage", "owner_without_mortgage")
TENURE_NAMES = {
    "renter": "Renter",
    "owner_with_mortgage": "Owner with mortgage",
    "owner_without_mortgage": "Owner without mortgage",
}
RUN_NAMES = {
    "package": "Package composite CPI",
    "fcsuti": "BLS's FCSUti index",
}
AMOUNT_NAMES = {
    "imputed_total": "All imputed benefits",
    "rental_assistance_per_renter": "Rental assistance per renter",
    "school_lunch": "School lunch",
}
YEARS = tuple(str(year) for year in range(2019, 2026))


def _dollars(value: float) -> str:
    return f"{value:,.0f}"


def _signed_dollars(value: float) -> str:
    return f"{'+' if value >= 0 else '−'}${abs(value):,.0f}"


def _signed(value: float, digits: int = 2) -> str:
    return f"{value:+.{digits}f}".replace("-", "−")


def _with_error(value: str, block: dict, digits: int = 2) -> str:
    return f"{value} ({block['standard_error']:.{digits}f})"


def _row(cells) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _table(header, rows) -> str:
    rule = "|" + "|".join(["---"] + ["---:"] * (len(header) - 1)) + "|"
    return "\n".join([_row(header), rule, *(_row(r) for r in rows)])


def _tenure_header(first: str) -> list[str]:
    return [first, *(TENURE_NAMES[t] for t in TENURES)]


def _levels_table(receipt: dict, run: str) -> str:
    years = receipt["runs"][run]["years"]
    rows = []
    for year in YEARS:
        record = years[year]
        cells = [year]
        for tenure in TENURES:
            ours = record["with_in_kind"][tenure]["standard_error"]
            without = record["without_in_kind"][tenure]["standard_error"]
            bls = record["bls"]["standard_errors"][tenure]
            cells.append(
                f"{_dollars(without)} / {_dollars(ours)} / {_dollars(bls)}"
            )
        rows.append(cells)
    return _table(_tenure_header("Year"), rows)


def _growth_table(receipt: dict) -> str:
    header = [
        "Tenure",
        "Without the stage",
        "With the stage",
        "Stage's change, points",
        "Degrees of freedom",
        "Imputed terms removed",
    ]
    rows = []
    for run in ("package", "fcsuti"):
        rows.append([RUN_NAMES[run], "", "", "", "", ""])
        block = receipt["runs"][run]["growth"]["2022-2025"]
        for tenure in TENURES:
            without = block["without_in_kind"][tenure]
            with_stage = block["with_in_kind"][tenure]
            change = block["stage_change_points"][tenure]
            removed = block["growth_without_imputed_terms"][tenure]
            rows.append(
                [
                    TENURE_NAMES[tenure],
                    _with_error(_signed(without["estimate"]) + "%", without),
                    _with_error(
                        _signed(with_stage["from_mean_thresholds"]) + "%",
                        with_stage,
                    ),
                    _with_error(
                        _signed(change["from_mean_thresholds"]), change
                    ),
                    f"{change['df']:.0f}",
                    _with_error(
                        _signed(removed["from_mean_thresholds"]) + "%",
                        removed,
                    ),
                ]
            )
    return _table(header, rows)


def _year_over_year_table(receipt: dict, run: str) -> str:
    growth = receipt["runs"][run]["growth"]
    rows = []
    for year in YEARS[1:]:
        span = f"{int(year) - 1}–{year}"
        block = growth[f"{int(year) - 1}-{year}"]["stage_change_points"]
        rows.append(
            [span]
            + [
                _with_error(
                    _signed(block[t]["from_mean_thresholds"]), block[t]
                )
                for t in TENURES
            ]
        )
    return _table(_tenure_header("Years"), rows)


def _amounts_table(receipt: dict, components: dict) -> str:
    header = ["Amount", "BLS", *(RUN_NAMES[run] for run in RUN_NAMES)]
    rows = []
    bls = components["bls"]["growth_2022_2025"]
    for name, label in AMOUNT_NAMES.items():
        cells = [label, _signed_dollars(bls[name]["rise"])]
        for run in RUN_NAMES:
            block = receipt["runs"][run]["amount_rise_2022_2025"][name]
            cells.append(
                f"{_signed_dollars(block['estimate'])} "
                f"({block['standard_error']:,.0f})"
            )
        rows.append(cells)
    return _table(header, rows)


def render_tables(receipt: dict, components: dict) -> dict[str, str]:
    """Each docs table, keyed by name."""
    return {
        "levels": _levels_table(receipt, "package"),
        "growth": _growth_table(receipt),
        "year_over_year": _year_over_year_table(receipt, "package"),
        "amounts": _amounts_table(receipt, components),
    }


def summarize(receipt: dict) -> dict:
    """Figures the docs prose quotes."""
    out = {}
    for run in RUN_NAMES:
        record = receipt["runs"][run]
        ratios = record["ratio_to_bls_standard_error_range"]
        years = record["years"]
        dfs = [
            years[y]["with_in_kind"][t]["df"] for y in YEARS for t in TENURES
        ]
        fractions = [
            years[y]["with_in_kind"][t]["fraction_missing_information"]
            for y in YEARS
            for t in TENURES
        ]
        within = [
            years[y]["ratio_to_bls_standard_error"]["with_in_kind_within"][t]
            for y in YEARS
            for t in TENURES
        ]
        out[run] = {
            "ratio_to_bls_without": ratios["without_in_kind"],
            "ratio_to_bls_with": ratios["with_in_kind"],
            "ratio_to_bls_within": [min(within), max(within)],
            "level_df_range": [min(dfs), max(dfs)],
            "fraction_missing_range": [min(fractions), max(fractions)],
            "growth_2022_2025": {
                key: {
                    t: {
                        "estimate": block[t].get(
                            "from_mean_thresholds", block[t]["estimate"]
                        ),
                        "standard_error": block[t]["standard_error"],
                        "df": block[t]["df"],
                        "t_975": block[t]["t_975"],
                    }
                    for t in TENURES
                }
                for key, block in record["growth"]["2022-2025"].items()
                if key != "bls_growth"
            },
        }
    return out


def main() -> None:
    receipt = json.loads(RECEIPT.read_text())
    components = json.loads(COMPONENTS_RECEIPT.read_text())
    for name, table in render_tables(receipt, components).items():
        print(f"{name}:\n\n{table}\n")
    print(json.dumps(summarize(receipt), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
