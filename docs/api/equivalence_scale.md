# Equivalence Scale

Functions for calculating the SPM three-parameter equivalence scale.

## Functions

### spm_equivalence_scale

```python
from spm_calculator import spm_equivalence_scale

spm_equivalence_scale(
    num_adults: Union[int, np.ndarray],
    num_children: Union[int, np.ndarray],
    normalize: bool = True
) -> Union[float, np.ndarray]
```

Calculate SPM equivalence scale for a given family composition.

**Official Betson three-parameter scale:**
- Single adult with children: `(1 + 0.8 + 0.5 × (children - 1))^0.7`
- Multiple adults with children: `(adults + 0.5 × children)^0.7`
- One adult without children: `1.0`
- Two adults without children: `1.41`
- Three or more adults without children: `adults^0.7`
- Normalized to the reference family `(2 adults, 2 children) = 3^0.7`

**Parameters:**

- `num_adults`: Number of adults (18+) in the SPM unit
- `num_children`: Number of children (under 18) in the SPM unit
- `normalize`: If `True`, normalize to reference family `(2 adults, 2 children) = 1.0`. If `False`, return the raw scale value.

**Returns:** Equivalence scale factor

**Examples:**

```python
from spm_calculator import spm_equivalence_scale

# Reference family (2 adults, 2 children)
scale = spm_equivalence_scale(2, 2)
# 1.0

# Single adult
scale = spm_equivalence_scale(1, 0)
# 0.463

# Couple, no children
scale = spm_equivalence_scale(2, 0)
# 0.653

# Single parent, 2 children
scale = spm_equivalence_scale(1, 2)
# 0.830

# Raw scale (not normalized)
raw = spm_equivalence_scale(2, 2, normalize=False)
# 2.157669279974593
```

### equivalence_scale_from_persons

```python
from spm_calculator.equivalence_scale import equivalence_scale_from_persons

equivalence_scale_from_persons(
    num_persons: Union[int, np.ndarray],
    num_children: Union[int, np.ndarray],
    normalize: bool = True
) -> Union[float, np.ndarray]
```

Calculate equivalence scale when you have total persons and children, rather
than adults and children separately.

**Parameters:**

- `num_persons`: Total number of persons in the SPM unit
- `num_children`: Number of children (under 18)
- `normalize`: If `True`, normalize to reference family `(2 adults, 2 children) = 1.0`

**Returns:** Equivalence scale factor

**Example:**

```python
from spm_calculator.equivalence_scale import equivalence_scale_from_persons

# 4 persons, 2 children = 2 adults, 2 children
scale = equivalence_scale_from_persons(4, 2)
# 1.0
```

## Vectorized Usage

Both functions support NumPy arrays for batch calculation:

```python
import numpy as np
from spm_calculator import spm_equivalence_scale

adults = np.array([1, 2, 2, 3])
children = np.array([0, 0, 2, 4])

scales = spm_equivalence_scale(adults, children)
# array([0.463, 0.653, 1.0, 1.43])
```

## Reference Values

| Family Type | Adults | Children | Raw Scale | Normalized |
|-------------|--------|----------|-----------|------------|
| Single adult | 1 | 0 | 1.000 | 0.463 |
| Couple | 2 | 0 | 1.410 | 0.653 |
| Single parent, 1 child | 1 | 1 | 1.509 | 0.699 |
| Single parent, 2 children | 1 | 2 | 1.791 | 0.830 |
| Reference (2A2C) | 2 | 2 | 2.158 | 1.000 |
| 2 adults, 3 children | 2 | 3 | 2.404 | 1.114 |
| 3 adults, 4 children | 3 | 4 | 3.085 | 1.430 |
