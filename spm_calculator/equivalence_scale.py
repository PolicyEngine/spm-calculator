"""
SPM three-parameter equivalence scale.

The SPM uses a modified OECD equivalence scale to adjust thresholds
for different family compositions.
"""

import numpy as np
from typing import Union


def spm_equivalence_scale(
    num_adults: Union[int, np.ndarray],
    num_children: Union[int, np.ndarray],
    normalize: bool = True,
) -> Union[float, np.ndarray]:
    """
    Calculate SPM equivalence scale for a given family composition.

    The SPM uses a three-parameter equivalence scale:
    - First adult: 1.0
    - Additional adults: 0.5 each
    - Children (under 18): 0.3 each

    Args:
        num_adults: Number of adults (18+) in the SPM unit
        num_children: Number of children (under 18) in the SPM unit
        normalize: If True, normalize to reference family (2A2C = 1.0).
                  If False, return raw scale value.

    Returns:
        Equivalence scale factor. If normalize=True, a family of 2 adults
        and 2 children returns 1.0.

    Examples:
        >>> spm_equivalence_scale(2, 2)  # Reference family
        1.0
        >>> spm_equivalence_scale(1, 0)  # Single adult
        0.476...
        >>> spm_equivalence_scale(2, 0)  # Couple, no children
        0.714...
        >>> spm_equivalence_scale(1, 2)  # Single parent, 2 children
        0.762...
    """
    num_adults = np.asarray(num_adults)
    num_children = np.asarray(num_children)

    # First adult counts as 1.0, additional adults as 0.5 each
    adult_scale = np.where(
        num_adults >= 1,
        1.0 + 0.5 * np.maximum(num_adults - 1, 0),
        0.0,
    )

    # Children count as 0.3 each
    child_scale = 0.3 * num_children

    raw_scale = adult_scale + child_scale

    if normalize:
        # Reference family: 2 adults, 2 children
        # = 1.0 + 0.5*(2-1) + 0.3*2 = 1.0 + 0.5 + 0.6 = 2.1
        reference_scale = 2.1
        return raw_scale / reference_scale
    else:
        return raw_scale


def equivalence_scale_from_persons(
    num_persons: Union[int, np.ndarray],
    num_children: Union[int, np.ndarray],
    normalize: bool = True,
) -> Union[float, np.ndarray]:
    """
    Calculate equivalence scale when you have total persons and children.

    Args:
        num_persons: Total number of persons in SPM unit
        num_children: Number of children (under 18)
        normalize: If True, normalize to reference family (2A2C = 1.0)

    Returns:
        Equivalence scale factor
    """
    num_adults = np.maximum(
        np.asarray(num_persons) - np.asarray(num_children), 0
    )
    return spm_equivalence_scale(num_adults, num_children, normalize)
