"""
Tests for the official Betson three-parameter SPM equivalence scale.
"""

import numpy as np
import pytest

from spm_calculator.equivalence_scale import (
    equivalence_scale_from_persons,
    spm_equivalence_scale,
)

REFERENCE_RAW_SCALE = 3**0.7


def expected_raw_scale(num_adults: int, num_children: int) -> float:
    """Official Betson three-parameter raw scale."""
    if num_adults == 0 and num_children == 0:
        return 0.0

    if num_children > 0:
        if num_adults <= 1:
            return (1.0 + 0.8 + 0.5 * max(num_children - 1, 0)) ** 0.7
        return (num_adults + 0.5 * num_children) ** 0.7

    if num_adults == 1:
        return 1.0
    if num_adults == 2:
        return 1.41
    return num_adults**0.7


class TestSPMEquivalenceScale:
    """Test the official SPM equivalence scale."""

    def test_reference_family_normalized(self):
        result = spm_equivalence_scale(num_adults=2, num_children=2)
        assert result == pytest.approx(1.0)

    def test_reference_family_raw(self):
        result = spm_equivalence_scale(
            num_adults=2, num_children=2, normalize=False
        )
        assert result == pytest.approx(REFERENCE_RAW_SCALE)

    def test_single_adult_no_children(self):
        result = spm_equivalence_scale(num_adults=1, num_children=0)
        assert result == pytest.approx(1.0 / REFERENCE_RAW_SCALE)

    def test_couple_no_children_uses_special_case(self):
        result = spm_equivalence_scale(num_adults=2, num_children=0)
        assert result == pytest.approx(1.41 / REFERENCE_RAW_SCALE)

    def test_single_parent_two_children(self):
        result = spm_equivalence_scale(
            num_adults=1, num_children=2, normalize=False
        )
        assert result == pytest.approx((1.0 + 0.8 + 0.5) ** 0.7)

    def test_three_adults_no_children(self):
        result = spm_equivalence_scale(
            num_adults=3, num_children=0, normalize=False
        )
        assert result == pytest.approx(3**0.7)

    def test_large_family(self):
        result = spm_equivalence_scale(
            num_adults=3, num_children=4, normalize=False
        )
        assert result == pytest.approx(5**0.7)

    def test_zero_persons(self):
        result = spm_equivalence_scale(num_adults=0, num_children=0)
        assert result == pytest.approx(0.0)

    def test_vectorized_input(self):
        adults = np.array([1, 2, 1, 3, 3])
        children = np.array([0, 0, 2, 0, 4])

        result = spm_equivalence_scale(adults, children, normalize=False)

        expected = np.array(
            [
                expected_raw_scale(1, 0),
                expected_raw_scale(2, 0),
                expected_raw_scale(1, 2),
                expected_raw_scale(3, 0),
                expected_raw_scale(3, 4),
            ]
        )
        np.testing.assert_allclose(result, expected)

    def test_normalized_vectorized(self):
        adults = np.array([1, 2, 2])
        children = np.array([0, 0, 2])

        result = spm_equivalence_scale(adults, children, normalize=True)

        expected = np.array(
            [
                expected_raw_scale(1, 0) / REFERENCE_RAW_SCALE,
                expected_raw_scale(2, 0) / REFERENCE_RAW_SCALE,
                expected_raw_scale(2, 2) / REFERENCE_RAW_SCALE,
            ]
        )
        np.testing.assert_allclose(result, expected)


class TestEquivalenceScaleFromPersons:
    """Test equivalence scale calculation from total persons."""

    def test_reference_family(self):
        result = equivalence_scale_from_persons(num_persons=4, num_children=2)
        assert result == pytest.approx(1.0)

    def test_single_adult(self):
        result = equivalence_scale_from_persons(num_persons=1, num_children=0)
        assert result == pytest.approx(1.0 / REFERENCE_RAW_SCALE)

    def test_single_parent_one_child(self):
        result = equivalence_scale_from_persons(
            num_persons=2, num_children=1, normalize=False
        )
        assert result == pytest.approx((1.0 + 0.8) ** 0.7)

    def test_more_children_than_persons_returns_zero(self):
        """An SPM unit with more children than total persons is not a
        valid household — it would imply zero (or negative) adults. The
        helper clamps adults at zero and a zero-adult unit returns scale
        0 rather than synthesising a single-parent scale from a ghost
        adult. Users who want the old "single parent of N children"
        reading should call ``spm_equivalence_scale(1, N)`` explicitly."""
        result = equivalence_scale_from_persons(
            num_persons=2, num_children=5, normalize=False
        )
        assert result == pytest.approx(0.0)
