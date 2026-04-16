"""
Main SPM threshold calculation.
"""

from __future__ import annotations

from datetime import date
from typing import Optional, Sequence, Union

import numpy as np

from .ce_threshold import calculate_base_thresholds
from .equivalence_scale import spm_equivalence_scale
from .forecast import get_thresholds
from .geoadj import (
    SUPPORTED_GEOGRAPHIES,
    get_bundled_metro_data,
    get_geoadj,
    get_latest_available_acs_year,
)

VALID_TENURE_TYPES = [
    "renter",
    "owner_with_mortgage",
    "owner_without_mortgage",
]


class SPMCalculator:
    """Calculator for SPM thresholds."""

    def __init__(
        self,
        year: int,
        use_published_thresholds: bool = True,
    ):
        self.year = year
        self.use_published_thresholds = use_published_thresholds
        self._base_thresholds: Optional[dict[str, float]] = None

    def get_base_thresholds(self) -> dict[str, float]:
        """Get reference-family thresholds by tenure type."""
        if self._base_thresholds is not None:
            return self._base_thresholds.copy()

        if self.use_published_thresholds:
            self._base_thresholds = get_thresholds(self.year)
        else:
            self._base_thresholds = calculate_base_thresholds(
                target_year=self.year,
                use_published_fallback=False,
            )

        return self._base_thresholds.copy()

    def _geoadj_year(self, geography_type: str) -> int:
        # Metro area GEOADJ uses the bundled SPM workbook for self.year;
        # nation always returns 1.0 regardless, so the year is irrelevant.
        if geography_type in ("metro_area", "nation"):
            return self.year
        latest_acs_year = get_latest_available_acs_year(date.today())
        return min(self.year - 1, latest_acs_year)

    def get_geoadj(
        self,
        geography_type: str,
        geography_id: str,
        tenure: str = "renter",
    ) -> float:
        """Get a tenure-specific geographic adjustment for a location."""
        geoadj_year = self._geoadj_year(geography_type)
        return get_geoadj(
            geography_type,
            geography_id,
            geoadj_year,
            tenure=tenure,
        )

    def calculate_threshold(
        self,
        num_adults: int,
        num_children: int,
        tenure: str,
        geography_type: str,
        geography_id: str,
    ) -> float:
        """Calculate an SPM threshold for a specific unit and location."""
        if tenure not in VALID_TENURE_TYPES:
            raise ValueError(
                f"Invalid tenure type: {tenure}. "
                f"Must be one of: {VALID_TENURE_TYPES}"
            )

        if num_adults < 0 or num_children < 0:
            raise ValueError("Number of persons cannot be negative")

        if num_adults == 0 and num_children == 0:
            return 0.0

        base = self.get_base_thresholds()[tenure]
        equiv_scale = spm_equivalence_scale(num_adults, num_children)
        geoadj = self.get_geoadj(geography_type, geography_id, tenure=tenure)
        return float(base * equiv_scale * geoadj)

    def calculate_thresholds(
        self,
        num_adults: Union[int, np.ndarray, Sequence[int]],
        num_children: Union[int, np.ndarray, Sequence[int]],
        tenure: Union[str, Sequence[str]],
        geography_type: str,
        geography_ids: Union[str, Sequence[str]],
    ) -> np.ndarray:
        """Calculate SPM thresholds for multiple units."""
        num_adults = np.atleast_1d(num_adults)
        num_children = np.atleast_1d(num_children)
        n = len(num_adults)

        if isinstance(tenure, str):
            tenure = [tenure] * n
        tenure = list(tenure)

        if isinstance(geography_ids, str):
            geography_ids = [geography_ids] * n
        geography_ids = list(geography_ids)

        if not (
            len(num_adults)
            == len(num_children)
            == len(tenure)
            == len(geography_ids)
        ):
            raise ValueError("All input arrays must have same length")

        for tenure_type in tenure:
            if tenure_type not in VALID_TENURE_TYPES:
                raise ValueError(
                    f"Invalid tenure type: {tenure_type}. "
                    f"Must be one of: {VALID_TENURE_TYPES}"
                )

        base_thresholds = self.get_base_thresholds()
        equiv_scales = spm_equivalence_scale(num_adults, num_children)

        unique_pairs = set(zip(geography_ids, tenure))
        pair_to_geoadj = {
            pair: self.get_geoadj(
                geography_type,
                pair[0],
                tenure=pair[1],
            )
            for pair in unique_pairs
        }
        geoadj_values = np.array(
            [
                pair_to_geoadj[(geo_id, tenure_type)]
                for geo_id, tenure_type in zip(geography_ids, tenure)
            ]
        )

        base_values = np.array(
            [base_thresholds[t] for t in tenure], dtype=float
        )
        return base_values * equiv_scales * geoadj_values

    @property
    def supported_geographies(self) -> list[str]:
        return list(SUPPORTED_GEOGRAPHIES.keys())


_metro_name_to_code: Optional[dict[str, str]] = None


def _get_metro_code(metro: str) -> str:
    """Resolve a metro name or code to the bundled metro code."""
    global _metro_name_to_code

    data = get_bundled_metro_data()
    metros = data["metroAreas"]

    if metro in metros:
        return metro

    if _metro_name_to_code is None:
        _metro_name_to_code = {}
        for code, info in metros.items():
            name = info["name"].lower()
            _metro_name_to_code[name] = code
            if "," in name:
                short = name.split(",")[0].strip()
                _metro_name_to_code.setdefault(short, code)
            if " msa" in name:
                short = name.replace(" msa", "").strip()
                _metro_name_to_code.setdefault(short, code)

    metro_lower = metro.lower()
    if metro_lower in _metro_name_to_code:
        return _metro_name_to_code[metro_lower]

    for name, code in _metro_name_to_code.items():
        if metro_lower in name:
            return code

    raise ValueError(
        f"Metro '{metro}' not found. Use a CBSA code like '35620' "
        f"or a name like 'New York' or 'San Jose'."
    )


def spm_threshold(
    num_adults: int,
    num_children: int,
    tenure: str = "renter",
    metro: str = "35620",
    year: int = 2024,
) -> float:
    """
    Convenience entry point for metro-area SPM threshold calculations.

    Args:
        num_adults: Number of adults (18+) in the SPM unit.
        num_children: Number of children (under 18) in the SPM unit.
        tenure: ``"renter"`` (default), ``"owner_with_mortgage"``, or
            ``"owner_without_mortgage"``.
        metro: A CBSA code (e.g. ``"35620"``) or a metro name match
            (e.g. ``"New York"``, ``"San Jose"``). Defaults to New York.
        year: Target threshold year. Defaults to 2024 (latest published).

    Returns:
        SPM threshold in dollars for the given household and metro.

    Example:
        >>> from spm_calculator import spm_threshold
        >>> round(spm_threshold(2, 2, metro="San Jose"))
        59815
        >>> round(spm_threshold(1, 0, tenure="owner_without_mortgage",
        ...                     metro="Alabama Nonmetro"))
        12921
    """
    calc = SPMCalculator(year=year)
    return calc.calculate_threshold(
        num_adults=num_adults,
        num_children=num_children,
        tenure=tenure,
        geography_type="metro_area",
        geography_id=_get_metro_code(metro),
    )
