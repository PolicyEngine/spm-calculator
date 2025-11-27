"""
Tests for SPM equivalence scale.

The SPM uses a three-parameter equivalence scale:
- First adult: 1.0
- Additional adults: 0.5 each
- Children: 0.3 each
- Reference family (2A2C) = 2.1 raw, normalized to 1.0
"""

import numpy as np
import pytest

from spm_calculator.equivalence_scale import (
    spm_equivalence_scale,
    equivalence_scale_from_persons,
)


class TestSPMEquivalenceScale:
    """Test the SPM three-parameter equivalence scale."""

    def test_reference_family_normalized(self):
        """Reference family (2 adults, 2 children) should equal 1.0."""
        result = spm_equivalence_scale(num_adults=2, num_children=2)
        assert result == pytest.approx(1.0)

    def test_reference_family_raw(self):
        """Reference family raw scale should equal 2.1."""
        # 1.0 (first adult) + 0.5 (second adult) + 0.6 (2 children)
        result = spm_equivalence_scale(
            num_adults=2, num_children=2, normalize=False
        )
        assert result == pytest.approx(2.1)

    def test_single_adult_no_children(self):
        """Single adult = 1.0 raw, 1.0/2.1 normalized."""
        result = spm_equivalence_scale(num_adults=1, num_children=0)
        expected = 1.0 / 2.1
        assert result == pytest.approx(expected)

    def test_couple_no_children(self):
        """Couple with no children = 1.5 raw, 1.5/2.1 normalized."""
        result = spm_equivalence_scale(num_adults=2, num_children=0)
        expected = 1.5 / 2.1
        assert result == pytest.approx(expected)

    def test_single_parent_two_children(self):
        """Single parent with 2 kids = 1.0 + 0.6 = 1.6 raw."""
        result = spm_equivalence_scale(num_adults=1, num_children=2)
        expected = 1.6 / 2.1
        assert result == pytest.approx(expected)

    def test_large_family(self):
        """Large family: 3 adults, 4 children."""
        # 1.0 + 0.5*2 + 0.3*4 = 1.0 + 1.0 + 1.2 = 3.2
        result = spm_equivalence_scale(
            num_adults=3, num_children=4, normalize=False
        )
        assert result == pytest.approx(3.2)

    def test_zero_persons(self):
        """Zero adults should return 0."""
        result = spm_equivalence_scale(num_adults=0, num_children=0)
        assert result == pytest.approx(0.0)

    def test_children_only(self):
        """Children only (edge case) = 0 adults + children."""
        result = spm_equivalence_scale(
            num_adults=0, num_children=2, normalize=False
        )
        # No adults = 0, children = 0.6
        assert result == pytest.approx(0.6)

    def test_vectorized_input(self):
        """Should handle numpy arrays."""
        adults = np.array([1, 2, 2, 3])
        children = np.array([0, 0, 2, 4])

        result = spm_equivalence_scale(adults, children, normalize=False)

        expected = np.array([1.0, 1.5, 2.1, 3.2])
        np.testing.assert_array_almost_equal(result, expected)

    def test_normalized_vectorized(self):
        """Normalized vectorized should all be relative to 2.1."""
        adults = np.array([1, 2, 2])
        children = np.array([0, 0, 2])

        result = spm_equivalence_scale(adults, children, normalize=True)

        expected = np.array([1.0 / 2.1, 1.5 / 2.1, 2.1 / 2.1])
        np.testing.assert_array_almost_equal(result, expected)


class TestEquivalenceScaleFromPersons:
    """Test equivalence scale calculation from total persons."""

    def test_reference_family(self):
        """4 persons, 2 children = 2 adults, 2 children."""
        result = equivalence_scale_from_persons(num_persons=4, num_children=2)
        assert result == pytest.approx(1.0)

    def test_single_adult(self):
        """1 person, 0 children = single adult."""
        result = equivalence_scale_from_persons(num_persons=1, num_children=0)
        expected = 1.0 / 2.1
        assert result == pytest.approx(expected)

    def test_single_parent_one_child(self):
        """2 persons, 1 child = 1 adult, 1 child."""
        result = equivalence_scale_from_persons(num_persons=2, num_children=1)
        # 1.0 + 0.3 = 1.3, normalized = 1.3/2.1
        expected = 1.3 / 2.1
        assert result == pytest.approx(expected)

    def test_more_children_than_persons_clamps(self):
        """If children > persons, adults should be 0."""
        result = equivalence_scale_from_persons(
            num_persons=2, num_children=5, normalize=False
        )
        # 0 adults + 5 children * 0.3 = 1.5
        assert result == pytest.approx(1.5)
