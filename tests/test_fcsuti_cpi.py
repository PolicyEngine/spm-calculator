"""Unit tests for the FCSUti CPI module.

Covers the pure-function helpers that run without hitting the BLS API:
``compute_fcsuti_weights_from_ce`` and the ``weights`` plumbing on the
composite-CPI builders, plus the offline fallback paths (precomputed
factors, composed factors) and the BLS registration-key plumbing.
End-to-end tests that actually fetch BLS data are network-gated in
``test_ce_validation.py``.
"""

from __future__ import annotations

import warnings

import pandas as pd
import pytest

from spm_calculator import fcsuti_cpi
from spm_calculator.fcsuti_cpi import (
    FCSUTI_WEIGHTS,
    PRECOMPUTED_FCSUTI_FACTORS,
    _compose_precomputed_fcsuti_factor,
    _directed_precomputed_factor,
    compute_fcsuti_weights_from_ce,
    fetch_bls_cpi_series,
    get_fcsuti_cpi,
    get_fcsuti_inflation_factor,
    get_precomputed_fcsuti_factor,
)


def _sample_ce_df(extra: dict | None = None) -> pd.DataFrame:
    """Build a synthetic FMLI DataFrame with the columns we care about."""
    base = {
        "PERSLT18": [1, 2, 0, 1],
        "FINLWT21": [100.0, 200.0, 150.0, 50.0],
        "FOODPQ": [1000.0, 2000.0, 800.0, 500.0],
        "FOODCQ": [1000.0, 2000.0, 800.0, 500.0],
        "APPARPQ": [100.0, 200.0, 50.0, 60.0],
        "APPARCQ": [100.0, 200.0, 50.0, 60.0],
        "SHELTPQ": [3000.0, 4000.0, 2500.0, 1800.0],
        "SHELTCQ": [3000.0, 4000.0, 2500.0, 1800.0],
        "UTILPQ": [500.0, 800.0, 400.0, 300.0],
        "UTILCQ": [500.0, 800.0, 400.0, 300.0],
        "TELEPHPQ": [200.0, 250.0, 180.0, 150.0],
        "TELEPHCQ": [200.0, 250.0, 180.0, 150.0],
    }
    if extra:
        base.update(extra)
    return pd.DataFrame(base)


class TestComputeFcsutiWeightsFromCE:
    def test_shares_sum_to_one(self):
        ce = _sample_ce_df()
        weights = compute_fcsuti_weights_from_ce(ce)
        assert pytest.approx(sum(weights.values()), rel=1e-12) == 1.0

    def test_restricts_to_consumer_units_with_children(self):
        """CUs with zero children must not contribute to the shares."""
        ce = _sample_ce_df()
        # Flip every CU to childless and watch the function reject the input.
        ce_childless = ce.assign(PERSLT18=0)
        with pytest.raises(
            ValueError, match="No consumer units with children"
        ):
            compute_fcsuti_weights_from_ce(ce_childless)

        # Now make one CU (row 2, weight 150) stay childless and keep the
        # other three. Row 2's expenditures must be excluded from the
        # share calculation.
        mixed = ce.copy()
        with_children_mask = mixed["PERSLT18"] > 0
        with_children_only = compute_fcsuti_weights_from_ce(
            mixed[with_children_mask].reset_index(drop=True)
        )
        all_rows_weights = compute_fcsuti_weights_from_ce(mixed)
        assert all_rows_weights == pytest.approx(with_children_only)

    def test_weight_proportional_expenditure(self):
        """Manually compute expected shares from the synthetic sample."""
        ce = _sample_ce_df()
        # Rows with PERSLT18 > 0 are indices 0, 1, 3 with FINLWT21 =
        # 100, 200, 50. Food PQ+CQ for those rows: 2000, 4000, 1000 ->
        # weighted sum matches the hand-computed totals below.
        food = 2000 * 100 + 4000 * 200 + 1000 * 50
        apparel = 200 * 100 + 400 * 200 + 120 * 50
        shelter = 6000 * 100 + 8000 * 200 + 3600 * 50
        util = 1000 * 100 + 1600 * 200 + 600 * 50
        tele = 400 * 100 + 500 * 200 + 300 * 50
        total = food + apparel + shelter + util + tele

        weights = compute_fcsuti_weights_from_ce(ce)
        assert weights["food"] == pytest.approx(food / total)
        assert weights["apparel"] == pytest.approx(apparel / total)
        assert weights["shelter"] == pytest.approx(shelter / total)
        assert weights["utilities"] == pytest.approx(util / total)
        assert weights["telephone"] == pytest.approx(tele / total)

    def test_subtracts_mortgage_principal_from_shelter(self):
        """When MRTPRIN columns are present, shelter is net of principal."""
        ce = _sample_ce_df(
            {
                "MRTPRINPQ": [500.0, 1000.0, 200.0, 0.0],
                "MRTPRINCQ": [500.0, 1000.0, 200.0, 0.0],
            }
        )
        with_subtraction = compute_fcsuti_weights_from_ce(
            ce, subtract_mortgage_principal=True
        )
        without_subtraction = compute_fcsuti_weights_from_ce(
            ce, subtract_mortgage_principal=False
        )
        # Shelter share shrinks when principal is subtracted out.
        assert with_subtraction["shelter"] < without_subtraction["shelter"]
        # Other components' shares rise (same numerator, smaller denominator).
        assert with_subtraction["food"] > without_subtraction["food"]

    def test_includes_internet_when_infotech_columns_present(self):
        ce = _sample_ce_df(
            {
                "INFOTECHPQ": [300.0, 400.0, 200.0, 180.0],
                "INFOTECHCQ": [300.0, 400.0, 200.0, 180.0],
            }
        )
        weights = compute_fcsuti_weights_from_ce(ce)
        assert "internet" in weights
        assert weights["internet"] > 0

    def test_missing_component_column_silently_dropped(self):
        """If a component's expenditure columns aren't present, the
        component is omitted from the returned shares rather than
        treated as zero (and the remaining shares re-normalize)."""
        ce = _sample_ce_df().drop(columns=["APPARPQ", "APPARCQ"])
        weights = compute_fcsuti_weights_from_ce(ce)
        assert "apparel" not in weights
        assert pytest.approx(sum(weights.values()), rel=1e-12) == 1.0

    def test_missing_weight_column_raises(self):
        ce = _sample_ce_df().drop(columns=["FINLWT21"])
        with pytest.raises(ValueError, match="FINLWT21"):
            compute_fcsuti_weights_from_ce(ce)

    def test_missing_children_column_raises(self):
        ce = _sample_ce_df().drop(columns=["PERSLT18"])
        with pytest.raises(ValueError, match="PERSLT18"):
            compute_fcsuti_weights_from_ce(ce)

    def test_no_expenditure_columns_raises(self):
        ce = _sample_ce_df().drop(
            columns=[
                c
                for c in _sample_ce_df().columns
                if c not in {"PERSLT18", "FINLWT21"}
            ]
        )
        with pytest.raises(ValueError, match="FCSUti expenditure"):
            compute_fcsuti_weights_from_ce(ce)


class TestGetFcsutiCpiWeightsPlumbing:
    def test_static_fallback_emits_runtime_warning(self, monkeypatch):
        """With no ``weights`` argument, the static default is used and
        a ``RuntimeWarning`` surfaces in logs."""
        # Stub out the BLS fetch so the test doesn't touch the network.
        fake_series = pd.Series(
            {2020: 100.0, 2021: 105.0, 2022: 112.0}, name="stub"
        )
        monkeypatch.setattr(
            fcsuti_cpi,
            "fetch_bls_cpi_series",
            lambda series_id, start_year, end_year: fake_series,
        )
        # Clear the cache on the cached helper so our patched fetch is
        # actually invoked.
        fcsuti_cpi._cached_fcsuti_cpi.cache_clear()

        with warnings.catch_warnings(record=True) as records:
            warnings.simplefilter("always")
            cpi = get_fcsuti_cpi(
                start_year=2020, end_year=2022, base_year=2022
            )
        assert cpi[2022] == pytest.approx(100.0)
        messages = [
            str(r.message)
            for r in records
            if issubclass(r.category, RuntimeWarning)
        ]
        assert any(
            "static FCSUti weights" in m for m in messages
        ), f"Expected static-weights warning, got: {messages}"

    def test_explicit_weights_suppress_warning(self, monkeypatch):
        """Supplying ``weights`` explicitly is the opt-in path and
        should not warn."""
        fake_series = pd.Series(
            {2020: 100.0, 2021: 105.0, 2022: 112.0}, name="stub"
        )
        monkeypatch.setattr(
            fcsuti_cpi,
            "fetch_bls_cpi_series",
            lambda series_id, start_year, end_year: fake_series,
        )
        fcsuti_cpi._cached_fcsuti_cpi.cache_clear()

        with warnings.catch_warnings(record=True) as records:
            warnings.simplefilter("always")
            get_fcsuti_cpi(
                start_year=2020,
                end_year=2022,
                base_year=2022,
                weights={"food": 0.5, "shelter": 0.5},
            )
        static_warnings = [
            r for r in records if "static FCSUti weights" in str(r.message)
        ]
        assert static_warnings == []

    def test_empty_weights_raises(self):
        with pytest.raises(ValueError, match="empty"):
            get_fcsuti_cpi(weights={})

    def test_inflation_factor_threads_weights(self, monkeypatch):
        """get_fcsuti_inflation_factor must forward its ``weights`` arg."""
        captured = {}

        def _stub(start_year, end_year, base_year, weights=None):
            captured["weights"] = weights
            # Caller does fcsuti[to_year] / 100, so 2024 must be in the
            # index. Emit a window that covers start_year..end_year and
            # sets 2024 to 120 relative to base_year=100.
            idx = list(range(start_year, end_year + 1))
            values = {y: 100.0 for y in idx}
            values[2024] = 120.0
            return pd.Series(values)

        monkeypatch.setattr(fcsuti_cpi, "get_fcsuti_cpi", _stub)
        w = {"food": 1.0}
        result = get_fcsuti_inflation_factor(2022, 2024, weights=w)
        assert captured["weights"] == w
        assert result == pytest.approx(1.2)


class TestStaticWeightsShape:
    def test_defaults_sum_approximately_to_one(self):
        """The fallback dict is a rough approximation but the shares
        should still integrate to 1.0 to within normal rounding."""
        assert sum(FCSUTI_WEIGHTS.values()) == pytest.approx(1.0, abs=0.01)


class TestPrecomputedFactor:
    def test_returns_direct_pair(self):
        assert get_precomputed_fcsuti_factor(
            2023, 2024
        ) == PRECOMPUTED_FCSUTI_FACTORS[(2023, 2024)]

    def test_returns_none_when_missing(self):
        assert get_precomputed_fcsuti_factor(2001, 2099) is None


class TestDirectedPrecomputedFactor:
    def test_inverts_stored_reverse_pair(self):
        forward = PRECOMPUTED_FCSUTI_FACTORS[(2022, 2024)]
        assert _directed_precomputed_factor(2024, 2022) == pytest.approx(
            1.0 / forward
        )

    def test_same_year_returns_one(self):
        assert _directed_precomputed_factor(2020, 2020) == 1.0


class TestComposedFactor:
    def test_chains_through_pivot(self):
        """(2019, 2022) is not directly baked, but (2019, 2024) and
        (2022, 2024) are; composing inverts the second and multiplies."""
        direct_19_24 = PRECOMPUTED_FCSUTI_FACTORS[(2019, 2024)]
        direct_22_24 = PRECOMPUTED_FCSUTI_FACTORS[(2022, 2024)]
        expected = direct_19_24 * (1.0 / direct_22_24)
        assert _compose_precomputed_fcsuti_factor(
            2019, 2022
        ) == pytest.approx(expected)

    def test_returns_none_when_no_pivot_works(self):
        assert _compose_precomputed_fcsuti_factor(1985, 1990) is None


class TestInflationFactorOfflineFallback:
    def test_uses_precomputed_when_api_fails(self, monkeypatch):
        """With the BLS fetch stubbed to raise, the resolver should
        consult `PRECOMPUTED_FCSUTI_FACTORS` before the 4%/yr estimate."""
        import spm_calculator.fcsuti_cpi as mod

        mod.get_fcsuti_cpi.cache_clear()

        def fail_fetch(*args, **kwargs):
            raise RuntimeError("no network")

        monkeypatch.setattr(mod, "fetch_bls_cpi_series", fail_fetch)

        factor = get_fcsuti_inflation_factor(2023, 2024)
        assert factor == pytest.approx(
            PRECOMPUTED_FCSUTI_FACTORS[(2023, 2024)]
        )

    def test_uses_composition_when_direct_not_available(self, monkeypatch):
        """Without an exact direct pair, composition through 2024 is
        used before the 4%/yr estimate."""
        import spm_calculator.fcsuti_cpi as mod

        mod.get_fcsuti_cpi.cache_clear()

        def fail_fetch(*args, **kwargs):
            raise RuntimeError("no network")

        monkeypatch.setattr(mod, "fetch_bls_cpi_series", fail_fetch)

        factor = get_fcsuti_inflation_factor(2019, 2022)
        composed = PRECOMPUTED_FCSUTI_FACTORS[
            (2019, 2024)
        ] * (1.0 / PRECOMPUTED_FCSUTI_FACTORS[(2022, 2024)])
        assert factor == pytest.approx(composed)

    def test_falls_back_to_4pct_when_nothing_precomputed_matches(
        self, monkeypatch
    ):
        """For year pairs outside the precomputed universe, the 4%/yr
        estimate is the last resort (and emits a RuntimeWarning)."""
        import warnings

        import spm_calculator.fcsuti_cpi as mod

        mod.get_fcsuti_cpi.cache_clear()
        monkeypatch.setattr(
            mod,
            "fetch_bls_cpi_series",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("x")),
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            factor = get_fcsuti_inflation_factor(1985, 1990)
        assert factor == pytest.approx(1.04**5)
        assert any("4%/yr" in str(w.message) for w in caught)

    def test_same_year_returns_identity(self):
        assert get_fcsuti_inflation_factor(2024, 2024) == 1.0


class TestRegistrationKey:
    def test_fetch_passes_registration_key_when_provided(self, monkeypatch):
        """When a registrationkey is supplied, it must be part of the
        POST payload. Without one, callers are capped at 25 BLS queries
        per IP per day (which is four `get_fcsuti_cpi` calls)."""
        import requests

        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "status": "REQUEST_SUCCEEDED",
                    "Results": {
                        "series": [
                            {
                                "data": [
                                    {
                                        "year": "2024",
                                        "period": "M13",
                                        "value": "100.0",
                                    }
                                ]
                            }
                        ]
                    },
                }

        def fake_post(url, json=None, timeout=None):
            captured["json"] = json
            return FakeResponse()

        monkeypatch.setattr(requests, "post", fake_post)
        fetch_bls_cpi_series(
            "CUUR0000SAF", 2023, 2024, registration_key="abc123"
        )
        assert captured["json"]["registrationkey"] == "abc123"

    def test_fetch_reads_registration_key_from_env(self, monkeypatch):
        """If no explicit key is passed, BLS_API_KEY is picked up from
        the environment so CI runners can register silently."""
        import requests

        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "status": "REQUEST_SUCCEEDED",
                    "Results": {
                        "series": [
                            {
                                "data": [
                                    {
                                        "year": "2024",
                                        "period": "M13",
                                        "value": "100.0",
                                    }
                                ]
                            }
                        ]
                    },
                }

        def fake_post(url, json=None, timeout=None):
            captured["json"] = json
            return FakeResponse()

        monkeypatch.setenv("BLS_API_KEY", "env-key")
        monkeypatch.setattr(requests, "post", fake_post)
        fetch_bls_cpi_series("CUUR0000SAF", 2023, 2024)
        assert captured["json"]["registrationkey"] == "env-key"

    def test_fetch_omits_registration_key_when_absent(self, monkeypatch):
        """No key, no `registrationkey` field (so we don't send an
        empty string that some clients might reject)."""
        import requests

        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "status": "REQUEST_SUCCEEDED",
                    "Results": {
                        "series": [
                            {
                                "data": [
                                    {
                                        "year": "2024",
                                        "period": "M13",
                                        "value": "100.0",
                                    }
                                ]
                            }
                        ]
                    },
                }

        def fake_post(url, json=None, timeout=None):
            captured["json"] = json
            return FakeResponse()

        monkeypatch.delenv("BLS_API_KEY", raising=False)
        monkeypatch.setattr(requests, "post", fake_post)
        fetch_bls_cpi_series("CUUR0000SAF", 2023, 2024)
        assert "registrationkey" not in captured["json"]
