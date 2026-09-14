# SPM unit IDs

Helpers for reconstructing SPM resource-unit membership from person records.

## spm_unit_id

```python
import pandas as pd
from spm_calculator import spm_unit_id

# Synthetic source data: one household contains two native SPM units.
persons = pd.DataFrame({
    "person_id": [1, 2, 3],
    "household_id": [1, 1, 1],
    "age": [40, 8, 30],
    "SPM_ID": [10, 10, 20],
})
ids, diagnostics = spm_unit_id(persons, diagnostics=True)
assert ids.tolist() == [10, 10, 20]
assert diagnostics["method"] == "native_spm_id"
print(diagnostics)
```

`spm_unit_id` returns a person-level `pandas.Series` aligned to `persons`.
If native IDs are present, it preserves `person_spm_unit_id`, `spm_unit_id`, or
`SPM_ID` exactly. Otherwise, it infers unit membership within each household.

### Inputs

Reconstruction requires a household ID; native-ID preservation does not.
More source inputs improve reconstruction fidelity. The Frame and country
adapters consume native membership and do not invoke this reconstruction helper
or infer primitive independence roles from its output.

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

The helper resolves parent pointers within each household before applying the
unrelated-child fallback. A child under 15 with a resolved parent pointer joins
that parent's unit. When no pointer resolves, the helper assumes that an
unrelated child under 15 belongs in the household reference unit and records
`attach_unrelated_under_15_to_reference_unit` in its fallback diagnostics.
Missing pointers, pointers to another household and self-pointers do not
establish a parent link. This fallback does not establish that a resident parent
is absent.

The generic relationship label `foster child` uses the foster attachment rule,
which joins children under 22 to the household reference unit. That label alone
does not attach someone aged 22 or older. Existing family membership and other
explicit links still apply.

These rules follow [Census working paper 2011-22, printed page 7](https://www.census.gov/content/dam/Census/library/working-papers/2011/demo/SEHSD-WP2011-22.pdf#page=8).
Source records must retain the parent links needed to distinguish unrelated
subfamilies. Reconstruction cannot recover a missing relationship from age alone.
Source adapters must resolve or quarantine ambiguous parent candidates before
calling the helper. Duplicate household/person pointer keys are not validated;
the helper's lookup retains the last matching row. Generic relationship
normalization does not implement an ACS `RELSHIPP` recode. Native IDs, explicit
family grouping and Census assignment flags retain their existing precedence.

### Diagnostics

With `diagnostics=True`, the function returns `(ids, diagnostics)`. The
`diagnostics` dictionary has these fields:

| Field | Type / allowed interpretation |
| --- | --- |
| `method` | `native_spm_id`, `census_relationship_rules` or `fallback_household_rules`. |
| `native_id_column` | Source column name, or `None` for reconstructed IDs. |
| `used_columns` | List of source column names. |
| `missing_recommended_columns` | List of missing source-field names. |
| `fallback_rules_used` | List of reconstruction rules used. |
| `confidence` | `native`, `rule_based` or `approximate`. |

Diagnostics describe assignment provenance only. They intentionally do not
report unit counts, sizes, child-only units, or other unit profile summaries.

### Unsupported cases

When the input lacks a direct partner pointer, multiple unrelated cohabiting
SPM units in the same household can be ambiguous. `SPM_WCOHABIT` identifies
people in cohabiting SPM units but does not distinguish multiple cohabiting
units inside the same household. Exact reconstruction of those cases requires
`PECOHAB` or an equivalent partner pointer.

## spm_unit_id_match

```python
import pandas as pd
from spm_calculator import spm_unit_id_match

persons = pd.DataFrame({"household_id": [1, 1, 1], "SPM_ID": [10, 10, 20]})
# The labels differ but the within-household partition is the same.
report = spm_unit_id_match(
    persons, reference_spm_unit_id="SPM_ID", predicted_spm_unit_id=[1, 1, 2]
)
assert report["match"] is True
```

`spm_unit_id_match` compares assignments within household up to arbitrary
relabeling of unit IDs. If `predicted_spm_unit_id` is omitted, it infers IDs
with `spm_unit_id` while disabling native-ID preservation.

The optional ASEC parity test runs when `SPM_CALCULATOR_ASEC_H5` points to a
Census CPS ASEC HDFStore. The previously recorded source-parity run used the full raw 2025 CPS ASEC person columns for
the 2024 data year, including `PECOHAB`; the default reconstruction matched
all 55,762 household partitions.


## Threshold comparison

```python
from spm_calculator import get_published_thresholds, spm_threshold_match

published = get_published_thresholds(2025)["renter"]
report = spm_threshold_match([published], [41_701], rtol=0, atol=0.5)
assert report["match"] is True
```

This example compares a full-precision value with its rounded source display.
A tolerance check does not establish source identity or forecast accuracy.
