"""Render the step 1 note's generated blocks from the reproduction results.

``docs/census-spm-reproduction.md`` holds blocks between
``<!-- BEGIN GENERATED: name -->`` and ``<!-- END GENERATED: name -->``
markers. :func:`render_blocks` builds each block from
``spm_calculator/data/census_spm/reproduction_2025.json`` and
:func:`apply_blocks` writes them into the note, so every number in those
blocks comes from the results file. A test checks that the committed note
matches a fresh rendering.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional

BLOCK = re.compile(
    r"(<!-- BEGIN GENERATED: (?P<name>[a-z0-9_]+) -->\n)"
    r"(?P<body>.*?)"
    r"(<!-- END GENERATED: (?P=name) -->)",
    re.DOTALL,
)

GROUP_HEADERS = ("All people", "Under 18", "18 to 64", "65 and older")

#: The largest-gaps block lists Table 5 effects and Table 4 percentages
#: whose gaps reach these sizes, in percentage points.
EFFECT_GAP_SHOWN = 0.03
PERCENT_GAP_SHOWN = 0.2

IDENTITY_LABELS = (
    (
        "resources_identity_max_gap",
        "Largest gap between SPM_RESOURCES and its components (dollars)",
    ),
    (
        "poor_flag_mismatches",
        "People whose SPM_POOR differs from resources < threshold",
    ),
    (
        "federal_tax_identity_max_gap",
        "Largest gap between SPM_FEDTAX and SPM_FEDTAXBC - SPM_EITC - "
        "SPM_ACTC (dollars)",
    ),
    (
        "cash_income_identity_max_gap",
        "Largest gap between SPM_TOTVAL and the unit's summed PTOTVAL "
        "(dollars)",
    ),
    (
        "units_with_varying_spm_fields",
        "SPM units whose unit-level fields vary across members",
    ),
    ("units_without_one_head", "SPM units without exactly one SPM_HEAD"),
    (
        "tax_units_spanning_spm_units",
        "Tax units (TAX_ID) that span two or more SPM units",
    ),
    (
        "spm_eitc_vs_eit_cred_max_gap",
        "Largest gap between SPM_EITC and the unit's summed EIT_CRED "
        "(dollars)",
    ),
    (
        "spm_actc_vs_actc_crd_max_gap",
        "Largest gap between SPM_ACTC and the unit's summed ACTC_CRD "
        "(dollars)",
    ),
    (
        "spm_fedtaxbc_vs_fedtax_bc_max_gap",
        "Largest gap between SPM_FEDTAXBC and the unit's summed FEDTAX_BC "
        "(dollars)",
    ),
    (
        "spm_fedtax_vs_fedtax_ac_max_gap",
        "Largest gap between SPM_FEDTAX and the unit's summed FEDTAX_AC "
        "(dollars)",
    ),
    (
        "spm_sttax_vs_statetax_a_max_gap",
        "Largest gap between SPM_STTAX and the unit's summed STATETAX_A "
        "(dollars)",
    ),
    (
        "spm_fica_vs_fica_max_gap",
        "Largest gap between SPM_FICA and the unit's summed FICA (dollars)",
    ),
    (
        "persons_without_replicate_weights",
        "People without replicate weights",
    ),
    ("negative_weights", "People with a negative weight"),
)

#: Checks that inform without gating the reproduction.
INFORMATIONAL_LABELS = (
    (
        "weight_rep0_max_gap",
        "Largest gap between the replicate file's pwwgt0 and MARSUPWT / 100 "
        "(people)",
    ),
    (
        "units_with_varying_famtype",
        "SPM units whose members carry different SPM_FAMTYPE codes",
    ),
    (
        "persons_in_units_with_varying_famtype",
        "People in those units",
    ),
    (
        "persons_with_negative_published_element",
        "People with a negative amount in a published element's field",
    ),
    (
        "persons_with_negative_state_tax",
        "People with negative state income tax (SPM_STTAX)",
    ),
)


def round_floats(value, digits: int = 6):
    """Round every float in a nested structure, for stable JSON."""
    if isinstance(value, float):
        if not math.isfinite(value):
            return value
        rounded = round(value, digits)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, dict):
        return {k: round_floats(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [round_floats(v, digits) for v in value]
    return value


def extract_blocks(text: str) -> Dict[str, str]:
    """The body of every generated block in a note, by name."""
    return {m.group("name"): m.group("body") for m in BLOCK.finditer(text)}


def apply_blocks(text: str, blocks: Dict[str, str]) -> str:
    """Replace each generated block's body; every block must be present."""
    present = set(extract_blocks(text))
    missing = sorted(set(blocks) - present)
    unknown = sorted(present - set(blocks))
    if missing or unknown:
        raise ValueError(
            f"Generated blocks differ: missing {missing}, unknown {unknown}"
        )

    def replace(match: re.Match) -> str:
        body = blocks[match.group("name")]
        if not body.endswith("\n"):
            body += "\n"
        return match.group(1) + body + match.group(4)

    return BLOCK.sub(replace, text)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def _pp(value: float, decimals: int = 2) -> str:
    text = f"{value:.{decimals}f}"
    return (
        "0." + "0" * decimals
        if text.startswith("-0.") and float(text) == 0
        else text
    )


def _thousands(value: float) -> str:
    return f"{value:,.0f}"


def _table(header: List[str], rows: List[List[str]], align: str) -> str:
    """A Markdown table; ``align`` holds one of l/r per column."""
    marks = {"l": ":--", "r": "--:"}
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(marks[a] for a in align) + " |",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def _ours(row: dict, j: int) -> str:
    return f"{_pp(row['estimate'][j])} ± {_pp(row['moe'][j])}"


def _theirs(pub: Optional[dict], j: int) -> str:
    if not pub:
        return "not published"
    return f"{pub['estimate_text'][j]} ± {pub['moe_text'][j]}"


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


def _words(n: int) -> str:
    names = "zero one two three four five six seven eight nine".split()
    return names[n] if 0 <= n < len(names) else str(n)


def _count(n: int, total: int) -> str:
    return "all" if n == total else f"{n} of the"


def headline_block(results: dict) -> str:
    s = results["comparison"]
    rate = _row(results, "spm_rate")
    pub = rate["published_values"]
    effects = [
        r
        for r in results["table5"]["rows"]
        if r["key"] != "spm_rate" and r.get("published_values")
    ]
    exact_effects = sum(
        1 for r in effects for g in r["estimate_gap"] if g < 1e-9
    )
    largest_cells = s["table5_effect_max_gap_cells"]
    largest = "; ".join(
        f"{_row(results, c['element'])['label']}, {c['group'].lower()}"
        for c in largest_cells
    )
    n_largest = len(largest_cells)
    where = (
        f"in {_words(n_largest)} cell{'s' if n_largest != 1 else ''}: "
        f"{largest}"
    )
    within = s["table5_effects_within_published_moe"]
    n_effects = s["table5_effect_cells"]
    rate_gap = max(
        s["table5_spm_rate_max_gap"], s["table5_spm_rate_moe_max_gap"]
    )
    return (
        f"- **SPM rate.** We estimate that {_pp(rate['estimate'][0])} "
        f"percent of people lived in SPM poverty in "
        f"{results['reference_year']}, with a 90 percent margin of error "
        f"of {_pp(rate['moe'][0])} points. Census publishes "
        f"{pub['estimate_text'][0]} ± {pub['moe_text'][0]}. Across all "
        f"people and the three age groups, {s['table5_spm_rate_cells_exact']}"
        f" of the {s['table5_spm_rate_cells']} published rates and margins "
        "match to the published two decimals, and none differs by more "
        f"than {_pp(rate_gap)} points.\n"
        f"- **Element effects.** {exact_effects} of the {n_effects} "
        "published effects of single resource elements match to two "
        f"decimals. The largest gap is {_pp(s['table5_effect_max_gap'])} "
        f"points, {where}. For {_count(within, n_effects)} "
        f"{n_effects} effects, the gap is smaller than Census's published "
        "margin of error, and no margin of error differs by more than "
        f"{_pp(s['table5_effect_moe_max_gap'])} points.\n"
        + _characteristics(s)
    )


def _characteristics(s: dict) -> str:
    n4 = s["table4_rows_identifiable"]
    rates = s["table4_percent_within_moe"]
    numbers = s["table4_number_within_moe"]
    if rates == numbers == n4:
        within = (
            f"For all {n4} Table 4 rows that the public-use file can "
            "define, our poverty rate and number in poverty fall within "
            "Census's published margins of error"
        )
    else:
        within = (
            f"Of the {n4} Table 4 rows that the public-use file can "
            f"define, our poverty rate falls within Census's published "
            f"margin of error for {rates} and our number in poverty for "
            f"{numbers}"
        )
    return (
        f"- **Characteristics.** {within}, and {s['table4_percent_exact']} "
        "rates match to the published decimal. The four residence rows "
        "need geography that the public-use file withholds for some "
        "households.\n"
    )


def sample_block(results: dict) -> str:
    n = results["sample"]
    inputs = results.get("inputs", {})
    micro = inputs.get("microdata", {})
    rows = [
        ["People", f"{n['persons']:,}"],
        ["SPM units", f"{n['spm_units']:,}"],
        ["Households", f"{n['households']:,}"],
        ["Tax units", f"{n['tax_units']:,}"],
        [
            "Weighted people (thousands)",
            _thousands(results["population_thousands"]),
        ],
    ]
    out = _table(["Records", "Count"], rows, "lr")
    if micro:
        out += (
            f"\nInput: `{micro['file']}` ({micro['bytes']:,} bytes, "
            f"SHA-256 `{micro['sha256']}`).\n"
        )
    return out


def _check_value(value) -> str:
    if isinstance(value, float) and value != int(value):
        return f"{value:.4f}"
    return f"{int(value):,}"


def identities_block(results: dict) -> str:
    checks = results["identities"]
    rows = [
        [label, _check_value(checks[key])] for key, label in IDENTITY_LABELS
    ]
    out = _table(["Check (must be zero)", "Result"], rows, "lr")
    info = [
        [label, _check_value(checks[key])]
        for key, label in INFORMATIONAL_LABELS
    ]
    return out + "\n" + _table(["Check (informational)", "Result"], info, "lr")


def table5_block(results: dict) -> str:
    header = ["Element"]
    for group in GROUP_HEADERS:
        header += [f"{group}: ours", "Census"]
    rows = []
    for row in results["table5"]["rows"]:
        cells = [row["label"]]
        for j in range(len(GROUP_HEADERS)):
            cells += [_ours(row, j), _theirs(row["published_values"], j)]
        rows.append(cells)
    return _table(header, rows, "l" + "r" * (2 * len(GROUP_HEADERS)))


def elements_block(results: dict) -> str:
    rows = []
    for row in results["table5"]["rows"]:
        if row["key"] == "spm_rate":
            continue
        fields = [f"`{c}`" for c in row["unit_columns"]] + [
            f"`{c}` summed over the unit's members"
            for c in row["person_columns"]
        ]
        kind = "Addition" if row["kind"] == "addition" else "Subtraction"
        published = "yes" if row["published_values"] else "no"
        rows.append([row["label"], kind, " + ".join(fields), published])
    return _table(
        ["Element", "Kind", "Public-use fields", "In Table 5"], rows, "llll"
    )


def table4_block(results: dict) -> str:
    header = [
        "Characteristic",
        "Definition",
        "Percent: ours",
        "Census",
        "Within margin",
        "Number (thousands): ours",
        "Census",
    ]
    rows = []
    section = None
    for row in results["table4"]["rows"]:
        if row["section"] != section and row["section"]:
            rows.append([f"*{row['section']}*", "", "", "", "", "", ""])
        section = row["section"]
        pub = row["published_values"]
        if not row["identifiable"]:
            within = "not testable"
        elif row["percent_within_moe"] and row["number_within_moe"]:
            within = "yes"
        else:
            within = "**no**"
        rows.append(
            [
                row["label"],
                f"`{row['definition']}`",
                f"{row['percent']:.1f} ± {row['percent_moe']:.1f}",
                f"{pub['percent']:.1f} ± {pub['percent_moe']:.1f}",
                within,
                f"{_thousands(row['number_thousands'])} ± "
                f"{_thousands(row['number_moe'])}",
                f"{_thousands(pub['number_thousands'])} ± "
                f"{_thousands(pub['number_moe'])}",
            ]
        )
    return _table(header, rows, "llrrlrr")


def alternatives_block(results: dict) -> str:
    alt = results["alternatives"]
    rows = []
    for row in alt["table5"]["rows"]:
        main = _row(results, row["compares_with"])
        rows.append(
            [
                f"{main['label']} (Table 5, all people)",
                f"{_pp(main['estimate'][0])}",
                f"{row['label']}: {_pp(row['estimate'][0])}",
                _theirs(row["published_values"], 0),
            ]
        )
    by_label = {r["label"]: r for r in results["table4"]["rows"]}
    for row in alt["table4"]["rows"]:
        main = by_label[row["compares_with"]]
        pub = row["published_values"]
        rows.append(
            [
                f"{main['label']} (Table 4, percent)",
                f"{main['percent']:.1f}",
                f"{row['label']}: {row['percent']:.1f}",
                f"{pub['percent']:.1f} ± {pub['percent_moe']:.1f}",
            ]
        )
    return _table(
        ["Published row", "Our definition", "Alternative", "Census"],
        rows,
        "lrrr",
    )


def geography_block(results: dict) -> str:
    g = results["unidentified_geography"]
    rows = {r["label"]: r for r in results["table4"]["rows"]}
    inside = rows["Inside metropolitan statistical areas"]["published_values"]
    outside = rows["Outside metropolitan statistical areas"][
        "published_values"
    ]
    everyone = rows["All people"]["published_values"]
    return (
        "The public-use file leaves metropolitan status unidentified "
        f"(GTMETSTA = 3) for {g['metro_status_persons']:,} sample people, "
        f"{_thousands(g['metro_status_thousands'])} thousand weighted, and "
        "principal-city status unidentified (GTCBSAST = 4) for "
        f"{g['principal_city_persons']:,} sample people, "
        f"{_thousands(g['principal_city_thousands'])} thousand weighted. "
        "Census's table places everyone: its inside- and "
        "outside-metropolitan numbers in poverty, "
        f"{_thousands(inside['number_thousands'])} and "
        f"{_thousands(outside['number_thousands'])} thousand, sum to "
        f"{_thousands(inside['number_thousands'] + outside['number_thousands'])}"
        f" thousand, against {_thousands(everyone['number_thousands'])} "
        "thousand for all people.\n"
    )


def _series(values: List[str]) -> str:
    return ", ".join(values[:-1]) + " and " + values[-1]


def credit_interaction_block(results: dict) -> str:
    ci = results["credit_interaction"]
    shares = ci["fica_shares"]
    n12 = ci["units_with_credit"]["one_or_two_children"]
    n3 = ci["units_with_credit"]["three_or_more_children"]
    m12 = ci["rule_matches"]["one_or_two_children"]
    m3 = ci["rule_matches"]["three_or_more_children"]
    missed_with_eitc = ci["units_without_credit_not_reproduced_with_eitc"]
    eitc = _row(results, "eitc")
    ours = eitc["estimate"]
    response = ci["eitc_with_ctc_response"]["estimate"]
    census = _series(list(eitc["published_values"]["estimate_text"]))
    changed = ci["persons_whose_status_changes"]
    above = ci["three_plus_above_earnings_branch"]
    if above == 0:
        payroll_sets = (
            "No unit with three or more qualifying children has an "
            "`ACTC_CRD` above 15 percent of its earnings over $2,500, the "
            "most the earnings branch allows, so the payroll tax "
            "alternative sets no credit in the file. "
        )
    else:
        payroll_sets = (
            f"{above:,} of the {n3:,} units with three or more qualifying "
            "children have an `ACTC_CRD` above 15 percent of their earnings "
            "over $2,500, the most the earnings branch allows. "
        )
    missed = "none" if missed_with_eitc == 0 else _words(missed_with_eitc)
    text = (
        f"The file's `FICA` equals {100 * shares['wages']:.2f} percent of "
        "wages for filers with wages alone and "
        f"{100 * shares['self_employment']:.2f} percent of self-employment "
        "income for filers with self-employment income alone, so it "
        "carries the whole self-employment tax; we count half of that tax, "
        "as the rule does. With that payroll tax, the rule gives "
        f"{_count(m12 + m3, n12 + n3)} {n12 + n3:,} tax units with a "
        "refundable credit their `ACTC_CRD` within a dollar: "
        f"{m12:,} of {n12:,} with one or two qualifying children and "
        f"{m3:,} of {n3:,} with three or more. It misses "
        f"{ci['units_without_credit_not_reproduced']:,} tax units that the "
        f"file gives no refundable credit, {missed} of them with an EITC. "
        f"{payroll_sets}Without the EITC, the rule would raise the credit "
        f"of {ci['units_raised']:,} tax units, by at most "
        f"${ci['largest_rise_dollars']:,.0f}, in SPM units with "
        f"{_thousands(ci['persons_in_raised_units_thousands'])} thousand "
        "people. "
    )
    if changed == 0 and all(abs(a - b) < 1e-9 for a, b in zip(response, ours)):
        text += (
            "That changes no one's poverty status, so our EITC effect "
            f"stays at {_series([_pp(x) for x in ours])} points for all "
            "people, under 18, 18 to 64 and 65 and older, against "
            f"Census's {census}.\n"
        )
    else:
        text += (
            f"That changes the poverty status of {changed:,} sample people "
            f"and moves our EITC effect from {_series([_pp(x) for x in ours])}"
            f" to {_series([_pp(x) for x in response])} points for all "
            "people, under 18, 18 to 64 and 65 and older, against "
            f"Census's {census}.\n"
        )
    return text


def largest_gaps_block(results: dict) -> str:
    groups = results["table5"]["groups"]
    cells = []
    for row in results["table5"]["rows"]:
        pub = row.get("published_values")
        if row["key"] == "spm_rate" or not pub:
            continue
        for j, gap in enumerate(row["estimate_gap"]):
            if gap is not None and gap >= EFFECT_GAP_SHOWN - 1e-9:
                cells.append((gap, row, j))
    cells.sort(key=lambda c: (-c[0], c[1]["label"], c[2]))
    t5 = _table(
        ["Element", "Group", "Ours", "Census", "Gap"],
        [
            [
                row["label"],
                groups[j],
                _pp(row["estimate"][j]),
                row["published_values"]["estimate_text"][j],
                _pp(gap),
            ]
            for gap, row, j in cells
        ],
        "llrrr",
    )
    t4_rows = [
        r
        for r in results["table4"]["rows"]
        if r["identifiable"] and r["percent_gap"] >= PERCENT_GAP_SHOWN - 1e-9
    ]
    t4_rows.sort(key=lambda r: (-r["percent_gap"], r["label"]))
    t4 = _table(
        ["Characteristic", "Ours", "Census", "Gap", "Census margin"],
        [
            [
                r["label"],
                f"{r['percent']:.1f}",
                f"{r['published_values']['percent']:.1f}",
                f"{r['percent_gap']:.1f}",
                f"{r['published_values']['percent_moe']:.1f}",
            ]
            for r in t4_rows
        ],
        "lrrrr",
    )
    return (
        f"Table 5 effects that differ from Census's by "
        f"{_pp(EFFECT_GAP_SHOWN)} points or more:\n\n{t5}\n"
        f"Identifiable Table 4 rows whose percentage differs from Census's "
        f"by {PERCENT_GAP_SHOWN:.1f} points or more:\n\n{t4}"
    )


def tolerances_block(results: dict) -> str:
    s = results["comparison"]
    t = results["tolerances"]
    rows = [
        [
            "Table 5 SPM rate, each age group",
            f"{_pp(t['table5_spm_rate'])} points",
            f"{_pp(s['table5_spm_rate_max_gap'])}",
        ],
        [
            "Table 5 SPM rate margin of error",
            f"{_pp(t['table5_spm_rate_moe'])} points",
            f"{_pp(s['table5_spm_rate_moe_max_gap'])}",
        ],
        [
            "Table 5 element effect",
            f"{_pp(t['table5_effect'])} points",
            f"{_pp(s['table5_effect_max_gap'])}",
        ],
        [
            "Table 5 element effect margin of error",
            f"{_pp(t['table5_effect_moe'])} points",
            f"{_pp(s['table5_effect_moe_max_gap'])}",
        ],
        [
            "Table 4 percent, identifiable rows",
            "within the published margin",
            f"{s['table4_percent_within_moe']} of "
            f"{s['table4_rows_identifiable']} rows",
        ],
        [
            "Table 4 number, identifiable rows",
            "within the published margin",
            f"{s['table4_number_within_moe']} of "
            f"{s['table4_rows_identifiable']} rows",
        ],
        [
            "Table 4 percent margin of error",
            f"{t['table4_percent_moe']:.1f} points",
            f"{s['table4_percent_moe_max_gap']:.1f}",
        ],
        [
            "Table 4 number margin of error",
            f"{100 * t['table4_number_moe_relative']:.0f} percent",
            f"{100 * s['table4_number_moe_relative_max_gap']:.1f} percent",
        ],
    ]
    return _table(["Comparison", "Tolerance", "Largest gap"], rows, "lrr")


def _row(results: dict, key: str) -> dict:
    for row in results["table5"]["rows"]:
        if row["key"] == key:
            return row
    raise KeyError(key)


def render_blocks(results: dict) -> Dict[str, str]:
    """Every generated block of the step 1 note, by name."""
    return {
        "headline": headline_block(results),
        "sample": sample_block(results),
        "identities": identities_block(results),
        "elements": elements_block(results),
        "table5": table5_block(results),
        "table4": table4_block(results),
        "geography": geography_block(results),
        "largest_gaps": largest_gaps_block(results),
        "alternatives": alternatives_block(results),
        "credit_interaction": credit_interaction_block(results),
        "tolerances": tolerances_block(results),
    }
