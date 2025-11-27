"""
Main SPMCalculator class for calculating SPM thresholds.

The full SPM threshold calculation is:
    threshold = base_threshold[tenure] × equivalence_scale × geoadj

Where:
- base_threshold varies by housing tenure (from CE Survey)
- equivalence_scale adjusts for family composition
- geoadj adjusts for local housing costs
"""

from typing import Union, Optional, Sequence

import numpy as np

from .ce_threshold import get_published_thresholds, calculate_base_thresholds
from .equivalence_scale import spm_equivalence_scale
from .geoadj import get_geoadj, create_geoadj_lookup, SUPPORTED_GEOGRAPHIES


VALID_TENURE_TYPES = [
    "renter",
    "owner_with_mortgage",
    "owner_without_mortgage",
]


class SPMCalculator:
    """
    Calculator for Supplemental Poverty Measure thresholds.

    Calculates SPM thresholds for any US geography and year using:
    - Base thresholds from BLS Consumer Expenditure Survey
    - Geographic adjustments from ACS median rents
    - SPM three-parameter equivalence scale

    Example:
        >>> calc = SPMCalculator(year=2024)
        >>> threshold = calc.calculate_threshold(
        ...     num_adults=2,
        ...     num_children=2,
        ...     tenure="renter",
        ...     geography_type="congressional_district",
        ...     geography_id="0612"
        ... )
    """

    def __init__(
        self,
        year: int,
        use_published_thresholds: bool = True,
    ):
        """
        Initialize SPMCalculator for a specific year.

        Args:
            year: Target year for threshold calculation
            use_published_thresholds: If True, use published BLS thresholds
                when available. If False, calculate from CE Survey data.
        """
        self.year = year
        self.use_published_thresholds = use_published_thresholds
        self._base_thresholds: Optional[dict[str, float]] = None

    def get_base_thresholds(self) -> dict[str, float]:
        """
        Get base SPM thresholds by tenure type.

        Returns thresholds for the reference family (2 adults, 2 children)
        before geographic adjustment.

        Returns:
            Dict with keys 'renter', 'owner_with_mortgage',
            'owner_without_mortgage' and threshold values in dollars.
        """
        if self._base_thresholds is not None:
            return self._base_thresholds.copy()

        if self.use_published_thresholds:
            try:
                self._base_thresholds = get_published_thresholds(self.year)
            except ValueError:
                # Published not available, forecast from latest available
                # Use simple CPI-U projection from 2024 for now
                # TODO: Implement proper CE-based forecasting
                latest_thresholds = get_published_thresholds(2024)
                years_ahead = self.year - 2024
                # Assume ~3% annual inflation
                inflation_factor = 1.03**years_ahead
                self._base_thresholds = {
                    k: v * inflation_factor
                    for k, v in latest_thresholds.items()
                }
        else:
            self._base_thresholds = calculate_base_thresholds(
                target_year=self.year,
                use_published_fallback=False,
            )

        return self._base_thresholds.copy()

    def get_geoadj(
        self,
        geography_type: str,
        geography_id: str,
    ) -> float:
        """
        Get geographic adjustment factor for a specific location.

        Args:
            geography_type: Type of geography (nation, state, county,
                congressional_district, etc.)
            geography_id: Geography identifier (FIPS code, etc.)

        Returns:
            GEOADJ value (typically 0.84 to 1.27)
        """
        # Use year - 1 for ACS data (lag)
        acs_year = min(self.year - 1, 2022)  # TODO: Update as data available
        return get_geoadj(geography_type, geography_id, acs_year)

    def calculate_threshold(
        self,
        num_adults: int,
        num_children: int,
        tenure: str,
        geography_type: str,
        geography_id: str,
    ) -> float:
        """
        Calculate SPM threshold for a specific SPM unit and location.

        Args:
            num_adults: Number of adults (18+) in the SPM unit
            num_children: Number of children (under 18) in the SPM unit
            tenure: Housing tenure type ('renter', 'owner_with_mortgage',
                'owner_without_mortgage')
            geography_type: Type of geography (nation, state, county, etc.)
            geography_id: Geography identifier

        Returns:
            SPM threshold in dollars

        Raises:
            ValueError: If tenure type invalid or geography not found
        """
        # Validate inputs
        if tenure not in VALID_TENURE_TYPES:
            raise ValueError(
                f"Invalid tenure type: {tenure}. "
                f"Must be one of: {VALID_TENURE_TYPES}"
            )

        if num_adults < 0 or num_children < 0:
            raise ValueError("Number of persons cannot be negative")

        # Zero persons = zero threshold
        if num_adults == 0 and num_children == 0:
            return 0.0

        # Get components
        base = self.get_base_thresholds()[tenure]
        equiv_scale = spm_equivalence_scale(num_adults, num_children)
        geoadj = self.get_geoadj(geography_type, geography_id)

        return base * equiv_scale * geoadj

    def calculate_thresholds(
        self,
        num_adults: Union[int, np.ndarray, Sequence[int]],
        num_children: Union[int, np.ndarray, Sequence[int]],
        tenure: Union[str, Sequence[str]],
        geography_type: str,
        geography_ids: Union[str, Sequence[str]],
    ) -> np.ndarray:
        """
        Calculate SPM thresholds for multiple SPM units (vectorized).

        Args:
            num_adults: Number of adults for each unit
            num_children: Number of children for each unit
            tenure: Tenure type(s) - single value or per-unit
            geography_type: Type of geography (same for all)
            geography_ids: Geography ID(s) - single value or per-unit

        Returns:
            Array of SPM thresholds
        """
        # Convert to arrays
        num_adults = np.atleast_1d(num_adults)
        num_children = np.atleast_1d(num_children)
        n = len(num_adults)

        # Handle tenure
        if isinstance(tenure, str):
            tenure = [tenure] * n
        tenure = list(tenure)

        # Handle geography_ids
        if isinstance(geography_ids, str):
            geography_ids = [geography_ids] * n
        geography_ids = list(geography_ids)

        # Validate lengths
        if not (
            len(num_adults)
            == len(num_children)
            == len(tenure)
            == len(geography_ids)
        ):
            raise ValueError("All input arrays must have same length")

        # Validate tenure types
        for t in tenure:
            if t not in VALID_TENURE_TYPES:
                raise ValueError(
                    f"Invalid tenure type: {t}. "
                    f"Must be one of: {VALID_TENURE_TYPES}"
                )

        # Get base thresholds
        base_thresholds = self.get_base_thresholds()

        # Calculate equivalence scales (vectorized)
        equiv_scales = spm_equivalence_scale(num_adults, num_children)

        # Get GEOADJ values
        # Cache unique geographies
        unique_geos = set(geography_ids)
        geo_to_geoadj = {}
        for geo_id in unique_geos:
            geo_to_geoadj[geo_id] = self.get_geoadj(geography_type, geo_id)

        geoadj_values = np.array([geo_to_geoadj[g] for g in geography_ids])

        # Get base values by tenure
        base_values = np.array([base_thresholds[t] for t in tenure])

        # Calculate thresholds
        thresholds = base_values * equiv_scales * geoadj_values

        return thresholds

    @property
    def supported_geographies(self) -> list[str]:
        """List of supported geography types."""
        return list(SUPPORTED_GEOGRAPHIES.keys())
