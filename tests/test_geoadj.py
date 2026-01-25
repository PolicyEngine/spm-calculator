"""
Tests for geographic adjustment (GEOADJ) calculation.

GEOADJ formula:
    GEOADJ = (local_median_rent / national_median_rent) × 0.492 + 0.508

Where 0.492 is the housing portion of the SPM threshold for renters.

Expected range: ~0.84 (West Virginia) to ~1.27 (Hawaii)

Sources:
- Census SPM methodology
- ACS Table B25031: Median Gross Rent by Bedrooms
"""

import pytest
import numpy as np


class TestGeoAdjFormula:
    """Test the GEOADJ formula calculation."""

    def test_national_average_equals_one(self):
        """When local rent equals national, GEOADJ should be 1.0."""
        from spm_calculator.geoadj import calculate_geoadj_from_rent

        result = calculate_geoadj_from_rent(
            local_rent=1500, national_rent=1500
        )
        assert result == pytest.approx(1.0)

    def test_double_rent_gives_correct_geoadj(self):
        """If local rent is 2x national, GEOADJ should be ~1.49."""
        from spm_calculator.geoadj import calculate_geoadj_from_rent

        # GEOADJ = 2.0 * 0.492 + 0.508 = 0.984 + 0.508 = 1.492
        result = calculate_geoadj_from_rent(
            local_rent=3000, national_rent=1500
        )
        assert result == pytest.approx(1.492)

    def test_half_rent_gives_correct_geoadj(self):
        """If local rent is 0.5x national, GEOADJ should be ~0.75."""
        from spm_calculator.geoadj import calculate_geoadj_from_rent

        # GEOADJ = 0.5 * 0.492 + 0.508 = 0.246 + 0.508 = 0.754
        result = calculate_geoadj_from_rent(local_rent=750, national_rent=1500)
        assert result == pytest.approx(0.754)

    def test_vectorized_calculation(self):
        """Should handle numpy arrays."""
        from spm_calculator.geoadj import calculate_geoadj_from_rent

        local_rents = np.array([1500, 3000, 750])
        national_rent = 1500

        result = calculate_geoadj_from_rent(local_rents, national_rent)

        expected = np.array([1.0, 1.492, 0.754])
        np.testing.assert_array_almost_equal(result, expected)


class TestGeoAdjRanges:
    """Test that GEOADJ values fall within expected ranges."""

    def test_minimum_geoadj_reasonable(self):
        """Minimum GEOADJ should be around 0.84 (West Virginia)."""
        # WV has lowest housing costs
        # If rent is ~55% of national: 0.55 * 0.492 + 0.508 = 0.779
        from spm_calculator.geoadj import calculate_geoadj_from_rent

        # Very low rent area (50% of national)
        result = calculate_geoadj_from_rent(750, 1500)
        assert result > 0.70, "Minimum GEOADJ should be > 0.70"

    def test_maximum_geoadj_reasonable(self):
        """Maximum GEOADJ should be around 1.27 (Hawaii)."""
        from spm_calculator.geoadj import calculate_geoadj_from_rent

        # Very high rent area (160% of national)
        result = calculate_geoadj_from_rent(2400, 1500)
        assert result < 1.40, "Maximum GEOADJ should be < 1.40"


class TestSupportedGeographies:
    """Test that all required geography types are supported."""

    REQUIRED_GEOGRAPHIES = [
        "nation",
        "state",
        "county",
        "metro_area",
        "congressional_district",
        "puma",
        "tract",
    ]

    def test_all_geography_types_defined(self):
        """All required geography types should be supported."""
        from spm_calculator.geoadj import SUPPORTED_GEOGRAPHIES

        for geo in self.REQUIRED_GEOGRAPHIES:
            assert geo in SUPPORTED_GEOGRAPHIES, f"{geo} not supported"

    def test_nation_geoadj_is_one(self):
        """National GEOADJ should always be 1.0."""
        from spm_calculator.geoadj import get_geoadj

        result = get_geoadj("nation", "US", year=2022)
        assert result == pytest.approx(1.0)


import os

# Mark tests requiring Census API
REQUIRES_CENSUS_API = pytest.mark.skipif(
    not os.environ.get("CENSUS_API_KEY"),
    reason="Requires CENSUS_API_KEY environment variable",
)


@pytest.mark.skipif(
    not os.environ.get("CENSUS_API_KEY"),
    reason="Requires CENSUS_API_KEY environment variable",
)
class TestStateGeoAdj:
    """Test state-level GEOADJ values."""

    def test_california_above_average(self):
        """California should have GEOADJ > 1.0."""
        from spm_calculator.geoadj import get_geoadj

        result = get_geoadj("state", "06", year=2022)  # CA FIPS = 06
        assert result > 1.0, "California should be above average"

    def test_west_virginia_below_average(self):
        """West Virginia should have GEOADJ < 1.0."""
        from spm_calculator.geoadj import get_geoadj

        result = get_geoadj("state", "54", year=2022)  # WV FIPS = 54
        assert result < 1.0, "West Virginia should be below average"

    def test_hawaii_highest(self):
        """Hawaii should have high GEOADJ (~1.20+)."""
        from spm_calculator.geoadj import get_geoadj

        result = get_geoadj("state", "15", year=2022)  # HI FIPS = 15
        assert result > 1.15, "Hawaii should have GEOADJ > 1.15"


@pytest.mark.skipif(
    not os.environ.get("CENSUS_API_KEY"),
    reason="Requires CENSUS_API_KEY environment variable",
)
class TestCongressionalDistrictGeoAdj:
    """Test congressional district-level GEOADJ values."""

    def test_sf_district_high(self):
        """San Francisco area district should have high GEOADJ."""
        from spm_calculator.geoadj import get_geoadj

        # CA-11 or CA-12 (San Francisco area)
        result = get_geoadj("congressional_district", "0611", year=2022)
        assert result > 1.15, "SF district should have high GEOADJ"

    def test_rural_district_low(self):
        """Rural district should have lower GEOADJ."""
        from spm_calculator.geoadj import get_geoadj

        # WV-01 or similar rural district
        result = get_geoadj("congressional_district", "5401", year=2022)
        assert result < 1.0, "Rural WV district should be below average"

    def test_all_435_districts_available(self):
        """Should have GEOADJ for all 435 congressional districts."""
        from spm_calculator.geoadj import create_geoadj_lookup

        lookup = create_geoadj_lookup("congressional_district", year=2022)
        # 435 districts + DC (at-large) + territories
        assert len(lookup) >= 435


@pytest.mark.skipif(
    not os.environ.get("CENSUS_API_KEY"),
    reason="Requires CENSUS_API_KEY environment variable",
)
class TestGeoAdjLookupTable:
    """Test creation and caching of GEOADJ lookup tables."""

    def test_lookup_returns_dataframe(self):
        """create_geoadj_lookup should return a DataFrame."""
        from spm_calculator.geoadj import create_geoadj_lookup
        import pandas as pd

        result = create_geoadj_lookup("state", year=2022)
        assert isinstance(result, pd.DataFrame)

    def test_lookup_has_required_columns(self):
        """Lookup table should have geography_id and geoadj columns."""
        from spm_calculator.geoadj import create_geoadj_lookup

        result = create_geoadj_lookup("state", year=2022)
        assert "geography_id" in result.columns
        assert "geoadj" in result.columns

    def test_lookup_cached(self):
        """Repeated calls should return cached result."""
        from spm_calculator.geoadj import create_geoadj_lookup

        result1 = create_geoadj_lookup("state", year=2022)
        result2 = create_geoadj_lookup("state", year=2022)

        # Should be the same object (cached)
        assert result1 is result2


class TestBundledCDData:
    """Test bundled congressional district GEOADJ data (no API key required)."""

    def test_get_cd_geoadj_basic(self):
        """Should return GEOADJ for a valid CD."""
        from spm_calculator import get_cd_geoadj

        # CA-12 (San Francisco) should have high GEOADJ
        result = get_cd_geoadj("612")
        assert result > 1.2, "SF district should have high GEOADJ"
        assert result <= 1.5, "GEOADJ should be clamped to 1.5"

    def test_get_cd_geoadj_int_input(self):
        """Should accept integer CD GEOID."""
        from spm_calculator import get_cd_geoadj

        result = get_cd_geoadj(612)  # int instead of string
        assert result > 1.2

    def test_get_cd_geoadj_with_leading_zeros(self):
        """Should handle zero-padded GEOIDs like '0612'."""
        from spm_calculator import get_cd_geoadj

        # Both formats should work
        result1 = get_cd_geoadj("612")
        result2 = get_cd_geoadj("0612")
        assert result1 == result2

    def test_get_cd_geoadj_low_cost_area(self):
        """Rural/low-cost areas should have GEOADJ < 1.0."""
        from spm_calculator import get_cd_geoadj

        # WV-01 (West Virginia) should have low GEOADJ
        result = get_cd_geoadj("5401")
        assert result < 0.9, "WV district should have low GEOADJ"

    def test_get_cd_geoadj_ny_manhattan(self):
        """NY-12 (Manhattan) should have maximum GEOADJ (clamped)."""
        from spm_calculator import get_cd_geoadj

        result = get_cd_geoadj("3612")
        assert result == pytest.approx(
            1.5
        ), "Manhattan should be at max (clamped)"

    def test_get_cd_geoadj_invalid_cd_raises(self):
        """Invalid CD should raise ValueError."""
        from spm_calculator import get_cd_geoadj

        with pytest.raises(ValueError, match="not found"):
            get_cd_geoadj("9999")  # No such CD

    def test_get_cd_geoadj_batch_basic(self):
        """Should return array of GEOADJ values for multiple CDs."""
        from spm_calculator import get_cd_geoadj_batch

        cds = ["612", "3612", "101"]  # CA-12, NY-12, AL-01
        result = get_cd_geoadj_batch(cds)

        assert len(result) == 3
        assert result[0] > 1.2  # CA-12 high
        assert result[1] == pytest.approx(1.5)  # NY-12 max
        assert result[2] < 0.9  # AL-01 low

    def test_get_cd_geoadj_batch_mixed_formats(self):
        """Should handle mixed string/int and padded/unpadded formats."""
        from spm_calculator import get_cd_geoadj_batch

        cds = [612, "0612", "612"]  # All same CD
        result = get_cd_geoadj_batch(cds)

        assert result[0] == result[1] == result[2]

    def test_get_bundled_cd_data_structure(self):
        """Should return dict with expected structure."""
        from spm_calculator import get_bundled_cd_data

        data = get_bundled_cd_data()

        assert "year" in data
        assert "national_median_2br_rent" in data
        assert "housing_share" in data
        assert "congressional_districts" in data
        assert data["housing_share"] == pytest.approx(0.492)

    def test_get_bundled_cd_data_cd_count(self):
        """Should have data for all 435+ congressional districts."""
        from spm_calculator import get_bundled_cd_data

        data = get_bundled_cd_data()
        cds = data["congressional_districts"]

        # At least 435 CDs (plus at-large states, DC delegate)
        # With both padded and unpadded keys, count unique by int value
        unique_cds = set(int(k) for k in cds.keys())
        assert len(unique_cds) >= 435

    def test_get_bundled_cd_data_cd_structure(self):
        """Each CD should have geoadj, name, and median_2br_rent."""
        from spm_calculator import get_bundled_cd_data

        data = get_bundled_cd_data()
        cd_612 = data["congressional_districts"]["612"]

        assert "geoadj" in cd_612
        assert "name" in cd_612
        assert "median_2br_rent" in cd_612
        assert cd_612["geoadj"] > 0
        assert cd_612["median_2br_rent"] > 0

    def test_invalid_year_raises(self):
        """Requesting unavailable year should raise ValueError."""
        from spm_calculator import get_cd_geoadj

        with pytest.raises(ValueError, match="No bundled CD data"):
            get_cd_geoadj("612", year=2010)


class TestInvalidInputs:
    """Test error handling for invalid inputs."""

    def test_invalid_geography_type_raises(self):
        """Invalid geography type should raise ValueError."""
        from spm_calculator.geoadj import get_geoadj

        with pytest.raises(ValueError, match="Unsupported geography"):
            get_geoadj("invalid_geo_type", "12345", year=2022)

    @pytest.mark.skipif(
        not os.environ.get("CENSUS_API_KEY"),
        reason="Requires CENSUS_API_KEY environment variable",
    )
    def test_invalid_geography_id_raises(self):
        """Invalid geography ID should raise ValueError."""
        from spm_calculator.geoadj import get_geoadj

        with pytest.raises(ValueError, match="not found"):
            get_geoadj("state", "99", year=2022)  # No state FIPS 99

    def test_future_year_raises(self):
        """Year in future should raise ValueError."""
        from spm_calculator.geoadj import get_geoadj

        with pytest.raises(ValueError, match="not available"):
            get_geoadj("state", "06", year=2030)
