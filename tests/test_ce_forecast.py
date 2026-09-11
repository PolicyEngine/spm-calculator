"""Synthetic scientific contracts for the CE rolling-window scenarios."""

import copy
import hashlib
import json
import math
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import spm_calculator.ce_forecast as ce_forecast
from spm_calculator.ce_forecast import (
    _fit_statistics,
    build_ce_forecast,
    ce_housing_shares,
    corrected_published_thresholds,
    evaluate_ce_backtest,
    extend_cpi_series,
    fit_real_growth,
    forecast_from_frames,
    load_observed_ce,
    project_ce_window,
)
from spm_calculator.ce_threshold import (
    TENURES,
    bls_quarter_window,
    calculate_fcsuti,
    estimate_thresholds,
    normalize_ce_sample,
    replicate_thresholds,
)
from spm_calculator.fcsuti_cpi import (
    CPI_SERIES,
    compute_fcsuti_weights_from_ce,
    get_fcsuti_inflation_factor,
)

MONETARY = tuple(
    f"{name}{suffix}"
    for name in (
        "FOOD",
        "FDHOME",
        "FDAWAY",
        "GROCER",
        "APPAR",
        "SHELT",
        "UTIL",
        "TELEPH",
    )
    for suffix in ("PQ", "CQ")
) + ("EMRTPNOP", "EMRTPNOC", "MRTPRNOP", "MRTPRNOC")
SHARE_ANCHOR = dict(zip(TENURES, (0.443, 0.434, 0.323)))


def prices(start=2014, end=2030, annual_rate=0.0):
    """Equal component inflation; each series has an independent base."""
    return {
        sid: pd.Series(
            {
                year: (100.0 + position * 50.0)
                * (1 + annual_rate) ** (year - start)
                for year in range(start, end + 1)
            }
        )
        for position, sid in enumerate(CPI_SERIES.values())
    }


def quarter_frame(year, quarter, *, scale=1.0, shelter=70.0):
    """Same 36 families each season, spanning all three estimator tenures."""
    size = 36
    spending = np.repeat(np.linspace(0.55, 1.45, 12), 3) * scale
    frame = pd.DataFrame(
        {
            "NEWID": np.arange(size) + 10000 * year + 100 * quarter,
            "AGE_REF": [40] * size,
            "PERSLT18": [2] * size,
            "FAM_SIZE": [4] * size,
            "CUTENURE": [4, 1, 2] * 12,
            "FINLWT21": [1.0, 2.0, 3.0] * 12,
            "ce_year": [year] * size,
            "ce_quarter": [quarter] * size,
            "UNRELATED_NUMERIC": np.arange(size) + 7.0,
            **{
                f"{name}{suffix}": spending * value
                for name, value in (
                    ("FOOD", 100.0),
                    ("APPAR", 10.0),
                    ("SHELT", shelter),
                    ("UTIL", 20.0),
                    ("TELEPH", 5.0),
                )
                for suffix in ("PQ", "CQ")
            },
            **{
                name: spending * np.tile([0.0, 2.0, 0.0], 12)
                for name in (
                    "EMRTPNOP",
                    "EMRTPNOC",
                    "MRTPRNOP",
                    "MRTPRNOC",
                )
            },
        }
    )
    frame.attrs["source"] = {
        "bundle_path": f"/synthetic/cache/intrvw{(year if quarter > 1 else year - 1) % 100:02d}.zip",
        "member": f"fmli{year % 100:02d}{quarter}.csv",
        "url": "https://example.test/synthetic.zip",
    }
    return frame


def observed_frames(
    start_block=2015,
    end_block=2025,
    *,
    real_log_rate=0.0,
    inflation_rate=0.0,
    changing_housing=False,
):
    frames = {}
    for end_year in range(start_block, end_block + 1):
        for year, quarter in (
            (end_year - 1, 2),
            (end_year - 1, 3),
            (end_year - 1, 4),
            (end_year, 1),
        ):
            frames[year, quarter] = quarter_frame(
                year,
                quarter,
                scale=math.exp(real_log_rate * (end_year - 2025))
                * (1 + inflation_rate) ** (year - 2014),
                shelter=(
                    40.0 + 6.0 * (end_year - start_block)
                    if changing_housing
                    else 70.0
                ),
            )
    return frames


def origin_weights(frames, origin=2025):
    raw = pd.concat([frames[key] for key in bls_quarter_window(origin)])
    return compute_fcsuti_weights_from_ce(raw)


def published_values():
    return {
        year: {
            tenure: (30000.0 + position * 2500.0)
            * (1.02 + 0.01 * position) ** (year - 2019)
            for position, tenure in enumerate(TENURES)
        }
        for year in range(2019, 2026)
    }


@pytest.mark.parametrize(
    "year,start,end,observed,projected",
    [
        (2024, "2019Q2", "2024Q1", 20, 0),
        (2025, "2020Q2", "2025Q1", 20, 0),
        (2026, "2021Q2", "2026Q1", 16, 4),
        (2027, "2022Q2", "2027Q1", 12, 8),
        (2028, "2023Q2", "2028Q1", 8, 12),
        (2029, "2024Q2", "2029Q1", 4, 16),
        (2030, "2025Q2", "2030Q1", 0, 20),
    ],
)
def test_reference_year_windows_and_counts(
    year, start, end, observed, projected
):
    frames = observed_frames()
    frame, metadata = project_ce_window(
        frames,
        origin_year=2025,
        target_year=year,
        cpi_series=prices(),
        origin_weights=origin_weights(frames),
    )
    assert metadata["window"] == {
        "start": start,
        "end": end,
        "observed_quarters": observed,
        "projected_quarters": projected,
    }
    actual = list(
        frame[["ce_year", "ce_quarter"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    assert actual == bls_quarter_window(year)
    assert len(frame) == 20 * 36


def test_direct_same_season_donors_scale_only_expenditure_fields():
    frames = observed_frames()
    donor = frames[2024, 2]
    # Mixed food schemas and missing principal entries must survive cloning.
    for name in ("FDHOME", "FDAWAY", "GROCER"):
        for suffix in ("PQ", "CQ"):
            donor[f"{name}{suffix}"] = np.arange(len(donor), dtype=float)
            donor.loc[0, f"{name}{suffix}"] = np.nan
    donor.loc[1, "EMRTPNOP"] = np.nan
    before = {key: value.copy(deep=True) for key, value in frames.items()}
    frame, metadata = project_ce_window(
        frames,
        origin_year=2025,
        target_year=2030,
        cpi_series=prices(annual_rate=0.04),
        origin_weights={"food": 0.4, "shelter": 0.6},
        real_log_rate=math.log(1.02),
    )
    for target_year in range(2025, 2030):
        target = frame.loc[
            (frame.ce_year == target_year) & (frame.ce_quarter == 2)
        ].reset_index(drop=True)
        factor = (1.04 * 1.02) ** (target_year - 2024)
        for column in donor:
            if column in ("ce_year", "ce_quarter"):
                continue
            expected = (
                donor[column] * factor if column in MONETARY else donor[column]
            )
            pd.testing.assert_series_equal(
                target[column],
                expected.reset_index(drop=True),
                check_names=False,
            )
        # Original IDs recur rather than becoming independent CU interviews.
        assert target.NEWID.tolist() == donor.NEWID.tolist()
    assert len(metadata["donor_quarters"]) == 20
    final = metadata["donor_quarters"][-1]
    assert final["target"] == "2030Q1"
    assert final["donor"] == "2025Q1"
    assert final["rows"] == len(frames[2025, 1])
    assert final["source"]["bundle_path"] == "intrvw24.zip"
    for year, quarter in ((2025, 2), (2029, 2), (2030, 1)):
        projected = frame.loc[
            (frame.ce_year == year) & (frame.ce_quarter == quarter)
        ]
        donor_year = 2025 if quarter == 1 else 2024
        assert projected.ce_donor_year.tolist() == [donor_year] * 36
        assert projected.ce_donor_quarter.tolist() == [quarter] * 36
        assert projected.ce_donor_row_position.tolist() == list(range(36))
    for key in frames:
        pd.testing.assert_frame_equal(frames[key], before[key])


def test_historical_gap_is_an_error_not_a_projected_observation():
    frames = observed_frames()
    del frames[2022, 3]
    with pytest.raises(ValueError, match="[Mm]issing|[Gg]ap"):
        project_ce_window(
            frames,
            origin_year=2025,
            target_year=2026,
            cpi_series=prices(),
            origin_weights={"food": 1.0},
        )


def test_future_observations_cannot_become_donors_or_growth_inputs():
    frames = observed_frames()
    contaminated = dict(frames)
    contaminated[2025, 2] = quarter_frame(2025, 2, scale=1000)
    contaminated[2026, 1] = quarter_frame(2026, 1, scale=1000000)
    options = {
        "origin_year": 2025,
        "cpi_series": prices(),
        "origin_weights": origin_weights(frames),
    }
    expected, expected_metadata = project_ce_window(
        frames, target_year=2030, **options
    )
    actual, actual_metadata = project_ce_window(
        contaminated, target_year=2030, **options
    )
    pd.testing.assert_frame_equal(actual, expected)
    assert actual_metadata == expected_metadata
    assert fit_real_growth(contaminated, **options) == fit_real_growth(
        frames, **options
    )


def test_extend_prices_preserves_observed_values_and_does_not_mutate():
    observed = prices(end=2025, annual_rate=0.03)
    before = copy.deepcopy(observed)
    rates = {2026: 0.023, 2027: 0.022, 2028: 0.02, 2029: 0.02, 2030: 0.02}
    actual = extend_cpi_series(
        observed, observed_end_year=2025, end_year=2030, inflation_rates=rates
    )
    for sid in observed:
        pd.testing.assert_series_equal(observed[sid], before[sid])
        pd.testing.assert_series_equal(actual[sid].loc[:2025], observed[sid])
        for year, rate in rates.items():
            assert actual[sid][year] == pytest.approx(
                actual[sid][year - 1] * (1 + rate)
            )


@pytest.mark.parametrize("bad_rate", [float("nan"), float("inf"), -1.0])
def test_invalid_future_prices_fail(bad_rate):
    with pytest.raises(ValueError):
        extend_cpi_series(
            prices(end=2025),
            end_year=2026,
            inflation_rates={2026: bad_rate},
        )


def test_housing_share_uses_median_multiplier_and_rejects_invalid_values():
    replication = {
        "thresholds": dict.fromkeys(TENURES, 100.0),
        "estimation": {
            "median_share": 0.82,
            "tenures": {tenure: {"su_mean": 50.0} for tenure in TENURES},
        },
    }
    assert ce_housing_shares(replication) == dict.fromkeys(TENURES, 0.41)
    for invalid in (0.0, -1.0, float("nan"), float("inf")):
        broken = copy.deepcopy(replication)
        broken["thresholds"][TENURES[0]] = invalid
        with pytest.raises(ValueError):
            ce_housing_shares(broken)
    for invalid in (0.0, -1.0, 1000.0, float("nan"), float("inf")):
        broken = copy.deepcopy(replication)
        broken["estimation"]["tenures"][TENURES[0]]["su_mean"] = invalid
        with pytest.raises(ValueError):
            ce_housing_shares(broken)


@pytest.mark.parametrize("slope", [math.log(1.06), math.log(0.94), 0.0])
def test_real_growth_fits_nonoverlapping_blocks_in_common_prices(slope):
    frames = observed_frames(real_log_rate=slope, inflation_rate=0.04)
    result = fit_real_growth(
        frames,
        origin_year=2025,
        cpi_series=prices(annual_rate=0.04),
        origin_weights=origin_weights(frames),
    )
    assert result["n"] == 5
    assert result["annual_log_slope"] == pytest.approx(slope, abs=1e-12)
    assert result["shrinkage"] == 0.5
    assert result["annual_rate"] == pytest.approx(math.expm1(slope * 0.5))
    assert result["unshrunk_annual_rate"] == pytest.approx(math.expm1(slope))
    assert result["OLS_slope_standard_error"] == pytest.approx(0, abs=1e-12)
    assert [block["end_year"] for block in result["annual_blocks"]] == list(
        range(2021, 2026)
    )
    for key, expected_n in (
        ("latest_ten_blocks", 10),
        ("pandemic_excluded", 3),
    ):
        fit = result["sensitivities"][key]
        assert fit["n"] == expected_n
        assert fit["annual_log_slope"] == pytest.approx(slope, abs=1e-12)
        assert fit["annual_rate"] == pytest.approx(math.expm1(slope * 0.5))
        assert fit["OLS_slope_standard_error"] == pytest.approx(0, abs=1e-12)
        assert fit["unshrunk_annual_rate"] == pytest.approx(math.expm1(slope))
        assert len(fit["annual_blocks"]) == expected_n
    excluded = result["sensitivities"]["pandemic_excluded"]["annual_blocks"]
    assert [block["end_year"] for block in excluded] == [2023, 2024, 2025]


def test_growth_shrinkage_is_configurable_without_silently_clipping():
    frames = observed_frames(real_log_rate=-0.04)
    result = fit_real_growth(
        frames,
        origin_year=2025,
        cpi_series=prices(),
        origin_weights=origin_weights(frames),
        shrinkage=0.25,
    )
    assert result["annual_log_slope"] == pytest.approx(-0.04)
    assert result["annual_rate"] == pytest.approx(math.expm1(-0.01))


def test_growth_requires_all_five_blocks_and_historical_prices():
    frames = observed_frames(start_block=2021)
    options = {
        "origin_year": 2025,
        "origin_weights": origin_weights(frames),
    }
    incomplete_prices = prices(start=2021)
    with pytest.raises(ValueError, match="[Mm]issing|[Cc]over|[Hh]istor"):
        fit_real_growth(frames, cpi_series=incomplete_prices, **options)
    del frames[2020, 2]
    with pytest.raises(ValueError, match="[Mm]issing|[Gg]ap|[Ff]ive"):
        fit_real_growth(frames, cpi_series=prices(), **options)


def test_unavailable_sensitivities_are_explicit():
    frames = observed_frames(start_block=2018, end_block=2022)
    result = fit_real_growth(
        frames,
        origin_year=2022,
        cpi_series=prices(),
        origin_weights=origin_weights(frames, 2022),
    )
    ten = result["sensitivities"]["latest_ten_blocks"]
    assert ten["status"] == "unavailable"
    assert ten["annual_rate"] is None
    assert ten["reason"]


def test_complete_forecast_keeps_separate_exact_anchors_and_rolls_at_zero_real():
    frames = observed_frames(changing_housing=True, real_log_rate=0.025)
    published = published_values()
    result = forecast_from_frames(
        frames,
        cpi_series=prices(),
        published_thresholds=published,
        housing_share_anchor=SHARE_ANCHOR,
        include_backtest=False,
    )
    json.dumps(result, allow_nan=False)
    assert result["default_scenario"] == "ce_trend"
    assert result["backtest"]["status"] == "not_run"
    assert result["backtest"]["unvalidated"] is True
    for scenario in ("zero_real", "ce_trend"):
        years = result["scenarios"][scenario]["years"]
        assert years["2024"]["thresholds"] == published[2024]
        assert years["2025"]["thresholds"] == published[2025]
        assert years["2024"]["housing_shares"] == SHARE_ANCHOR
        for year in range(2024, 2031):
            for tenure in TENURES:
                value = years[str(year)]["housing_shares"][tenure]
                assert math.isfinite(value) and 0 < value < 1
        target = years["2026"]
        for tenure in TENURES:
            assert target["thresholds"][tenure] == pytest.approx(
                published[2025][tenure]
                * target["replication"]["thresholds"][tenure]
                / years["2025"]["replication"]["thresholds"][tenure]
            )
            assert target["housing_shares"][tenure] == pytest.approx(
                SHARE_ANCHOR[tenure]
                * ce_housing_shares(target["replication"])[tenure]
                / ce_housing_shares(years["2024"]["replication"])[tenure]
            )
    zero = result["scenarios"]["zero_real"]["years"]
    assert zero["2026"]["thresholds"] != zero["2025"]["thresholds"]
    assert zero["2026"]["housing_shares"] != zero["2025"]["housing_shares"]


def test_uniform_price_and_real_scaling_has_no_double_inflation():
    frames = observed_frames()
    raw, _ = project_ce_window(
        frames,
        origin_year=2025,
        target_year=2030,
        cpi_series=prices(annual_rate=0.04),
        origin_weights=origin_weights(frames),
        real_log_rate=math.log(1.02),
    )
    # Inspect one donor season: donor price -> collection year, then only
    # collection year -> threshold year. Three Q2 records stay proportional.
    target = raw.loc[(raw.ce_year == 2027) & (raw.ce_quarter == 2)]
    donor = frames[2024, 2]
    baseline = replicate_thresholds(donor, 2024, cpi_series=prices())
    actual = replicate_thresholds(
        target, 2030, cpi_series=prices(annual_rate=0.04)
    )
    expected_factor = 1.04 ** (2030 - 2024) * 1.02 ** (2027 - 2024)
    for tenure in TENURES:
        assert actual["thresholds"][tenure] == pytest.approx(
            baseline["thresholds"][tenure] * expected_factor
        )
        assert ce_housing_shares(actual)[tenure] == pytest.approx(
            ce_housing_shares(baseline)[tenure]
        )


def test_donor_price_bridge_is_ratio_of_one_origin_anchored_price_index():
    frames = observed_frames()
    cpi = prices()
    # With different component paths, weighted factors cannot be freely
    # chained/rebased. Freeze the historical bridge at the origin weights.
    cpi[CPI_SERIES["food"]].loc[[2024, 2025, 2026]] = [100, 110, 154]
    cpi[CPI_SERIES["shelter"]].loc[[2024, 2025, 2026]] = [100, 130, 143]
    weights = {"food": 0.5, "shelter": 0.5}
    frame, metadata = project_ce_window(
        frames,
        origin_year=2025,
        target_year=2026,
        cpi_series=cpi,
        origin_weights=weights,
    )
    bridge = get_fcsuti_inflation_factor(
        2024, 2025, weights=weights, cpi_series=cpi
    )
    future = get_fcsuti_inflation_factor(
        2025, 2026, weights=weights, cpi_series=cpi
    )
    assert bridge == pytest.approx(1.2)
    assert future == pytest.approx(1.25)
    # A Q1 donor is observed in 2025, while Q2's donor is observed in 2024.
    q1 = frame.loc[(frame.ce_year == 2026) & (frame.ce_quarter == 1)]
    np.testing.assert_allclose(
        q1.FOODPQ.to_numpy(), frames[2025, 1].FOODPQ.to_numpy() * future
    )
    q2 = frame.loc[(frame.ce_year == 2025) & (frame.ce_quarter == 2)]
    np.testing.assert_allclose(
        q2.FOODPQ.to_numpy(), frames[2024, 2].FOODPQ.to_numpy() * bridge
    )
    _, next_metadata = project_ce_window(
        frames,
        origin_year=2025,
        target_year=2027,
        cpi_series=cpi,
        origin_weights=weights,
    )
    target = next(
        quarter
        for quarter in next_metadata["donor_quarters"]
        if quarter["target"] == "2026Q2"
    )
    assert target["nominal_price_factor"] == pytest.approx(bridge * future)
    assert target["nominal_price_factor"] != pytest.approx(
        get_fcsuti_inflation_factor(
            2024, 2026, weights=weights, cpi_series=cpi
        )
    )


def test_forecast_source_identity_does_not_depend_on_cache_directory():
    frames = observed_frames()
    relocated = copy.deepcopy(frames)
    for frame in relocated.values():
        frame.attrs["source"]["bundle_path"] = frame.attrs["source"][
            "bundle_path"
        ].replace("/synthetic/cache", "/different/machine/cache")
    options = {
        "cpi_series": prices(),
        "published_thresholds": published_values(),
        "housing_share_anchor": SHARE_ANCHOR,
        "end_year": 2026,
        "include_backtest": False,
        "information_date": "2026-09-09",
    }
    first = forecast_from_frames(frames, **options)
    second = forecast_from_frames(relocated, **options)
    assert json.dumps(first, sort_keys=True, allow_nan=False) == json.dumps(
        second, sort_keys=True, allow_nan=False
    )


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, float("nan"), float("inf")])
def test_invalid_share_anchor_cannot_be_shipped(bad):
    anchor = dict(SHARE_ANCHOR)
    anchor[TENURES[0]] = bad
    with pytest.raises(ValueError):
        forecast_from_frames(
            observed_frames(),
            cpi_series=prices(),
            published_thresholds=published_values(),
            housing_share_anchor=anchor,
            include_backtest=False,
            end_year=2026,
        )


def test_ten_block_sensitivity_uses_origin_five_block_cpi_weights():
    frames = observed_frames(changing_housing=True)
    cpi = prices(annual_rate=0.02)
    for component, annual_rate in (("food", 0.01), ("shelter", 0.08)):
        cpi[CPI_SERIES[component]] = pd.Series(
            {
                year: 100.0 * (1 + annual_rate) ** (year - 2014)
                for year in range(2014, 2031)
            }
        )
    weights = origin_weights(frames)
    means = []
    for end_year in range(2016, 2026):
        keys = [(end_year - 1, quarter) for quarter in (2, 3, 4)] + [
            (end_year, 1)
        ]
        raw = pd.concat([frames[key] for key in keys], ignore_index=True)
        normalized, _ = normalize_ce_sample(raw)
        normalized["fcsuti_2a2c"] = calculate_fcsuti(normalized) * raw[
            "ce_year"
        ].map(
            {
                year: get_fcsuti_inflation_factor(
                    year, 2025, weights=weights, cpi_series=cpi
                )
                for year in raw.ce_year.unique()
            }
        )
        normalized["su_2a2c"] = 0.0
        normalized["ce_weight"] = normalized.FINLWT21
        _, estimation = estimate_thresholds(normalized)
        means.append(estimation["fcsuti_mean"])
    expected_slope = np.polyfit(range(2016, 2026), np.log(means), 1)[0]
    result = fit_real_growth(
        frames,
        origin_year=2025,
        cpi_series=cpi,
        origin_weights=weights,
    )["sensitivities"]["latest_ten_blocks"]
    assert [block["fcsuti_mean"] for block in result["annual_blocks"]] == (
        pytest.approx(means)
    )
    assert result["annual_log_slope"] == pytest.approx(expected_slope)


@pytest.fixture(scope="module")
def static_backtest():
    frames = observed_frames()
    cpi = prices(end=2025)
    # Components are flat but the independent all-items comparator grows.
    cpi[CPI_SERIES["all_items"]] = pd.Series(
        {year: 100 * 1.07 ** (year - 2014) for year in range(2014, 2026)}
    )
    published = published_values()
    result = evaluate_ce_backtest(
        frames, cpi_series=cpi, published_thresholds=published
    )
    return frames, cpi, published, result


def test_backtest_has_identical_complete_multihorizon_fold_coverage(
    static_backtest,
):
    _, _, _, result = static_backtest
    assert result["status"] == "complete"
    assert result["unvalidated"] is False
    assert result["fold_count"] == 21
    assert result["fold_tenure_observation_count"] == 63
    assert len(result["folds"]) == 21
    expected = {
        (origin, target)
        for origin in range(2019, 2025)
        for target in range(origin + 1, min(origin + 6, 2025) + 1)
    }
    assert {
        (fold["origin_year"], fold["target_year"]) for fold in result["folds"]
    } == expected
    for horizon in range(1, 7):
        assert result["by_horizon"][str(horizon)]["fold_count"] == 7 - horizon
    for fold in result["folds"]:
        assert fold["horizon"] == fold["target_year"] - fold["origin_year"]
        assert set(fold["scenarios"]) == {"zero_real", "ce_trend"}
        assert fold["scenarios"]["ce_trend"]["shrinkage"] == 0.5
        for scenario in fold["scenarios"].values():
            assert set(scenario["thresholds"]) == set(TENURES)
            assert set(scenario["errors_by_tenure"]) == set(TENURES)


def test_backtest_predictions_use_origin_anchor_and_all_items_comparator(
    static_backtest,
):
    _, _, published, result = static_backtest
    for fold in result["folds"]:
        origin = fold["origin_year"]
        target = fold["target_year"]
        horizon = target - origin
        for tenure in TENURES:
            baseline = published[origin][tenure] * 1.07**horizon
            assert fold["baseline"]["thresholds"][tenure] == pytest.approx(
                baseline
            )
            for scenario in fold["scenarios"].values():
                # Fixed nominal CE distributions and component prices imply
                # no rolling estimate change even as official anchors rise.
                assert scenario["thresholds"][tenure] == pytest.approx(
                    published[origin][tenure]
                )
                signed = 100 * (
                    published[origin][tenure] / published[target][tenure] - 1
                )
                assert scenario["errors_by_tenure"][tenure][
                    "percentage_error"
                ] == (pytest.approx(signed))
                assert scenario["errors_by_tenure"][tenure][
                    "absolute_percentage_error"
                ] == (pytest.approx(abs(signed)))


def test_backtest_metrics_are_equal_tenure_and_horizon_balanced_means(
    static_backtest,
):
    _, _, published, result = static_backtest
    by_horizon = {horizon: [] for horizon in range(1, 7)}
    baseline_by_horizon = {horizon: [] for horizon in range(1, 7)}
    signed_errors = []
    baseline_errors = []
    for origin in range(2019, 2025):
        for target in range(origin + 1, 2026):
            horizon = target - origin
            for tenure in TENURES:
                signed = 100 * (
                    published[origin][tenure] / published[target][tenure] - 1
                )
                baseline = 100 * (
                    published[origin][tenure]
                    * 1.07**horizon
                    / published[target][tenure]
                    - 1
                )
                signed_errors.append(signed)
                baseline_errors.append(abs(baseline))
                by_horizon[horizon].append(abs(signed))
                baseline_by_horizon[horizon].append(abs(baseline))
    expected = float(np.mean(np.abs(signed_errors)))
    baseline = float(np.mean(baseline_errors))
    balanced = float(np.mean([np.mean(by_horizon[h]) for h in range(1, 6)]))
    baseline_balanced = float(
        np.mean([np.mean(baseline_by_horizon[h]) for h in range(1, 6)])
    )
    assert balanced != pytest.approx(expected)
    assert result["baseline"][
        "mean_absolute_percentage_error"
    ] == pytest.approx(baseline)
    assert result["baseline"][
        "horizon_balanced_mean_absolute_percentage_error"
    ] == (pytest.approx(baseline_balanced))
    for identifier in ("zero_real", "ce_trend"):
        metrics = result["scenarios"][identifier]
        assert metrics["mean_absolute_percentage_error"] == pytest.approx(
            expected
        )
        assert metrics["median_absolute_percentage_error"] == pytest.approx(
            np.median(np.abs(signed_errors))
        )
        assert metrics["mean_percentage_error"] == pytest.approx(
            np.mean(signed_errors)
        )
        assert metrics[
            "horizon_balanced_mean_absolute_percentage_error"
        ] == pytest.approx(balanced)
        assert metrics["beats_baseline"] is (expected < baseline)
        assert metrics["beats_horizon_balanced_baseline"] is (
            balanced < baseline_balanced
        )
        for horizon in range(1, 7):
            row = result["by_horizon"][str(horizon)]
            candidate_score = float(np.mean(by_horizon[horizon]))
            comparator_score = float(np.mean(baseline_by_horizon[horizon]))
            assert row["scenarios"][identifier][
                "mean_absolute_percentage_error"
            ] == (pytest.approx(candidate_score))
            assert row["baseline"]["mean_absolute_percentage_error"] == (
                pytest.approx(comparator_score)
            )
            assert row["scenarios"][identifier]["beats_baseline"] is (
                candidate_score < comparator_score
            )


@pytest.mark.parametrize("missing", ["published", "quarter", "price"])
def test_missing_required_backtest_data_raises_instead_of_partial_results(
    missing,
):
    frames = observed_frames()
    cpi = prices(end=2025)
    published = published_values()
    if missing == "published":
        del published[2022]
    elif missing == "quarter":
        del frames[2014, 2]
    else:
        cpi[CPI_SERIES["all_items"]] = cpi[CPI_SERIES["all_items"]].drop(2022)
    with pytest.raises(ValueError):
        evaluate_ce_backtest(
            frames, cpi_series=cpi, published_thresholds=published
        )


def test_equal_backtest_scores_do_not_count_as_beating_baseline():
    published = {
        year: dict.fromkeys(TENURES, 30000.0) for year in range(2019, 2026)
    }
    result = evaluate_ce_backtest(
        observed_frames(),
        cpi_series=prices(end=2025),
        published_thresholds=published,
    )
    for scenario in result["scenarios"].values():
        assert scenario["mean_absolute_percentage_error"] == pytest.approx(0)
        assert scenario["beats_baseline"] is False
        assert scenario["beats_horizon_balanced_baseline"] is False
    for horizon in result["by_horizon"].values():
        for scenario in horizon["scenarios"].values():
            assert scenario["beats_baseline"] is False


def test_scored_trend_uses_half_slope_and_never_uses_later_ce_observations():
    frames = observed_frames(real_log_rate=0.04)
    cpi = prices(end=2025)
    published = published_values()
    result = evaluate_ce_backtest(
        frames, cpi_series=cpi, published_thresholds=published
    )
    fold = next(
        fold
        for fold in result["folds"]
        if (fold["origin_year"], fold["target_year"]) == (2019, 2025)
    )
    weights = origin_weights(frames, 2019)
    base_raw, _ = project_ce_window(
        frames,
        origin_year=2019,
        target_year=2019,
        cpi_series=cpi,
        origin_weights=weights,
    )
    target_raw, _ = project_ce_window(
        frames,
        origin_year=2019,
        target_year=2025,
        cpi_series=cpi,
        origin_weights=weights,
        real_log_rate=0.02,
    )
    base = replicate_thresholds(base_raw, 2019, cpi_series=cpi)
    target = replicate_thresholds(target_raw, 2025, cpi_series=cpi)
    for tenure in TENURES:
        assert fold["scenarios"]["ce_trend"]["thresholds"][tenure] == (
            pytest.approx(
                published[2019][tenure]
                * target["thresholds"][tenure]
                / base["thresholds"][tenure]
            )
        )
    contaminated = copy.deepcopy(frames)
    for key, frame in contaminated.items():
        if key > (2019, 1):
            for column in frame.columns.intersection(MONETARY):
                frame[column] *= 2.0
    rerun = evaluate_ce_backtest(
        contaminated, cpi_series=cpi, published_thresholds=published
    )
    expected = [
        fold for fold in result["folds"] if fold["origin_year"] == 2019
    ]
    actual = [fold for fold in rerun["folds"] if fold["origin_year"] == 2019]
    assert actual == expected


@pytest.mark.parametrize("end_years", [[2024, 2025], [2025, 2025, 2025]])
def test_unavailable_fit_diagnostics_for_small_or_singular_samples(end_years):
    fit = _fit_statistics(
        [{"end_year": year, "fcsuti_mean": 100.0} for year in end_years],
        shrinkage=0.5,
    )
    assert fit["status"] == "unavailable"
    assert fit["n"] == len(end_years)
    assert fit["reason"]
    for field in (
        "annual_log_slope",
        "OLS_slope_standard_error",
        "unshrunk_annual_rate",
        "annual_rate",
    ):
        assert fit[field] is None


def test_projected_rows_cannot_masquerade_as_observed_donors():
    frames = observed_frames()
    frames[2025, 1]["ce_is_projected"] = True
    with pytest.raises(ValueError, match="[Pp]rojected.*[Dd]onor"):
        project_ce_window(
            frames,
            origin_year=2025,
            target_year=2026,
            cpi_series=prices(),
            origin_weights={"food": 1.0},
        )


def test_release_builder_cannot_skip_required_backtest(tmp_path):
    with pytest.raises(ValueError, match="[Bb]acktest|[Vv]alidation"):
        build_ce_forecast(
            cache_dir=tmp_path,
            cpi_path=tmp_path / "not-read.json",
            published_thresholds=published_values(),
            housing_share_anchor=SHARE_ANCHOR,
            inflation_rates={year: 0.02 for year in range(2026, 2031)},
            include_backtest=False,
        )


def test_release_builder_rejects_2019_published_instead_of_revised(tmp_path):
    document = json.loads(
        (
            Path(__file__).resolve().parent.parent
            / "spm_calculator/data/bls/threshold_series.json"
        ).read_text()
    )
    old = document["series"]["bls-corrected-2026-07-17"]["segments"][
        "published_2005_2019"
    ]["years"]["2019"]
    published = corrected_published_thresholds()
    wrong = {tenure: old[tenure]["threshold"] for tenure in TENURES}
    assert wrong != published[2019]
    published[2019] = wrong
    with pytest.raises(ValueError, match="2019 Revised"):
        build_ce_forecast(
            cache_dir=tmp_path,
            cpi_path=tmp_path / "not-read.json",
            published_thresholds=published,
            housing_share_anchor=SHARE_ANCHOR,
            inflation_rates={year: 0.02 for year in range(2026, 2031)},
        )


def write_synthetic_cache(cache, *, alternate_2024_q1=False):
    """Small actual CSV/ZIP inputs exercise the existing offline reader."""
    cache.mkdir()
    for bundle_year in range(2014, 2025):
        path = cache / f"intrvw{bundle_year % 100:02d}.zip"
        keys = [(bundle_year, quarter) for quarter in (2, 3, 4)] + [
            (bundle_year + 1, 1)
        ]
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for year, quarter in keys:
                if alternate_2024_q1 and (year, quarter) == (2024, 1):
                    continue
                member = f"intrvw{bundle_year % 100:02d}/fmli{year % 100:02d}{quarter}.csv"
                archive.writestr(
                    member, quarter_frame(year, quarter).to_csv(index=False)
                )
            if alternate_2024_q1 and bundle_year == 2024:
                archive.writestr(
                    "intrvw24/fmli241x.csv",
                    quarter_frame(2024, 1).to_csv(index=False),
                )


def test_offline_cache_provenance_survives_relocation_and_hashes_bundles_once(
    tmp_path, monkeypatch
):
    first_cache = tmp_path / "original"
    second_cache = tmp_path / "relocated"
    write_synthetic_cache(first_cache)
    shutil.copytree(first_cache, second_cache)
    actual_load = ce_forecast.load_ce_quarter
    actual_hash = ce_forecast._sha256
    hashes = []
    loads = []

    def guarded_load(*args, **kwargs):
        assert kwargs["allow_download"] is False
        loads.append(args)
        return actual_load(*args, **kwargs)

    def counted_hash(path):
        hashes.append(path)
        return actual_hash(path)

    def no_network(*args, **kwargs):
        raise AssertionError("CE cache reads must never request a download")

    monkeypatch.setattr(ce_forecast, "load_ce_quarter", guarded_load)
    monkeypatch.setattr(ce_forecast, "_sha256", counted_hash)
    monkeypatch.setattr("spm_calculator.ce_threshold._fetch_bytes", no_network)
    first, first_sources = load_observed_ce(first_cache)
    assert len(hashes) == 11
    assert len(loads) == 44
    second, second_sources = load_observed_ce(second_cache)
    assert len(hashes) == 22
    assert len(loads) == 88
    assert len(set(hashes)) == 22
    assert first_sources == second_sources
    assert len(first_sources) == 11
    assert sum(len(source["members"]) for source in first_sources) == 44
    assert set(first) == set(second) == set(observed_frames())
    for key in first:
        pd.testing.assert_frame_equal(first[key], second[key])
        assert first[key].attrs == second[key].attrs
        source = first[key].attrs["source"]
        assert source["bundle_path"] == Path(source["bundle_path"]).name
        assert "UNRELATED_NUMERIC" not in first[key]
        assert "NEWID" in first[key]
        assert "FINLWT21" in first[key]
        assert "EMRTPNOP" in first[key]
        with zipfile.ZipFile(first_cache / source["bundle_path"]) as archive:
            expected = hashlib.sha256(
                archive.read(source["member"])
            ).hexdigest()
        assert source["member_sha256"] == expected
        assert (
            source["bundle_sha256"]
            == hashlib.sha256(
                (first_cache / source["bundle_path"]).read_bytes()
            ).hexdigest()
        )


def test_cache_rejects_noncanonical_q1_overlap_vintage(tmp_path, monkeypatch):
    cache = tmp_path / "alternate"
    write_synthetic_cache(cache, alternate_2024_q1=True)

    def no_network(*args, **kwargs):
        raise AssertionError("CE cache reads must never request a download")

    monkeypatch.setattr("spm_calculator.ce_threshold._fetch_bytes", no_network)
    with pytest.raises(ValueError, match="noncanonical.*vintage"):
        load_observed_ce(cache)
