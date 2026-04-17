"""
Official Betson three-parameter SPM equivalence scale.

Source:
- https://www.bls.gov/pir/spmhome.htm
"""

from typing import Union

import numpy as np

# Reference family for SPM thresholds: 2 adults, 2 children.
REFERENCE_RAW_SCALE = 3**0.7


def _maybe_scalar(value: np.ndarray) -> Union[float, np.ndarray]:
    """Return a Python float when the result is scalar-like."""
    if value.ndim == 0:
        return float(value)
    return value


def spm_equivalence_scale(
    num_adults: Union[int, np.ndarray],
    num_children: Union[int, np.ndarray],
    normalize: bool = True,
) -> Union[float, np.ndarray]:
    """
    Calculate the SPM equivalence scale for a family composition.

    The official SPM scale follows Betson's three-parameter form:
    - Single adult with children: (1 + 0.8 + 0.5 * (K - 1)) ** 0.7
    - Multiple adults with children: (A + 0.5 * K) ** 0.7
    - One adult without children: 1.0
    - Two adults without children: 1.41
    - Three or more adults without children: A ** 0.7

    Args:
        num_adults: Number of adults (18+) in the SPM unit.
        num_children: Number of children (under 18) in the SPM unit.
        normalize: If True, divide by the 2-adult, 2-child reference scale.

    Returns:
        Raw or normalized equivalence scale.
    """
    adults, children = np.broadcast_arrays(
        np.asarray(num_adults, dtype=float),
        np.asarray(num_children, dtype=float),
    )

    raw = np.zeros_like(adults, dtype=float)
    # A "child-only" unit (0 adults with children > 0) is not a valid SPM
    # unit — every SPM unit is headed by at least one reference person
    # aged 15+. Treat it like the zero-person case and leave `raw` at 0.0
    # so the calculator surfaces the impossibility downstream rather than
    # synthesising a single-parent scale from a ghost adult.
    has_adults = adults > 0
    with_children = has_adults & (children > 0)

    single_adult_with_children = with_children & (adults == 1)
    raw[single_adult_with_children] = (
        1.0
        + 0.8
        + 0.5 * np.maximum(children[single_adult_with_children] - 1, 0)
    ) ** 0.7

    multi_adult_with_children = with_children & (adults > 1)
    raw[multi_adult_with_children] = (
        adults[multi_adult_with_children]
        + 0.5 * children[multi_adult_with_children]
    ) ** 0.7

    no_children = has_adults & (children == 0)
    one_adult = no_children & (adults == 1)
    two_adults = no_children & (adults == 2)
    larger_adult_units = no_children & (adults > 2)

    raw[one_adult] = 1.0
    raw[two_adults] = 1.41
    raw[larger_adult_units] = adults[larger_adult_units] ** 0.7

    result = raw / REFERENCE_RAW_SCALE if normalize else raw
    return _maybe_scalar(result)


def equivalence_scale_from_persons(
    num_persons: Union[int, np.ndarray],
    num_children: Union[int, np.ndarray],
    normalize: bool = True,
) -> Union[float, np.ndarray]:
    """
    Calculate the equivalence scale from total persons and children.
    """
    num_adults = np.maximum(
        np.asarray(num_persons, dtype=float)
        - np.asarray(num_children, dtype=float),
        0,
    )
    return spm_equivalence_scale(num_adults, num_children, normalize)
