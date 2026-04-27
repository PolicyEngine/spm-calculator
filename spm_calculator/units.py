"""SPM resource-unit membership helpers."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def spm_unit_id(
    persons: pd.DataFrame,
    *,
    household_id: str | None = "household_id",
    person_id: str | None = "person_id",
    line_number: str | None = "line_number",
    age: str | None = "age",
    family_id: str | None = "family_id",
    relationship_to_head: str | None = "relationship_to_head",
    unmarried_partner_id: str | None = "unmarried_partner_id",
    spouse_id: str | None = "spouse_id",
    parent_id: str | None = "parent_id",
    mother_id: str | None = "mother_id",
    father_id: str | None = "father_id",
    foster_child: str | None = "is_foster_child",
    spm_cohabiting_unit: str | None = "spm_cohabiting_unit",
    spm_foster_child_unit: str | None = "spm_foster_child_unit",
    spm_unrelated_child_unit: str | None = "spm_unrelated_child_unit",
    spm_new_parent_unit: str | None = "spm_new_parent_unit",
    native_person_spm_unit_id: str | None = "person_spm_unit_id",
    native_spm_unit_id: str | None = "spm_unit_id",
    diagnostics: bool = False,
) -> pd.Series | tuple[pd.Series, dict[str, Any]]:
    """Return person-level SPM resource-unit IDs.

    If the input already includes native SPM IDs, those IDs are preserved.
    Otherwise, this applies a best-effort implementation of Census-style SPM
    resource-unit membership: family members share a unit, cohabiting partners
    share a unit when partner links are present, foster children under 22 and
    unrelated children under 15 are attached to the household reference unit,
    and other people remain in separate units.

    The function returns a Series aligned to ``persons`` and does not mutate the
    input DataFrame.
    """
    native_column = _resolve_column(
        persons,
        native_person_spm_unit_id,
        ("person_spm_unit_id", "SPM_ID"),
    )
    if native_column is None:
        native_column = _resolve_column(
            persons,
            native_spm_unit_id,
            ("spm_unit_id",),
        )

    if native_column is not None:
        ids = persons[native_column].copy()
        ids.name = "spm_unit_id"
        info = {
            "method": "native_spm_id",
            "native_id_column": native_column,
            "used_columns": [native_column],
            "missing_recommended_columns": [],
            "fallback_rules_used": [],
            "confidence": "native",
        }
        return (ids, info) if diagnostics else ids

    ids, info = _infer_spm_unit_id(
        persons,
        household_id=household_id,
        person_id=person_id,
        line_number=line_number,
        age=age,
        family_id=family_id,
        relationship_to_head=relationship_to_head,
        unmarried_partner_id=unmarried_partner_id,
        spouse_id=spouse_id,
        parent_id=parent_id,
        mother_id=mother_id,
        father_id=father_id,
        foster_child=foster_child,
        spm_cohabiting_unit=spm_cohabiting_unit,
        spm_foster_child_unit=spm_foster_child_unit,
        spm_unrelated_child_unit=spm_unrelated_child_unit,
        spm_new_parent_unit=spm_new_parent_unit,
    )
    return (ids, info) if diagnostics else ids


def _infer_spm_unit_id(
    persons: pd.DataFrame,
    *,
    household_id: str | None,
    person_id: str | None,
    line_number: str | None,
    age: str | None,
    family_id: str | None,
    relationship_to_head: str | None,
    unmarried_partner_id: str | None,
    spouse_id: str | None,
    parent_id: str | None,
    mother_id: str | None,
    father_id: str | None,
    foster_child: str | None,
    spm_cohabiting_unit: str | None,
    spm_foster_child_unit: str | None,
    spm_unrelated_child_unit: str | None,
    spm_new_parent_unit: str | None,
) -> tuple[pd.Series, dict[str, Any]]:
    household_column = _resolve_column(
        persons,
        household_id,
        ("household_id", "person_household_id", "H_SEQ", "PH_SEQ"),
        required=True,
    )
    person_column = _resolve_column(
        persons,
        person_id,
        ("person_id", "P_ID", "P_SEQ", "PERIDNUM"),
    )
    line_column = _resolve_column(
        persons,
        line_number,
        ("line_number", "person_line_number", "A_LINENO"),
    )
    age_column = _resolve_column(persons, age, ("age", "A_AGE"))
    family_column = _resolve_column(
        persons,
        family_id,
        ("family_id", "person_family_id", "PF_SEQ"),
    )
    relationship_column = _resolve_column(
        persons,
        relationship_to_head,
        ("relationship_to_head", "family_relationship", "A_FAMREL"),
    )
    partner_column = _resolve_column(
        persons,
        unmarried_partner_id,
        (
            "unmarried_partner_id",
            "partner_id",
            "cohabiting_partner_id",
            "PECOHAB",
        ),
    )
    spouse_column = _resolve_column(
        persons,
        spouse_id,
        ("spouse_id", "spouse_person_id", "A_SPOUSE"),
    )
    foster_column = _resolve_column(
        persons,
        foster_child,
        ("is_foster_child", "foster_child"),
    )
    parent_columns = [
        column
        for column in (
            _resolve_column(persons, parent_id, ("parent_id",)),
            _resolve_column(
                persons,
                mother_id,
                ("mother_id", "first_parent_id", "PEPAR1"),
            ),
            _resolve_column(
                persons,
                father_id,
                ("father_id", "second_parent_id", "PEPAR2"),
            ),
        )
        if column is not None
    ]
    parent_columns = list(dict.fromkeys(parent_columns))
    cohabiting_unit_column = _resolve_column(
        persons,
        spm_cohabiting_unit,
        ("spm_cohabiting_unit", "SPM_WCOHABIT"),
    )
    foster_child_unit_column = _resolve_column(
        persons,
        spm_foster_child_unit,
        ("spm_foster_child_unit", "SPM_WFOSTER22"),
    )
    unrelated_child_unit_column = _resolve_column(
        persons,
        spm_unrelated_child_unit,
        ("spm_unrelated_child_unit", "SPM_WUI_LT15"),
    )
    new_parent_unit_column = _resolve_column(
        persons,
        spm_new_parent_unit,
        ("spm_new_parent_unit", "SPM_WNEWPARENT"),
    )
    spm_unit_flag_columns = {
        "merge_census_foster_under_22_flags": foster_child_unit_column,
        "merge_census_unrelated_under_15_flags": unrelated_child_unit_column,
        "merge_census_new_parent_flags": new_parent_unit_column,
    }
    if cohabiting_unit_column is not None and partner_column is None:
        spm_unit_flag_columns["merge_census_cohabiting_unit_flags"] = (
            cohabiting_unit_column
        )
    spm_unit_flag_columns = {
        rule: column
        for rule, column in spm_unit_flag_columns.items()
        if column is not None
    }
    has_linkage_columns = (
        parent_columns
        or partner_column is not None
        or spouse_column is not None
        or foster_column is not None
        or spm_unit_flag_columns
    )
    pointer_column = line_column or person_column
    pointer_work_column = (
        "_line_number"
        if pointer_column is not None and pointer_column == line_column
        else "_person"
    )

    n = len(persons)
    parents = list(range(n))

    def find(position: int) -> int:
        while parents[position] != position:
            parents[position] = parents[parents[position]]
            position = parents[position]
        return position

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    work = pd.DataFrame(
        {
            "_position": np.arange(n, dtype=int),
            "_household": persons[household_column].to_numpy(),
        },
        index=persons.index,
    )
    if person_column is not None:
        work["_person"] = persons[person_column].to_numpy()
    if line_column is not None:
        work["_line_number"] = persons[line_column].to_numpy()
    if age_column is not None:
        work["_age"] = pd.to_numeric(
            persons[age_column],
            errors="coerce",
        )
    if family_column is not None:
        work["_family"] = persons[family_column].to_numpy()
    if relationship_column is not None:
        work["_relationship"] = _normalize_relationship(
            persons[relationship_column]
        )
    if foster_column is not None:
        work["_foster_child"] = _coerce_bool(persons[foster_column])
    for rule_name, column in spm_unit_flag_columns.items():
        work[f"_{rule_name}"] = _coerce_bool(persons[column])

    fallback_rules_used: set[str] = set()

    for _, household_rows in work.groupby("_household", sort=False):
        positions = household_rows["_position"].to_numpy(dtype=int)
        if len(positions) == 0:
            continue

        primary_anchor: int | None = None

        if "_family" in household_rows:
            family_rows = household_rows[household_rows["_family"].notna()]
            for _, group in family_rows.groupby("_family", sort=False):
                group_positions = group["_position"].to_numpy(dtype=int)
                _union_all(group_positions, union)

            if "_relationship" in household_rows:
                head_rows = household_rows[
                    household_rows["_relationship"].eq("head")
                ]
                if not head_rows.empty:
                    primary_anchor = find(int(head_rows["_position"].iloc[0]))
            if primary_anchor is None:
                primary_anchor = find(int(positions[0]))
        elif "_relationship" in household_rows:
            primary_rows = household_rows[
                household_rows["_relationship"].isin(
                    {"head", "spouse", "child"}
                )
            ]
            primary_positions = primary_rows["_position"].to_numpy(dtype=int)
            _union_all(primary_positions, union)
            if len(primary_positions) > 0:
                primary_anchor = find(int(primary_positions[0]))
        else:
            if not has_linkage_columns:
                _union_all(positions, union)
                fallback_rules_used.add("household_level_fallback")
            primary_anchor = find(int(positions[0]))

        if primary_anchor is None:
            continue

        if (
            "_relationship" in household_rows
            and "_age" in household_rows
            and unrelated_child_unit_column is None
        ):
            unrelated_children = household_rows[
                household_rows["_relationship"].eq("other")
                & household_rows["_age"].lt(15)
            ]["_position"].to_numpy(dtype=int)
            if len(unrelated_children) > 0:
                fallback_rules_used.add(
                    "attach_unrelated_under_15_to_reference_unit"
                )
            for position in unrelated_children:
                union(primary_anchor, int(position))

        if (
            "_foster_child" in household_rows
            and "_age" in household_rows
            and foster_child_unit_column is None
        ):
            foster_children = household_rows[
                household_rows["_foster_child"] & household_rows["_age"].lt(22)
            ]["_position"].to_numpy(dtype=int)
            if len(foster_children) > 0:
                fallback_rules_used.add(
                    "attach_foster_under_22_to_reference_unit"
                )
            for position in foster_children:
                union(primary_anchor, int(position))

    for rule_name in spm_unit_flag_columns:
        flag_column = f"_{rule_name}"
        flagged_rows = work[work[flag_column]]
        for _, group in flagged_rows.groupby("_household", sort=False):
            positions = group["_position"].to_numpy(dtype=int)
            if len(positions) < 2:
                continue
            _union_all(positions, union)
            fallback_rules_used.add(rule_name)

    if pointer_column is not None and partner_column is not None:
        person_lookup = {
            (row["_household"], row[pointer_work_column]): int(
                row["_position"]
            )
            for _, row in work.iterrows()
        }
        for row_position, partner_value in enumerate(persons[partner_column]):
            if pd.isna(partner_value):
                continue
            household_value = work["_household"].iloc[row_position]
            partner_position = person_lookup.get(
                (household_value, partner_value)
            )
            if partner_position is None:
                continue
            union(row_position, partner_position)
            fallback_rules_used.add("link_unmarried_partners")

    if pointer_column is not None and spouse_column is not None:
        person_lookup = {
            (row["_household"], row[pointer_work_column]): int(
                row["_position"]
            )
            for _, row in work.iterrows()
        }
        for row_position, spouse_value in enumerate(persons[spouse_column]):
            if pd.isna(spouse_value):
                continue
            household_value = work["_household"].iloc[row_position]
            spouse_position = person_lookup.get(
                (household_value, spouse_value)
            )
            if spouse_position is None:
                continue
            union(row_position, spouse_position)
            fallback_rules_used.add("link_spouses")

    if pointer_column is not None and parent_columns:
        person_lookup = {
            (row["_household"], row[pointer_work_column]): int(
                row["_position"]
            )
            for _, row in work.iterrows()
        }
        for parent_column_name in parent_columns:
            for row_position, parent_value in enumerate(
                persons[parent_column_name]
            ):
                if pd.isna(parent_value):
                    continue
                household_value = work["_household"].iloc[row_position]
                parent_position = person_lookup.get(
                    (household_value, parent_value)
                )
                if parent_position is None:
                    continue
                union(row_position, parent_position)
                fallback_rules_used.add("link_parent_child")

    root_to_id: dict[int, int] = {}
    values: list[int] = []
    for position in range(n):
        root = find(position)
        if root not in root_to_id:
            root_to_id[root] = len(root_to_id)
        values.append(root_to_id[root])

    used_columns = [
        column
        for column in (
            household_column,
            person_column,
            line_column,
            age_column,
            family_column,
            relationship_column,
            partner_column,
            spouse_column,
            foster_column,
            *parent_columns,
            *spm_unit_flag_columns.values(),
        )
        if column is not None
    ]
    used_columns = list(dict.fromkeys(used_columns))
    missing_recommended = [
        name
        for name, column in {
            "age": age_column,
            "family_id": family_column,
            "relationship_to_head": relationship_column,
            "unmarried_partner_id": partner_column,
            "spouse_id": spouse_column,
            "line_number": line_column,
            "parent_id": parent_columns or None,
            "foster_child": foster_column,
            "spm_cohabiting_unit": spm_unit_flag_columns.get(
                "merge_census_cohabiting_unit_flags"
            )
            or partner_column,
            "spm_foster_child_unit": spm_unit_flag_columns.get(
                "merge_census_foster_under_22_flags"
            ),
            "spm_unrelated_child_unit": spm_unit_flag_columns.get(
                "merge_census_unrelated_under_15_flags"
            ),
            "spm_new_parent_unit": spm_unit_flag_columns.get(
                "merge_census_new_parent_flags"
            ),
        }.items()
        if column is None
    ]

    method = (
        "census_relationship_rules"
        if (
            family_column is not None
            or relationship_column is not None
            or parent_columns
            or partner_column is not None
            or spouse_column is not None
            or spm_unit_flag_columns
        )
        else "fallback_household_rules"
    )
    confidence = (
        "rule_based"
        if method == "census_relationship_rules"
        else "approximate"
    )
    info = {
        "method": method,
        "native_id_column": None,
        "used_columns": used_columns,
        "missing_recommended_columns": missing_recommended,
        "fallback_rules_used": sorted(fallback_rules_used),
        "confidence": confidence,
    }
    return pd.Series(values, index=persons.index, name="spm_unit_id"), info


def _resolve_column(
    frame: pd.DataFrame,
    requested: str | None,
    candidates: tuple[str, ...],
    *,
    required: bool = False,
) -> str | None:
    if requested is None:
        if required:
            raise KeyError(f"Missing required column; tried {candidates}")
        return None
    if requested in frame.columns:
        return requested
    if requested not in candidates:
        raise KeyError(f"Column '{requested}' is not present")
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    if required:
        tried = ", ".join(dict.fromkeys((requested, *candidates)))
        raise KeyError(f"Missing required column; tried {tried}")
    return None


def _normalize_relationship(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    unique_numeric = set(numeric.dropna().astype(int).unique().tolist())
    if unique_numeric and unique_numeric.issubset({0, 1, 2, 3, 4}):
        if 4 in unique_numeric:
            mapped = numeric.map({1: "head", 2: "spouse", 3: "child"})
        elif 0 in unique_numeric:
            mapped = numeric.map({0: "head", 1: "spouse", 2: "child"})
        else:
            mapped = numeric.map({1: "head", 2: "spouse", 3: "child"})
        return mapped.fillna("other")

    normalized = values.astype(str).str.strip().str.lower()
    result = pd.Series("other", index=values.index, dtype=object)
    result.loc[
        normalized.isin(
            {
                "head",
                "householder",
                "reference person",
                "self",
            }
        )
    ] = "head"
    result.loc[
        normalized.isin(
            {
                "spouse",
                "wife",
                "husband",
                "partner",
                "unmarried partner",
            }
        )
    ] = "spouse"
    result.loc[
        normalized.isin(
            {
                "child",
                "own child",
                "son",
                "daughter",
                "stepchild",
                "foster child",
            }
        )
    ] = "child"
    return result


def _coerce_bool(values: pd.Series) -> pd.Series:
    if values.dtype == bool:
        return values.fillna(False)
    numeric = pd.to_numeric(values, errors="coerce")
    normalized = values.astype(str).str.strip().str.lower()
    return numeric.eq(1) | normalized.isin({"true", "t", "yes", "y"})


def _union_all(values: np.ndarray, union: Any) -> None:
    if len(values) == 0:
        return
    first = int(values[0])
    for value in values[1:]:
        union(first, int(value))
