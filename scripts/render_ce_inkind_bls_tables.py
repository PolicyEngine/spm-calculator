"""Print the docs tables and ranges from the BLS components receipt.

``docs/ce-inkind-imputation.md`` holds these tables verbatim, and
``tests/test_ce_bls_shares.py`` checks that. This script only formats the
receipt that ``scripts/compare_ce_inkind_bls_shares.py`` writes.

Run: uv run --no-sync python scripts/render_ce_inkind_bls_tables.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from spm_calculator.ce_bls_shares import (
    ACCOUNTINGS,
    OTHER,
    TENURES,
    BandComponents,
)

ROOT = Path(__file__).resolve().parent.parent
RECEIPT = (
    ROOT
    / "spm_calculator/data/current/ce_inkind_bls_components_2019_2025.json"
)
TENURE_NAMES = {
    "renter": "Renter",
    "owner_with_mortgage": "Owner with mortgage",
    "owner_without_mortgage": "Owner without mortgage",
}
#: Shelter pieces BLS's papers leave out.
OUTSIDE_BLS_SHELTER = (
    "other_lodging",
    "vacation_home_principal",
    "rent_as_pay",
)
GAP_ROWS = (
    ("imputed", "Imputed benefits"),
    ("shelter", "Shelter"),
    ("internet", "Home internet"),
    ("utilities", "Utilities"),
    ("food", "Food"),
    ("clothing", "Clothing"),
    ("telephone", "Telephone"),
)
#: The extra row under the ``other_separate`` accounting.
OTHER_ROW = (OTHER, "Other (0.2 × FCSUti)")


def _range(values) -> dict[str, float]:
    values = [float(v) for v in values]
    return {"min": min(values), "max": max(values)}


def _years(receipt: dict) -> list[str]:
    return sorted(receipt["bls"]["years"])


def _outside_bls_shelter(pieces: dict) -> float:
    return sum(pieces[piece] for piece in OUTSIDE_BLS_SHELTER)


def summarize(receipt: dict) -> dict:
    """The ranges the docs page states in prose."""
    years = _years(receipt)
    bls = receipt["bls"]["years"]
    summary = {
        "bls_identity_largest_error_dollars": max(
            max(
                abs(bls[y]["checks"]["fcsuti_error_dollars"]),
                *(
                    abs(v)
                    for v in bls[y]["checks"][
                        "threshold_error_dollars"
                    ].values()
                ),
            )
            for y in years
        ),
        "bls_shared_component_largest_spread_dollars": max(
            max(bls[y]["checks"]["shared_component_spread_dollars"].values())
            for y in years
        ),
        "bls_other_separate_largest_share_error": max(
            max(bls[y]["checks"]["other_separate_share_error"].values())
            for y in years
        ),
        "bls_internet_percent_of_threshold": {
            accounting: _range(
                100
                * _bls_term(receipt, y, t, "internet", accounting)
                / bls[y]["published_thresholds"][t]
                for y, t in [(y, t) for y in years for t in TENURES]
            )
            for accounting in ACCOUNTINGS
        },
        "runs": {},
    }
    cells = [(y, t) for y in years for t in TENURES]
    for run, record in receipt["runs"].items():
        data = record["years"]
        growth = record["growth_2022_2025"]["by_tenure"]
        gaps_without = [
            data[y]["without_in_kind"]["gap_percent"][t] for y, t in cells
        ]
        gaps_with = [
            data[y]["with_in_kind"]["gap_percent"][t] for y, t in cells
        ]
        block = {
            "gap_percent_without": _range(gaps_without),
            "gap_percent_with": _range(gaps_with),
            "gap_percent_without_mean_absolute": float(
                np.mean(np.abs(gaps_without))
            ),
            "gap_percent_with_mean_absolute": float(
                np.mean(np.abs(gaps_with))
            ),
            "cells_above_bls_with": int(sum(g > 0 for g in gaps_with)),
            "cells_within_one_percent_with": int(
                sum(abs(g) < 1 for g in gaps_with)
            ),
            "tenure_mix_points_from_bls": {
                t: _range(
                    100
                    * (
                        data[y]["with_in_kind"]["band"]["tenure_mix"][t]
                        - bls[y]["band"]["tenure_mix"][t]
                    )
                    for y in years
                )
                for t in TENURES
            },
            "rental_assistance_per_renter_ratio": _range(
                data[y]["with_in_kind"]["band"]["by_tenure"]["renter"][
                    "rental_assistance"
                ]
                / bls[y]["band"]["by_tenure"]["renter"]["rental_assistance"]
                for y in years
            ),
            "school_lunch_ratio": _range(
                data[y]["with_in_kind"]["band"]["pooled"]["nslp"]
                / bls[y]["band"]["pooled"]["nslp"]
                for y in years
            ),
            "imputed_total_ratio_by_year": {
                y: data[y]["with_in_kind"]["imputed_total"]
                / bls[y]["imputed_total"]
                for y in years
            },
            "shelter_excess_dollars": _range(
                data[y]["shelter_excess_dollars"][t] for y, t in cells
            ),
            "shelter_excess_less_bls_internet_dollars": _range(
                data[y]["shelter_excess_dollars"][t]
                - bls[y]["band"]["pooled"]["internet"]
                for y, t in cells
            ),
            "meals_as_pay_dollars": _range(
                data[y]["with_in_kind"]["band_pieces"]["pooled"][
                    "meals_as_pay"
                ]
                for y in years
            ),
            "level_gap_points": {
                accounting: _level_gap_points(data, years, accounting)
                for accounting in ACCOUNTINGS
            },
            "rank_shift_points": {
                t: growth[t]["other_spread"]["rank_shift_points"]
                for t in TENURES
            },
        }
        if not record["bls_written_definitions"]:
            block["vacation_utilities_dollars"] = {
                t: _range(
                    data[y]["with_in_kind"]["band_pieces"][t][
                        "vacation_utilities"
                    ]
                    for y in years
                )
                for t in TENURES
            }
            block["other_lodging_dollars"] = _range(
                data[y]["with_in_kind"]["band_pieces"][t]["other_lodging"]
                for y, t in cells
            )
            block["other_lodging_share_of_shelter_excess_percent"] = _range(
                100
                * data[y]["with_in_kind"]["band_pieces"][t]["other_lodging"]
                / data[y]["shelter_excess_dollars"][t]
                for y, t in cells
            )
            block["outside_bls_share_of_shelter_excess_percent"] = _range(
                100
                * _outside_bls_shelter(
                    data[y]["with_in_kind"]["band_pieces"][t]
                )
                / data[y]["shelter_excess_dollars"][t]
                for y, t in cells
            )
        summary["runs"][run] = block
    return summary


def _bls_term(
    receipt: dict, year: str, tenure: str, term: str, accounting: str
) -> float:
    """One of BLS's threshold terms, rebuilt from the receipt's band."""
    band = receipt["bls"]["years"][year]["band"]
    return BandComponents(
        band["pooled"], band["by_tenure"], band["tenure_mix"]
    ).threshold_terms(tenure, accounting)[term]


def _level_gap_points(data: dict, years: list, accounting: str) -> dict:
    out = {}
    for t in TENURES:
        records = [
            data[y]["level_gap_percent_of_bls"][accounting][t] for y in years
        ]
        out[t] = {
            term: _range(r["terms"][term] for r in records)
            for term in records[0]["terms"]
        } | {
            "imputed": _range(r["imputed"] for r in records),
            "shelter_plus_internet": _range(
                r["terms"]["shelter"] + r["terms"]["internet"] for r in records
            ),
        }
    return out


def _dollars(value: float) -> str:
    # MyST reads paired dollar signs as math, so escape each one.
    return f"\\${value:,.0f}"


def _signed_dollars(value: float) -> str:
    return f"{'+' if value >= 0 else '−'}\\${abs(value):,.0f}"


def _signed(value: float, digits: int = 2) -> str:
    return f"{value:+.{digits}f}".replace("-", "−")


def _rate(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace("-", "−")


def _row(cells) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _table(header, rows) -> str:
    rule = "|" + "|".join(["---"] + ["---:"] * (len(header) - 1)) + "|"
    return "\n".join([_row(header), rule, *(_row(r) for r in rows)])


def _level_gap_table(receipt: dict, run: str, accounting: str) -> str:
    gaps = summarize(receipt)["runs"][run]["level_gap_points"][accounting]
    rows = GAP_ROWS + ((OTHER_ROW,) if accounting == "other_separate" else ())
    return _table(
        ["Term", *TENURE_NAMES.values()],
        [
            [
                label,
                *(
                    f"{_signed(gaps[t][key]['min'])} to "
                    f"{_signed(gaps[t][key]['max'])}"
                    for t in TENURES
                ),
            ]
            for key, label in rows
        ],
    )


def _gap_table(receipt: dict, run: str) -> str:
    data = receipt["runs"][run]["years"]
    return _table(
        ["Target", *TENURE_NAMES.values()],
        [
            [
                y,
                *(
                    f"{_signed(data[y]['without_in_kind']['gap_percent'][t])}"
                    " → "
                    f"{_signed(data[y]['with_in_kind']['gap_percent'][t])}"
                    for t in TENURES
                ),
            ]
            for y in _years(receipt)
        ],
    )


def render_tables(receipt: dict) -> dict[str, str]:
    """The docs page's comparison tables, by name."""
    years = _years(receipt)
    bls = receipt["bls"]["years"]
    package = receipt["runs"]["package"]["years"]
    tables = {}

    amounts = []
    for y in years:
        ours = package[y]["with_in_kind"]
        theirs = bls[y]["band"]
        amounts.append(
            [
                y,
                f"{_dollars(ours['imputed_total'])} / "
                f"{_dollars(bls[y]['imputed_total'])}",
                f"{_dollars(ours['band']['by_tenure']['renter']['rental_assistance'])}"
                " / "
                f"{_dollars(theirs['by_tenure']['renter']['rental_assistance'])}",
                f"{_dollars(ours['band']['pooled']['nslp'])} / "
                f"{_dollars(theirs['pooled']['nslp'])}",
            ]
        )
    tables["imputed_amounts"] = _table(
        [
            "Target",
            "All imputed benefits",
            "Rental assistance per renter",
            "School lunch",
        ],
        amounts,
    )

    tables["tenure_mix"] = _table(
        ["Target", *TENURE_NAMES.values()],
        [
            [
                y,
                *(
                    f"{_rate(100 * package[y]['with_in_kind']['band']['tenure_mix'][t])}"
                    " / "
                    f"{_rate(100 * bls[y]['band']['tenure_mix'][t])}"
                    for t in TENURES
                ),
            ]
            for y in years
        ],
    )

    tables["shelter_excess"] = _table(
        ["Target", *TENURE_NAMES.values(), "BLS home internet"],
        [
            [
                y,
                *(
                    f"{_dollars(package[y]['shelter_excess_dollars'][t])} "
                    f"({_dollars(_outside_bls_shelter(package[y]['with_in_kind']['band_pieces'][t]))})"
                    for t in TENURES
                ),
                _dollars(bls[y]["band"]["pooled"]["internet"]),
            ]
            for y in years
        ],
    )

    tables["level_gap"] = _level_gap_table(receipt, "package", "other_spread")
    tables["level_gap_other_separate"] = _level_gap_table(
        receipt, "package", "other_separate"
    )
    tables["level_gap_bls_definitions"] = _level_gap_table(
        receipt, "package_bls_definition", "other_spread"
    )
    tables["level_gap_bls_definitions_other_separate"] = _level_gap_table(
        receipt, "package_bls_definition", "other_separate"
    )
    tables["gap_bls_definitions_package"] = _gap_table(
        receipt, "package_bls_definition"
    )
    tables["gap_bls_definitions_fcsuti"] = _gap_table(
        receipt, "fcsuti_bls_definition"
    )

    bls_growth = receipt["bls"]["growth_2022_2025"]
    all_runs = (
        "package",
        "fcsuti",
        "package_bls_definition",
        "fcsuti_bls_definition",
    )
    tables["growth_by_definition"] = _table(
        [
            "Tenure",
            "BLS corrected",
            "Replication's definitions, package CPI",
            "Replication's definitions, FCSUti index",
            "BLS's written definitions, package CPI",
            "BLS's written definitions, FCSUti index",
        ],
        [
            [
                TENURE_NAMES[t],
                f"{_signed(bls_growth['by_tenure'][t]['growth'])}%",
                *(
                    f"{_signed(receipt['runs'][run]['growth_2022_2025']['by_tenure'][t]['growth_with_stage'])}%"
                    for run in all_runs
                ),
            ]
            for t in TENURES
        ],
    )

    tables["stage_change"] = _table(
        ["Tenure", *("Package CPI", "FCSUti index")],
        [
            [
                TENURE_NAMES[t],
                *(
                    _stage_change(receipt["runs"][run], t)
                    for run in ("package", "fcsuti")
                ),
            ]
            for t in TENURES
        ],
    )

    series = (
        ("BLS", bls_growth),
        ("Ours, package CPI", receipt["runs"]["package"]["growth_2022_2025"]),
        ("Ours, FCSUti index", receipt["runs"]["fcsuti"]["growth_2022_2025"]),
    )

    def path(block: dict) -> str:
        return (
            f"{_dollars(block['2022'])} → {_dollars(block['2025'])} "
            f"({_signed_dollars(block['rise'])})"
        )

    tables["imputed_growth"] = _table(
        [
            "Series",
            "All imputed benefits",
            "Rental assistance per renter",
            "School lunch",
        ],
        [
            [
                label,
                path(block["imputed_total"]),
                path(block["rental_assistance_per_renter"]),
                path(block["school_lunch"]),
            ]
            for label, block in series
        ],
    )

    def triple(block: dict, accounting: str, key: str, render) -> str:
        return " / ".join(
            render(block["by_tenure"][t][accounting][key]) for t in TENURES
        )

    share = "imputed_share_of_growth_beyond_cpi_u_percent"
    tables["imputed_part_of_growth"] = _table(
        [
            "Series",
            "Share of growth beyond CPI-U, Other spread, %",
            "Share of growth beyond CPI-U, Other separate, %",
            "Points of growth, Other spread",
            "Growth without imputed terms, Other spread, %",
        ],
        [
            [
                label,
                triple(block, "other_spread", share, _rate),
                triple(block, "other_separate", share, _rate),
                triple(
                    block, "other_spread", "band_fixed_effect_points", _signed
                ),
                triple(
                    block,
                    "other_spread",
                    "growth_without_imputed_terms",
                    lambda v: _rate(v, 2),
                ),
            ]
            for label, block in series
        ],
    )

    tables["shortfall"] = _table(
        [
            "Tenure",
            "Replication's definitions, package CPI",
            "Replication's definitions, FCSUti index",
            "BLS's written definitions, package CPI",
            "BLS's written definitions, FCSUti index",
        ],
        [
            [
                TENURE_NAMES[t],
                *(_shortfall(receipt["runs"][run], t) for run in all_runs),
            ]
            for t in TENURES
        ],
    )
    return tables


def _stage_change(run: dict, tenure: str) -> str:
    growth = run["growth_2022_2025"]["by_tenure"][tenure]
    return (
        f"{_signed(growth['stage_change_points'])} "
        f"({_rate(growth['stage_change_between_implicate_sd'], 2)})"
    )


def _shortfall(run: dict, tenure: str) -> str:
    growth = run["growth_2022_2025"]["by_tenure"][tenure]
    return (
        f"{_signed(growth['growth_less_bls_points'])} → "
        f"{_signed(growth['other_spread']['growth_without_imputed_terms_less_bls_points'])}"
    )


def main() -> None:
    receipt = json.loads(RECEIPT.read_text())
    for name, table in render_tables(receipt).items():
        print(f"{name}:\n\n{table}\n")
    print(json.dumps(summarize(receipt), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
