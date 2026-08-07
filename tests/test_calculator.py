"""
Tests for the main SPM calculator API.
"""

import os

import numpy as np
import pytest

REQUIRES_CENSUS_API = pytest.mark.skipif(
    not os.environ.get("CENSUS_API_KEY"),
    reason="Requires CENSUS_API_KEY environment variable",
)

REFERENCE_RAW_SCALE = 3**0.7


class TestSPMCalculator:
    """Test the main SPMCalculator class."""

    def test_initialization(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        assert calc.year == 2024

    def test_get_base_thresholds(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        base = calc.get_base_thresholds()

        assert "renter" in base
        assert "owner_with_mortgage" in base
        assert "owner_without_mortgage" in base
        assert all(v > 0 for v in base.values())

    def test_future_year_base_thresholds_use_shared_forecast_path(self):
        from spm_calculator import SPMCalculator, get_thresholds

        calc = SPMCalculator(year=2026)
        assert calc.get_base_thresholds() == get_thresholds(2026)

    def test_get_geoadj_nation(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        geoadj = calc.get_geoadj("nation", "US", tenure="renter")

        assert geoadj == pytest.approx(1.0)

    def test_get_geoadj_metro_uses_official_census_data(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        geoadj = calc.get_geoadj("metro_area", "35620", tenure="renter")

        assert geoadj == pytest.approx(45736 / 39430)

    @REQUIRES_CENSUS_API
    def test_get_geoadj_state(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        ca_geoadj = calc.get_geoadj("state", "06", tenure="renter")

        assert ca_geoadj > 1.0


class TestThresholdCalculation:
    """Test full threshold calculation."""

    def test_reference_family_national(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        threshold = calc.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="renter",
            geography_type="nation",
            geography_id="US",
        )

        assert threshold == pytest.approx(calc.get_base_thresholds()["renter"])

    def test_single_adult_scales_down(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)

        ref_threshold = calc.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="renter",
            geography_type="nation",
            geography_id="US",
        )

        single_threshold = calc.calculate_threshold(
            num_adults=1,
            num_children=0,
            tenure="renter",
            geography_type="nation",
            geography_id="US",
        )

        ratio = single_threshold / ref_threshold
        assert ratio == pytest.approx(1.0 / REFERENCE_RAW_SCALE)

    def test_reference_family_metro_matches_census_workbook(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        threshold = calc.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="renter",
            geography_type="metro_area",
            geography_id="1002",
        )

        assert threshold == pytest.approx(
            31622 * _correction_rescale("renter")
        )

    def test_spm_threshold_matches_census_workbook(self):
        from spm_calculator import spm_threshold

        assert spm_threshold(
            2, 2, tenure="renter", metro="35620", year=2024
        ) == pytest.approx(45736 * _correction_rescale("renter"))
        assert spm_threshold(
            2,
            2,
            tenure="owner_with_mortgage",
            metro="35620",
            year=2024,
        ) == pytest.approx(45189 * _correction_rescale("owner_with_mortgage"))

    def test_spm_threshold_accepts_metro_name(self):
        """Metro can be a CBSA code or a name; both must resolve."""
        from spm_calculator import spm_threshold

        by_code = spm_threshold(
            2, 2, tenure="renter", metro="41940", year=2024
        )
        by_name = spm_threshold(
            2, 2, tenure="renter", metro="San Jose", year=2024
        )
        assert by_code == pytest.approx(59815 * _correction_rescale("renter"))
        assert by_name == pytest.approx(by_code)

        alabama = spm_threshold(
            1,
            0,
            tenure="owner_without_mortgage",
            metro="Alabama Nonmetro",
            year=2024,
        )
        assert alabama == pytest.approx(
            12921.81 * _correction_rescale("owner_without_mortgage"),
            rel=1e-4,
        )

    def test_tenure_affects_threshold(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)

        renter = calc.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="renter",
            geography_type="nation",
            geography_id="US",
        )

        owner_no_mortgage = calc.calculate_threshold(
            num_adults=2,
            num_children=2,
            tenure="owner_without_mortgage",
            geography_type="nation",
            geography_id="US",
        )

        assert owner_no_mortgage < renter
        ratio = owner_no_mortgage / renter
        assert 0.75 < ratio < 0.90


class TestHouseholdValidation:
    """Guards against child-only and negative-count SPM unit inputs."""

    def test_zero_adults_with_children_raises_scalar(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        with pytest.raises(ValueError, match="at least one adult"):
            calc.calculate_threshold(
                num_adults=0,
                num_children=2,
                tenure="renter",
                geography_type="nation",
                geography_id="US",
            )

    def test_zero_adults_with_children_raises_batch(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        with pytest.raises(ValueError, match="at least one adult"):
            calc.calculate_thresholds(
                num_adults=np.array([1, 0, 2]),
                num_children=np.array([0, 2, 2]),
                tenure="renter",
                geography_type="nation",
                geography_ids="US",
            )

    def test_negative_counts_raise_batch(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        with pytest.raises(ValueError, match="cannot be negative"):
            calc.calculate_thresholds(
                num_adults=np.array([-1, 2]),
                num_children=np.array([0, 2]),
                tenure="renter",
                geography_type="nation",
                geography_ids="US",
            )

    def test_negative_children_raises_batch(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        with pytest.raises(ValueError, match="cannot be negative"):
            calc.calculate_thresholds(
                num_adults=np.array([2, 2]),
                num_children=np.array([0, -1]),
                tenure="renter",
                geography_type="nation",
                geography_ids="US",
            )


class TestBatchCalculation:
    """Test batch/vectorized threshold calculation."""

    @REQUIRES_CENSUS_API
    def test_batch_calculation(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)

        results = calc.calculate_thresholds(
            num_adults=np.array([1, 2, 2, 3]),
            num_children=np.array([0, 0, 2, 4]),
            tenure=["renter", "renter", "renter", "owner_with_mortgage"],
            geography_type="state",
            geography_ids=["06", "06", "54", "54"],
        )

        assert len(results) == 4
        assert all(t > 0 for t in results)

    def test_batch_with_single_geography(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)

        results = calc.calculate_thresholds(
            num_adults=np.array([1, 2, 3]),
            num_children=np.array([0, 2, 4]),
            tenure=["renter", "renter", "renter"],
            geography_type="nation",
            geography_ids="US",
        )

        assert len(results) == 3
        base = calc.get_base_thresholds()["renter"]
        expected_scales = (
            np.array([1.0, REFERENCE_RAW_SCALE, 5**0.7]) / REFERENCE_RAW_SCALE
        )
        expected = base * expected_scales
        np.testing.assert_allclose(results, expected)

    def test_batch_uses_tenure_specific_metro_adjustments(self):
        from spm_calculator import SPMCalculator

        calc = SPMCalculator(year=2024)
        results = calc.calculate_thresholds(
            num_adults=np.array([2, 2, 2]),
            num_children=np.array([2, 2, 2]),
            tenure=[
                "renter",
                "owner_with_mortgage",
                "owner_without_mortgage",
            ],
            geography_type="metro_area",
            geography_ids=["1002", "1002", "1002"],
        )

        np.testing.assert_allclose(
            results,
            np.array(
                [
                    31622 * _correction_rescale("renter"),
                    31489 * _correction_rescale("owner_with_mortgage"),
                    27881 * _correction_rescale("owner_without_mortgage"),
                ]
            ),
        )


# Published 2024 reference thresholds from the Census SPM metro workbook,
# for a 2-adult, 2-child reference family. Pins every tenure across a range
# of cost levels so a regression in rent index, tenure share, or base
# threshold in any direction is caught.
#
# The workbook predates the 2026-07-17 BLS correction: its absolute
# levels embed the pre-correction national base. The bundled geoadj
# ratios (metro / national, same pre-correction vintage) are still
# internally consistent, so composed thresholds now equal the workbook
# value rescaled by (corrected national / published national) for the
# tenure — see `_correction_rescale`. When Census re-releases the metro
# workbook, regenerate the geoadj data and drop the rescale.
CENSUS_2024_METRO_REFERENCE_THRESHOLDS = [
    # (metro_geoid, name, renter, owner_with_mortgage, owner_without_mortgage)
    ("41940", "San Jose (high cost)", 59815, 58855, 44869),
    ("31080", "Los Angeles", 49910, 49241, 38901),
    ("47900", "Washington, DC", 48076, 47461, 37796),
    ("35620", "New York", 45736, 45189, 36386),
    ("16980", "Chicago", 40094, 39712, 32986),
    ("1002", "Alabama Nonmetro (low cost)", 31622, 31489, 27881),
]


def _correction_rescale(tenure: str) -> float:
    """Corrected / pre-correction 2024 national base for a tenure."""
    from spm_calculator.forecast import get_thresholds

    corrected = get_thresholds(2024, allow_forecast=False)
    published = get_thresholds(2024, series="census-published-pre-correction")
    return corrected[tenure] / published[tenure]


@pytest.mark.parametrize(
    "metro_geoid,name,renter,owner_with_mortgage,owner_without_mortgage",
    CENSUS_2024_METRO_REFERENCE_THRESHOLDS,
    ids=[row[1] for row in CENSUS_2024_METRO_REFERENCE_THRESHOLDS],
)
def test_metro_reference_thresholds_match_published_2024(
    metro_geoid,
    name,
    renter,
    owner_with_mortgage,
    owner_without_mortgage,
):
    """All three tenure-specific thresholds for a 2A2C reference family
    must match the Census 2024 SPM metro workbook rescaled onto the
    corrected national base."""
    from spm_calculator import spm_threshold

    assert spm_threshold(
        2, 2, tenure="renter", metro=metro_geoid, year=2024
    ) == pytest.approx(renter * _correction_rescale("renter"))
    assert spm_threshold(
        2, 2, tenure="owner_with_mortgage", metro=metro_geoid, year=2024
    ) == pytest.approx(
        owner_with_mortgage * _correction_rescale("owner_with_mortgage")
    )
    assert spm_threshold(
        2, 2, tenure="owner_without_mortgage", metro=metro_geoid, year=2024
    ) == pytest.approx(
        owner_without_mortgage * _correction_rescale("owner_without_mortgage")
    )
