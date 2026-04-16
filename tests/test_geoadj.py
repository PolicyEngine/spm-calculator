"""
Tests for geographic adjustments.

For metro areas, the bundled 2024 Census data provides the raw median-rent
index plus tenure-specific reference-family thresholds.
"""

import os

import numpy as np
import pytest

REQUIRES_CENSUS_API = pytest.mark.skipif(
    not os.environ.get("CENSUS_API_KEY"),
    reason="Requires CENSUS_API_KEY environment variable",
)


class TestGeoAdjFormula:
    """Test tenure-specific GEOADJ calculations from rent ratios."""

    def test_national_average_equals_one(self):
        from spm_calculator.geoadj import calculate_geoadj_from_rent

        result = calculate_geoadj_from_rent(
            local_rent=1500, national_rent=1500, tenure="renter"
        )
        assert result == pytest.approx(1.0)

    def test_national_average_equals_one_for_every_tenure(self):
        """Rent ratio of 1.0 must yield GEOADJ=1.0 regardless of tenure."""
        from spm_calculator.geoadj import (
            VALID_TENURE_TYPES,
            calculate_geoadj_from_rent,
        )

        for tenure in VALID_TENURE_TYPES:
            assert calculate_geoadj_from_rent(
                1500, 1500, tenure=tenure
            ) == pytest.approx(
                1.0
            ), f"GEOADJ at rent parity must be 1.0 for {tenure}"

    def test_double_rent_varies_by_tenure(self):
        from spm_calculator.geoadj import calculate_geoadj_from_rent

        assert calculate_geoadj_from_rent(
            3000, 1500, tenure="owner_with_mortgage"
        ) == pytest.approx(1.434)
        assert calculate_geoadj_from_rent(
            3000, 1500, tenure="owner_without_mortgage"
        ) == pytest.approx(1.323)
        assert calculate_geoadj_from_rent(
            3000, 1500, tenure="renter"
        ) == pytest.approx(1.443)

    def test_half_rent_varies_by_tenure(self):
        from spm_calculator.geoadj import calculate_geoadj_from_rent

        assert calculate_geoadj_from_rent(
            750, 1500, tenure="owner_with_mortgage"
        ) == pytest.approx(0.783)
        assert calculate_geoadj_from_rent(
            750, 1500, tenure="owner_without_mortgage"
        ) == pytest.approx(0.8385)
        assert calculate_geoadj_from_rent(
            750, 1500, tenure="renter"
        ) == pytest.approx(0.7785)

    def test_vectorized_calculation(self):
        from spm_calculator.geoadj import calculate_geoadj_from_rent

        local_rents = np.array([1500, 3000, 750])
        national_rent = 1500

        result = calculate_geoadj_from_rent(
            local_rents, national_rent, tenure="renter"
        )

        expected = np.array([1.0, 1.443, 0.7785])
        np.testing.assert_allclose(result, expected)


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
        from spm_calculator.geoadj import SUPPORTED_GEOGRAPHIES

        for geo in self.REQUIRED_GEOGRAPHIES:
            assert geo in SUPPORTED_GEOGRAPHIES, f"{geo} not supported"

    def test_nation_geoadj_is_one(self):
        from spm_calculator.geoadj import get_geoadj

        result = get_geoadj("nation", "US", year=2024, tenure="renter")
        assert result == pytest.approx(1.0)


@REQUIRES_CENSUS_API
class TestStateGeoAdj:
    """Test state-level GEOADJ values."""

    def test_california_above_average(self):
        from spm_calculator.geoadj import get_geoadj

        result = get_geoadj("state", "06", year=2023, tenure="renter")
        assert result > 1.0

    def test_west_virginia_below_average(self):
        from spm_calculator.geoadj import get_geoadj

        result = get_geoadj("state", "54", year=2023, tenure="renter")
        assert result < 1.0


@REQUIRES_CENSUS_API
class TestGeoAdjLookupTable:
    """Test creation and caching of GEOADJ lookup tables."""

    def test_lookup_returns_dataframe(self):
        import pandas as pd

        from spm_calculator.geoadj import create_geoadj_lookup

        result = create_geoadj_lookup("state", year=2023, tenure="renter")
        assert isinstance(result, pd.DataFrame)

    def test_lookup_has_required_columns(self):
        from spm_calculator.geoadj import create_geoadj_lookup

        result = create_geoadj_lookup("state", year=2023, tenure="renter")
        assert "geography_id" in result.columns
        assert "geoadj" in result.columns

    def test_lookup_cached(self):
        from spm_calculator.geoadj import create_geoadj_lookup

        result1 = create_geoadj_lookup("state", year=2023, tenure="renter")
        result2 = create_geoadj_lookup("state", year=2023, tenure="renter")
        assert result1 is result2


class TestBundledCDData:
    """Test bundled congressional district data derived from ACS rents."""

    def test_get_cd_geoadj_basic(self):
        from spm_calculator import get_cd_geoadj

        result = get_cd_geoadj("612", tenure="renter")
        assert result > 1.2
        assert result <= 1.5

    def test_get_cd_geoadj_is_tenure_specific(self):
        from spm_calculator import get_cd_geoadj

        renter = get_cd_geoadj("612", tenure="renter")
        owner_nm = get_cd_geoadj("612", tenure="owner_without_mortgage")
        owner_m = get_cd_geoadj("612", tenure="owner_with_mortgage")
        # All three tenures must be callable and produce distinct, sensible
        # high-cost values (CA-12 is well above national rent).
        assert renter > 1.0
        assert owner_m > 1.0
        assert owner_nm > 1.0
        # For high-cost areas the share ordering (renter 0.443 > owner_m
        # 0.434 > owner_nm 0.323) pushes renter > owner_m > owner_nm.
        assert renter > owner_m > owner_nm

    def test_get_cd_geoadj_int_input(self):
        from spm_calculator import get_cd_geoadj

        result = get_cd_geoadj(612, tenure="renter")
        assert result > 1.2

    def test_get_cd_geoadj_with_leading_zeros(self):
        from spm_calculator import get_cd_geoadj

        result1 = get_cd_geoadj("612", tenure="renter")
        result2 = get_cd_geoadj("0612", tenure="renter")
        assert result1 == result2

    def test_get_cd_geoadj_low_cost_area(self):
        from spm_calculator import get_cd_geoadj

        result = get_cd_geoadj("5401", tenure="renter")
        assert result < 0.9

    def test_get_cd_geoadj_invalid_cd_raises(self):
        from spm_calculator import get_cd_geoadj

        with pytest.raises(ValueError, match="not found"):
            get_cd_geoadj("9999", tenure="renter")

    def test_get_cd_geoadj_batch_basic(self):
        from spm_calculator import get_cd_geoadj_batch

        cds = ["612", "3612", "101"]
        result = get_cd_geoadj_batch(cds, tenure="renter")

        assert len(result) == 3
        assert result[0] > 1.2
        assert result[1] > 1.3
        assert result[2] < 0.9

    def test_get_bundled_cd_data_structure(self):
        from spm_calculator import get_bundled_cd_data

        data = get_bundled_cd_data()

        assert "year" in data
        assert "national_median_2br_rent" in data
        assert "congressional_districts" in data

    def test_get_bundled_cd_data_cd_structure(self):
        from spm_calculator import get_bundled_cd_data

        data = get_bundled_cd_data()
        cd_612 = data["congressional_districts"]["612"]

        assert "geoadj" in cd_612
        assert "name" in cd_612
        assert "median_2br_rent" in cd_612

    def test_invalid_year_raises(self):
        from spm_calculator import get_cd_geoadj

        with pytest.raises(ValueError, match="No bundled CD data"):
            get_cd_geoadj("612", year=2010, tenure="renter")


class TestBundledMetroData:
    """Test bundled official Census metro thresholds."""

    def test_get_metro_rent_index_basic(self):
        from spm_calculator.geoadj import get_metro_rent_index

        result = get_metro_rent_index("35620")
        assert result == pytest.approx(1.361)

    def test_get_metro_geoadj_matches_official_renter_threshold(self):
        from spm_calculator import get_metro_geoadj

        result = get_metro_geoadj("35620", tenure="renter")
        assert result == pytest.approx(45736 / 39430)

    def test_get_metro_geoadj_is_tenure_specific(self):
        from spm_calculator import get_metro_geoadj

        renter = get_metro_geoadj("1002", tenure="renter")
        owner = get_metro_geoadj("1002", tenure="owner_without_mortgage")
        assert renter < owner

    def test_get_metro_geoadj_batch(self):
        from spm_calculator import get_metro_geoadj

        codes = ["35620", "41940", "1002"]
        result = get_metro_geoadj(codes, tenure="renter")

        np.testing.assert_allclose(
            result,
            np.array([45736 / 39430, 59815 / 39430, 31622 / 39430]),
        )

    def test_get_bundled_metro_data_structure(self):
        from spm_calculator import get_bundled_metro_data

        data = get_bundled_metro_data()

        assert "year" in data
        assert "source" in data
        assert "sourceUrl" in data
        assert "nationalThresholds" in data
        assert "housingShares" in data
        assert "metroAreas" in data
        assert data["year"] == 2024

    def test_get_bundled_metro_data_metro_count(self):
        from spm_calculator import get_bundled_metro_data

        data = get_bundled_metro_data()
        metros = data["metroAreas"]

        assert len(metros) == 341

    def test_get_bundled_metro_data_metro_structure(self):
        from spm_calculator import get_bundled_metro_data

        data = get_bundled_metro_data()
        nyc = data["metroAreas"]["35620"]

        assert "rentIndex" in nyc
        assert "adjustments" in nyc
        assert "referenceThresholds" in nyc
        assert "name" in nyc
        assert "New York" in nyc["name"]

    def test_list_metro_areas(self):
        from spm_calculator.geoadj import list_metro_areas

        metros = list_metro_areas()

        assert len(metros) == 341
        assert all(
            "code" in m and "name" in m and "rentIndex" in m for m in metros
        )
        assert metros[0]["name"] < metros[-1]["name"]

    def test_invalid_metro_year_raises(self):
        from spm_calculator import get_metro_geoadj

        with pytest.raises(ValueError, match="No bundled metro data"):
            get_metro_geoadj("35620", year=2010, tenure="renter")


class TestInvalidInputs:
    """Test error handling for invalid inputs."""

    def test_invalid_geography_type_raises(self):
        from spm_calculator.geoadj import get_geoadj

        with pytest.raises(ValueError, match="Unsupported geography"):
            get_geoadj("invalid_geo_type", "12345", year=2023, tenure="renter")

    @REQUIRES_CENSUS_API
    def test_invalid_geography_id_raises(self):
        from spm_calculator.geoadj import get_geoadj

        with pytest.raises(ValueError, match="not found"):
            get_geoadj("state", "99", year=2023, tenure="renter")

    def test_future_year_raises_for_nonmetro_when_unavailable(self):
        from spm_calculator.geoadj import get_geoadj

        with pytest.raises(ValueError, match="not available"):
            get_geoadj("state", "06", year=2035, tenure="renter")
