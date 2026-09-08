# Microcosm integration

`spm_calculator.microcosm_adapter` optionally applies an explicit SPM release
to an actual `microcosm.frame.Frame`. The lightweight release reader does not
import Microcosm or require a population download. The adapter requires only
the frame/graph kernel and their dependencies, not the country-build,
calibration, fit or PolicyEngine stacks.

```python
from spm_calculator.microcosm_adapter import (
    apply_release_to_frame,
    summarize_spm_units,
)

result = apply_release_to_frame(
    frame,
    release,
    year=2025,
    unit_entity="spm_unit",
    weight_entity="household",
    membership_provenance="Native SPM-unit identifiers from the selected dataset release",
    columns={
        "num_adults": "spm_num_adults",
        "num_children": "spm_num_children",
        "tenure": "spm_tenure",
        "resources": "spm_resources",
    },
)
summary = summarize_spm_units(
    result, unit_entity="spm_unit", weight_entity="household"
)
```

The schema must already declare the SPM-unit group and its person membership
column. Counts must use the caller's SPM classification and sum to the linked
membership. The adapter never reconstructs units or classifies children from
age alone. An explicit provenance description is required. Microcosm
revalidates the entire source Frame before the adapter reads it.

Threshold results are added to the SPM-unit table in a new Frame. Original
tables, person links, weights, strata and mass-change history are preserved.
Release and input provenance lives in immutable Frame metadata. Geography
defaults explicitly to national; columns can instead name `geography_kind`,
`geography_id`, or a caller-supplied whole-threshold `geographic_adjustment`.
Unknown requested areas fail. Estimated years require explicit opt-in.

The caller names the expected weight source. The adapter checks it against
Microcosm's effective-weight resolution, including inheritance from household
weights through person membership. Ambiguous sources or unequal weights among
members of an unweighted unit fail rather than being averaged. Microcosm's
`wmean` and `wsum` perform all aggregate arithmetic using the owning entity's
weights. The summary reports **SPM-unit poverty**, with units in its
denominator; it is not a person-level Census poverty rate. Missing resources
produce no poverty aggregate.

Reweighting the same population changes weighted summaries but never changes
individual thresholds. CE consumer units, interview weights and the BLS
threshold estimator remain a separate statistical pipeline. This adapter does
not reinterpret CE consumer units as SPM units, substitute calibrated weights
for CE weights, or claim that Microcosm's generic inverse-CDF quantile matches
the BLS estimation convention.

Acceptance uses the actual frame/graph packages from Microcosm commit
`923cec2e174c93ef0032de3415fbec87f716eea4`. To use that development checkout,
install its two local packages explicitly into a Python 3.13+ environment:

```sh
uv pip install /path/to/microcosm/packages/microcosm-graph \
  /path/to/microcosm/packages/microcosm-frame
python -m pytest tests/test_microcosm_adapter.py
```

These tests use synthetic linked records, exercise actual Frame construction
and accounting, and distinguish person counts from unit counts. They establish
software interoperability, not certification of a population release.
