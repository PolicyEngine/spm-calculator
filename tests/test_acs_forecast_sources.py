"""Source-universe and revision safeguards for Census PUMS inputs."""

import copy
import zipfile

import pandas as pd
import pytest

from spm_calculator.acs_forecast_sources import (
    apply_puma_update,
    load_pums_records,
    normalize_housing,
    sha256_file,
    verify_file,
)


def housing(**changes):
    row = {
        "SERIALNO": "2024HU0000001",
        "STATE": "01",
        "PUMA": "00100",
        "TYPEHUGQ": 1,
        "NP": 2,
        "TEN": 3,
        "BDSP": 2,
        "KIT": 1,
        "PLM": 1,
        "WGTP": 10,
        "GRNTP": 1000,
        "ADJHSG": 1100000,
        "RNTP": 800,
        "ELEP": 100,
        "GASP": 50,
        "FULP": 0,
        "WATP": 600,
    }
    row.update(changes)
    return pd.DataFrame([row])


def topcodes():
    return {
        "2024": {
            "01": {
                "RNTP": {"threshold": 2000, "replacement": 3000},
                "ELEP": {"threshold": 400, "replacement": 500},
                "GASP": {"threshold": 500, "replacement": 600},
                "FULP": {"threshold": 5000, "replacement": 6000},
                "WATP": {"threshold": 2000, "replacement": 3000},
            }
        }
    }


def test_normalization_applies_housing_inflation_once_and_retains_weights():
    data = normalize_housing(housing(), 2024, topcodes())
    assert data.rent.iloc[0] == 1100
    assert data.weight.iloc[0] == 10
    assert data.puma_geoid.iloc[0] == "0100100"
    assert data.cohort_year.iloc[0] == 2024


@pytest.mark.parametrize(
    "field,value", [("TEN", 4), ("KIT", 2), ("PLM", 2), ("NP", 0), ("BDSP", 3)]
)
def test_eligibility_excludes_ineligible_units(field, value):
    assert normalize_housing(housing(**{field: value}), 2024, topcodes()).empty


def test_topcodes_use_cash_and_annual_utility_thresholds_before_adjustment():
    data = normalize_housing(housing(WATP=3000, GRNTP=1200), 2024, topcodes())
    assert data.top_water.iloc[0]
    assert not data.top_rent.iloc[0]
    assert data.rent_lower_bound.iloc[0] == 880


def test_census_utility_blanks_are_included_or_not_separately_paid():
    data = normalize_housing(
        housing(ELEP=float("nan"), GASP=float("nan")), 2024, topcodes()
    )
    assert data.rent.iloc[0] == 1100
    assert not data.top_electricity.iloc[0]
    assert not data.top_gas.iloc[0]


def test_update_replaces_every_cohort_and_excludes_update_only_records():
    original = pd.DataFrame(
        {
            "SERIALNO": ["2018HU1", "2022HU1"],
            "ST": ["01", "01"],
            "PUMA10": ["00100", "-0009"],
            "PUMA20": ["-0009", "00200"],
            "WGTP": [1, 2],
        }
    )
    update = pd.DataFrame(
        {
            "SERIALNO": ["2018HU1", "2022HU1", "2022PR1"],
            "puma": ["00300", "00400", "00500"],
            "wgtp": [3, 4, 99],
        }
    )
    data = apply_puma_update(original, update)
    assert list(data.WGTP) == [3, 4]
    assert list(data.PUMA) == ["00300", "00400"]
    assert list(data.STATE) == ["01", "01"]
    with pytest.raises(ValueError, match="missing|Missing"):
        apply_puma_update(original, update.iloc[:1])
    with pytest.raises(ValueError, match="Duplicate|duplicate"):
        apply_puma_update(original, pd.concat([update, update.iloc[:1]]))


def test_invalid_eligible_data_and_hash_mismatch_fail(tmp_path):
    with pytest.raises(ValueError, match="ADJHSG"):
        normalize_housing(housing(ADJHSG=0), 2024, topcodes())
    file = tmp_path / "input"
    file.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA"):
        verify_file(file, "0" * 64)


def cache_bundle(tmp_path):
    raw = pd.concat(
        [housing(SERIALNO=f"{year}HU0000001") for year in range(2020, 2025)]
    )
    archive_path = tmp_path / "2024/csv_hus.zip"
    archive_path.parent.mkdir()
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("psam_husa.csv", raw.to_csv(index=False))
        for letter in "bcd":
            archive.writestr(
                f"psam_hus{letter}.csv", raw.iloc[:0].to_csv(index=False)
            )
    return {
        "sources": [
            {
                "cache_path": "2024/csv_hus.zip",
                "sha256": sha256_file(archive_path),
            }
        ],
        "topcodes": {
            str(year): topcodes()["2024"] for year in range(2020, 2025)
        },
        "area_allocations": [{"puma_geoid": "0100100"}],
    }


def test_normalized_cache_round_trips_string_columns_without_pickle(
    tmp_path, monkeypatch
):
    import spm_calculator.acs_forecast_sources as sources

    bundle = cache_bundle(tmp_path)
    first = load_pums_records(tmp_path, 2024, bundle)

    def no_reparse(*args, **kwargs):
        raise AssertionError(
            "Verified normalized cache should avoid reparsing"
        )

    monkeypatch.setattr(sources, "normalize_housing", no_reparse)
    second = load_pums_records(tmp_path, 2024, bundle)
    pd.testing.assert_frame_equal(first, second, check_dtype=False)


def test_normalized_cache_uses_supplied_topcodes_not_canonical_pin(tmp_path):
    bundle = cache_bundle(tmp_path)
    first = load_pums_records(tmp_path, 2024, bundle)
    assert not first.top_rent.any()
    changed = copy.deepcopy(bundle)
    changed["topcodes"]["2024"]["01"]["RNTP"]["threshold"] = 700
    cached = load_pums_records(tmp_path, 2024, changed)
    uncached = load_pums_records(
        tmp_path, 2024, changed, use_normalized_cache=False
    )
    assert cached.loc[cached.cohort_year == 2024, "top_rent"].all()
    pd.testing.assert_frame_equal(cached, uncached, check_dtype=False)


def test_normalized_cache_cannot_skip_changed_geography_validation(tmp_path):
    bundle = cache_bundle(tmp_path)
    load_pums_records(tmp_path, 2024, bundle)
    changed = copy.deepcopy(bundle)
    changed["area_allocations"] = [{"puma_geoid": "0100200"}]
    with pytest.raises(ValueError, match="absent from pinned geography"):
        load_pums_records(tmp_path, 2024, changed)
