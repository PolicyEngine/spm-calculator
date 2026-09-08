import pandas as pd
import pytest

from spm_calculator import geoadj


def test_tract_geoid_supplies_state_to_lookup(monkeypatch):
    def lookup(kind, year, state_fips, tenure):
        assert (kind, year, state_fips, tenure) == (
            "tract",
            2023,
            "06",
            "renter",
        )
        return pd.DataFrame(
            {"geography_id": ["06001400100"], "geoadj": [1.25]}
        )

    monkeypatch.setattr(geoadj, "create_geoadj_lookup", lookup)
    assert geoadj.get_geoadj("tract", "06001400100", 2023) == 1.25


@pytest.mark.parametrize(
    "identity", ["6001400100", "06abc400100", "06001", 6001400100]
)
def test_incomplete_tract_geoid_fails_before_request(identity):
    with pytest.raises(ValueError, match="11-digit"):
        geoadj.get_geoadj("tract", identity, 2023)
