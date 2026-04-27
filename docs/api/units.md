# SPM Unit IDs

Helpers for reconstructing SPM resource-unit membership from person records.

## spm_unit_id

```python
from spm_calculator import spm_unit_id

ids = spm_unit_id(persons)
ids, diagnostics = spm_unit_id(persons, diagnostics=True)
```

`spm_unit_id` returns a person-level `pandas.Series` aligned to `persons`.
If native IDs are present, it preserves `person_spm_unit_id`, `spm_unit_id`, or
`SPM_ID` exactly. Otherwise, it infers unit membership within each household.

### Inputs

Only a household ID is required. More inputs improve fidelity.

| Input class | Columns recognized by default |
|-------------|-------------------------------|
| Required | `household_id`, `person_household_id`, `H_SEQ`, or `PH_SEQ` |
| Family grouping | `family_id`, `person_family_id`, or `PF_SEQ` |
| Age | `age` or `A_AGE` |
| Person line number | `line_number`, `person_line_number`, or `A_LINENO` |
| Parent pointers | `parent_id`, `mother_id`, `father_id`, `PEPAR1`, or `PEPAR2` |
| Partner and spouse pointers | `unmarried_partner_id`, `partner_id`, `cohabiting_partner_id`, `PECOHAB`, `spouse_id`, or `A_SPOUSE` |
| Census SPM assignment flags | `SPM_WFOSTER22`, `SPM_WUI_LT15`, and `SPM_WNEWPARENT`; `SPM_WCOHABIT` is used only when no direct cohabiting partner pointer such as `PECOHAB` is available |
| Generic relationship fields | `relationship_to_head`, `family_relationship`, `A_FAMREL`, `is_foster_child`, or `foster_child` |

Pointer columns are matched to `line_number` when it is present; otherwise they
are matched to `person_id`.

### Diagnostics

With `diagnostics=True`, the function returns:

```python
{
    "method": "native_spm_id" | "census_relationship_rules" | "fallback_household_rules",
    "native_id_column": "SPM_ID" | None,
    "used_columns": [...],
    "missing_recommended_columns": [...],
    "fallback_rules_used": [...],
    "confidence": "native" | "rule_based" | "approximate",
}
```

Diagnostics describe assignment provenance only. They intentionally do not
report unit counts, sizes, child-only units, or other unit profile summaries.

### Unsupported Cases

When the input lacks a direct partner pointer, multiple unrelated cohabiting
SPM units in the same household can be ambiguous. `SPM_WCOHABIT` identifies
people in cohabiting SPM units but does not distinguish multiple cohabiting
units inside the same household. Exact reconstruction of those cases requires
`PECOHAB` or an equivalent partner pointer.

## spm_unit_id_match

```python
from spm_calculator import spm_unit_id_match

report = spm_unit_id_match(persons, reference_spm_unit_id="SPM_ID")
```

`spm_unit_id_match` compares assignments within household up to arbitrary
relabeling of unit IDs. If `predicted_spm_unit_id` is omitted, it infers IDs
with `spm_unit_id` while disabling native-ID preservation.

The optional ASEC parity test runs when `SPM_CALCULATOR_ASEC_H5` points to a
Census CPS ASEC HDFStore. With the full raw 2025 CPS ASEC person columns for
the 2024 data year, including `PECOHAB`, the default reconstruction matched
all 55,762 household partitions.
