# Equivalence scale

`spm_equivalence_scale(num_adults, num_children, normalize=True)` calculates
the Betson three-parameter scale from already classified SPM counts. With
normalization, the two-adult/two-child reference family has factor 1.

These are measurement counts, not simply everyone above/below age 18.
Person-based integrations classify age ≥18 as adult, or age ≥15 with an explicit
SPM independent-minor role, within the source unit membership. The scalar
`SPMUnit` contract validates at least one adult and nonnegative integer children.
Use it for household calculations; the low-level scale helper does not replace
input validation or reconstruct roles.

```python
from spm_calculator import spm_equivalence_scale

for adults, children in ((1, 0), (2, 0), (1, 2), (2, 2), (3, 4)):
    print(adults, children, round(spm_equivalence_scale(adults, children), 3))
assert spm_equivalence_scale(2, 2) == 1.0
print(spm_equivalence_scale(2, 2, normalize=False))  # 2.157669279974593
```

The raw scale is `(1.8 + 0.5 × (children − 1))^0.7` for one adult with
children, and `(adults + 0.5 × children)^0.7` for multiple adults with children.
Childless units use 1 for one adult, 1.41 for two adults, and `adults^0.7` for
three or more adults. Normalization divides by `3^0.7`.
See the [methodology and source references](../methodology.md).

## Arrays and total-person inputs

NumPy arrays support elementwise scale calculations:

```python
import numpy as np
from spm_calculator import spm_equivalence_scale
from spm_calculator.equivalence_scale import equivalence_scale_from_persons

scales = spm_equivalence_scale(np.array([1, 2, 2, 3]), np.array([0, 0, 2, 4]))
print(np.round(scales, 3))  # [0.463 0.653 1.    1.43 ]
assert equivalence_scale_from_persons(4, 2) == 1.0
```

`equivalence_scale_from_persons(num_persons, num_children, normalize=True)`
subtracts the already classified child count from total persons; it does not
classify children from their ages. These array helpers do not aggregate
population weights. Use native Frame operations for population accounting.

The [Axiom bridge](../axiom-integration.md) exports canonical factors over a
declared finite domain because that runtime lacks fractional power. Native
classification and counts select the exported factor; unsupported counts fail.
