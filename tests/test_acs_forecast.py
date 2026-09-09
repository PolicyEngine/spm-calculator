"""Behavioral tests for explicitly approximate ACS rolling projections."""

import numpy as np
import pandas as pd
import pytest

from spm_calculator.acs_forecast import (
    add_index_topcode_diagnostics,
    build_window,
    evaluate_indices,
    project_acs_windows,
    summarize_window,
    weighted_median,
)


def records(years, values_a=None, values_b=None, repeats=1):
    rows = []
    for year in years:
        for puma, values in [("0100100", values_a), ("0100200", values_b)]:
            value = values.get(year, 100) if values else 100
            for n in range(repeats):
                rows.append(
                    {
                        "record_id": f"{year}-{puma}-{n}",
                        "cohort_year": year,
                        "puma_geoid": puma,
                        "rent": value,
                        "weight": 1.0,
                    }
                )
    return pd.DataFrame(rows)


def allocations(fraction=1.0):
    return pd.DataFrame(
        [
            {
                "puma_geoid": "0100100",
                "area_code": "1001",
                "fraction": fraction,
            },
            {
                "puma_geoid": "0100100",
                "area_code": None,
                "fraction": 1 - fraction,
            },
            {"puma_geoid": "0100200", "area_code": "1002", "fraction": 1.0},
        ]
    )


def project(old, new, **kwargs):
    return project_acs_windows(
        old,
        new,
        allocations(),
        {"1001": 1.0, "1002": 1.0},
        nominal_rent_growth_by_year={y: 0.03 for y in range(2025, 2031)},
        price_growth_by_year={y: 0.03 for y in range(2025, 2031)},
        **kwargs,
    )


def test_pooled_weighted_median_is_not_a_median_of_annual_medians():
    assert weighted_median([10, 100, 200], [8, 1, 1]) == 10
    assert np.median([10, 100, 200]) == 100


def test_equal_future_rent_growth_moves_ratio_as_history_leaves():
    a = {2019: 50, 2020: 50, 2021: 50, 2022: 200, 2023: 200, 2024: 200}
    old = records(range(2019, 2024), a)
    new = records(range(2020, 2025), a)
    result = project(old, new)
    assert result["indices_by_year"]["2024"]["1001"] == 1
    assert result["indices_by_year"]["2025"]["1001"] != 1
    assert result["diagnostics_by_year"]["2026"]["window"] == {
        "start": 2021,
        "end": 2025,
        "observed_years": [2021, 2022, 2023, 2024],
        "projected_years": [2025],
    }


def test_proportional_constant_history_is_invariant():
    a = {y: 200 for y in range(2019, 2025)}
    b = {y: 100 for y in range(2019, 2025)}
    result = project(
        records(range(2019, 2024), a, b), records(range(2020, 2025), a, b)
    )
    assert all(
        v == {"1001": 1.0, "1002": 1.0}
        for v in result["indices_by_year"].values()
    )


def test_vintage_bridge_removes_measured_common_window_shift():
    old = records(range(2019, 2024))
    new = records(range(2020, 2025), {y: 250 for y in range(2020, 2025)})
    result = project(old, new)
    assert (
        result["metadata"]["overlap_bridge"]["1001"][
            "overlap_vintage_multiplier"
        ]
        != 1
    )
    assert result["indices_by_year"]["2025"]["1001"] == 1


def test_new_official_anchor_has_no_old_vintage_bridge():
    result = project(
        records(range(2019, 2024)),
        records(range(2020, 2025)),
        anchor_spm_year=2025,
    )
    assert result["indices_by_year"]["2025"] == {"1001": 1.0, "1002": 1.0}
    assert result["metadata"]["overlap_bridge"] == {}


def test_terminal_donors_do_not_inflate_original_support():
    source = records(range(2020, 2025), repeats=10)
    window = build_window(
        source,
        2030,
        donor_year=2024,
        nominal_rent_growth_by_year={y: 0.03 for y in range(2025, 2030)},
        price_growth_by_year={y: 0.03 for y in range(2025, 2030)},
    )
    result = summarize_window(window, allocations(), ["1001", "1002"])
    area = result["areas"]["1001"]
    assert area["unique_records"] == 10
    assert area["expected_whole_record_count"] == 10
    assert area["kish_effective_count"] == pytest.approx(10)
    assert area["thin_support"]


def test_fractional_sliver_is_thin_and_unassigned_stays_national():
    source = records(range(2020, 2025), repeats=20)
    result = summarize_window(source, allocations(0.01), ["1001", "1002"])
    area = result["areas"]["1001"]
    assert area["unique_records"] == 100
    assert area["expected_whole_record_count"] == pytest.approx(1)
    assert area["thin_support"]
    assert result["national_weight"] == 200
    assert result["unassigned_weight"] == pytest.approx(99)
    assert result["assigned_weight"] + result[
        "unassigned_weight"
    ] == pytest.approx(200)


def test_missing_source_cohort_and_growth_fail():
    with pytest.raises(ValueError, match="cohort"):
        project(records([2019, 2020, 2022, 2023]), records(range(2020, 2025)))
    with pytest.raises(ValueError, match="growth"):
        build_window(
            records(range(2020, 2025)),
            2026,
            donor_year=2024,
            nominal_rent_growth_by_year={},
            price_growth_by_year={},
        )


@pytest.mark.parametrize("weights", [[0, 1], [-1, 1], [np.nan, 1]])
def test_invalid_weights_fail(weights):
    with pytest.raises(ValueError):
        weighted_median([1, 2], weights)


def test_incomplete_allocations_fail():
    with pytest.raises(ValueError, match="sum|allocation"):
        summarize_window(
            records(range(2020, 2025)),
            allocations().iloc[1:],
            ["1001", "1002"],
        )


def test_topcode_bounds_flag_a_possibly_affected_median():
    data = records([2024])
    data["top_rent"] = [True, False]
    data["rent_lower_bound"] = [10.0, 100.0]
    result = summarize_window(data, allocations(), ["1001", "1002"])
    assert result["areas"]["1001"]["median_topcode_warning"]
    assert result["areas"]["1001"]["topcoded_weight_share"] == 1


def test_uncensored_local_median_inherits_national_index_warning():
    data = records([2024], values_b={2024: 200})
    data["weight"] = [1.0, 3.0]
    data["top_rent"] = [False, True]
    data["rent_lower_bound"] = [100.0, 150.0]
    result = summarize_window(data, allocations(), ["1001", "1002"])
    area = result["areas"]["1001"]
    assert area["model_rent_index"] == 0.5
    assert not area["local_median_topcode_warning"]
    assert area["topcoded_weight_share"] == 0
    assert result["national_topcoding"]["median_topcode_warning"]
    assert area["rent_index_topcode_warning"]
    assert area["rent_index_topcode_sources"] == {
        "target_local_median": False,
        "target_national_median": True,
    }


def test_bridge_reference_warning_survives_after_censored_cohort_leaves():
    old = records(range(2019, 2024))
    censored = (old.cohort_year == 2019) & (old.puma_geoid == "0100200")
    old["top_rent"] = censored
    old["rent_lower_bound"] = 100.0
    old.loc[censored, ["rent", "weight", "rent_lower_bound"]] = [200, 50, 150]
    new = records(range(2020, 2025))
    result = project(old, new)
    anchor = result["diagnostics_by_year"]["2024"]["areas"]["1001"]
    assert anchor["model_rent_index_topcode_warning"]
    assert not anchor["rent_index_topcode_warning"]
    for year in range(2025, 2031):
        area = result["diagnostics_by_year"][str(year)]["areas"]["1001"]
        assert not area["model_rent_index_topcode_warning"]
        assert not area["local_median_topcode_warning"]
        assert area["rent_index_topcode_warning"]
        assert area["rent_index_topcode_sources"]["old_full_national_median"]
        assert not area["rent_index_topcode_sources"][
            "old_overlap_national_median"
        ]


def test_unpublished_modeled_anchor_retains_topcode_warning():
    old = records(range(2019, 2024))
    old["top_rent"] = True
    old["rent_lower_bound"] = 50.0
    result = project(
        old,
        records(range(2020, 2025)),
        anchor_status_by_area={
            "1001": "modeled_unanchored",
            "1002": "published_anchor",
        },
    )
    areas = result["diagnostics_by_year"]["2024"]["areas"]
    assert areas["1001"]["rent_index_topcode_warning"]
    assert not areas["1002"]["rent_index_topcode_warning"]
    assert areas["1001"]["anchor_status"] == "modeled_unanchored"
    with pytest.raises(ValueError, match="Anchor statuses"):
        project(
            old,
            records(range(2020, 2025)),
            anchor_status_by_area={"1001": "published_anchor"},
        )


def test_holdout_ratio_warning_includes_origin_denominator():
    origin = records([2022], values_b={2022: 200})
    origin["weight"] = [1.0, 3.0]
    origin["top_rent"] = [False, True]
    origin["rent_lower_bound"] = [100.0, 150.0]
    reference = summarize_window(origin, allocations(), ["1001", "1002"])
    target = summarize_window(records([2023]), allocations(), ["1001", "1002"])
    add_index_topcode_diagnostics(target, {"origin": reference})
    area = target["areas"]["1001"]
    assert not area["model_rent_index_topcode_warning"]
    assert area["rent_index_topcode_warning"]
    assert area["rent_index_topcode_sources"]["origin_national_median"]


def test_evaluation_requires_identical_area_coverage_and_strict_improvement():
    result = evaluate_indices({"a": 1.1}, {"a": 1}, {"a": 1.1})
    assert result["status"] == "complete"
    assert result["candidate_metrics"]["mape"] == pytest.approx(10)
    assert not result["beats_baseline"]
    with pytest.raises(ValueError, match="coverage"):
        evaluate_indices({"a": 1}, {"a": 1, "b": 1}, {"a": 1})


def test_donor_rent_sensitivity_changes_real_rent_without_touching_history():
    data = records(range(2020, 2025))
    baseline = build_window(
        data,
        2027,
        donor_year=2024,
        nominal_rent_growth_by_year={2025: 0.03, 2026: 0.02},
        price_growth_by_year={2025: 0.03, 2026: 0.02},
    )
    sensitivity = build_window(
        data,
        2027,
        donor_year=2024,
        nominal_rent_growth_by_year={2025: 0.05, 2026: 0.04},
        price_growth_by_year={2025: 0.03, 2026: 0.02},
    )
    assert (baseline.rent == 100).all()
    assert (
        sensitivity.loc[sensitivity.cohort_year <= 2024, "rent"] == 100
    ).all()
    assert sensitivity.loc[sensitivity.cohort_year == 2026, "rent"].iloc[
        0
    ] == pytest.approx(100 * 1.05 / 1.03 * 1.04 / 1.02)
    assert sensitivity.weight.sum() == baseline.weight.sum()


def test_mixed_source_vintages_cannot_enter_one_pooled_median():
    data = records(range(2020, 2025))
    data["source_vintage"] = [2023] + [2024] * (len(data) - 1)
    with pytest.raises(ValueError, match="one source vintage"):
        summarize_window(data, allocations(), ["1001", "1002"])


def test_historical_donor_window_rejects_target_observations():
    with pytest.raises(ValueError, match="last observed"):
        build_window(
            records(range(2018, 2024)),
            2024,
            donor_year=2022,
            nominal_rent_growth_by_year={2023: 0.04},
            price_growth_by_year={2023: 0.04},
        )


def test_allocation_tolerance_only_accepts_floating_point_roundoff():
    mapping = allocations()
    mapping.loc[0, "fraction"] = 1 + 2e-16
    summarize_window(records([2024]), mapping, ["1001", "1002"])
    mapping.loc[0, "fraction"] = 1.001
    with pytest.raises(ValueError, match="allocation"):
        summarize_window(records([2024]), mapping, ["1001", "1002"])


def test_thin_support_keeps_computed_2035_window_and_rejects_missing_area():
    old = records(
        range(2019, 2024), values_a={y: 60 for y in range(2019, 2024)}
    )
    new = records(
        range(2020, 2025),
        values_a={y: 200 if y == 2024 else 60 for y in range(2020, 2025)},
    )
    rates = {y: 0.03 for y in range(2025, 2036)}
    result = project_acs_windows(
        old,
        new,
        allocations(),
        {"1001": 0.6, "1002": 1.0},
        end_spm_year=2035,
        nominal_rent_growth_by_year=rates,
        price_growth_by_year=rates,
    )
    future = result["diagnostics_by_year"]["2035"]["areas"]["1001"]
    assert future["thin_support"]
    assert future["unique_records"] == 1
    assert future["donor_support"]["unique_records"] == 1
    assert future["kish_effective_count"] == pytest.approx(1)
    assert (
        result["indices_by_year"]["2035"]["1001"]
        != result["indices_by_year"]["2024"]["1001"]
    )
    with pytest.raises(ValueError, match="Missing positive area coverage"):
        summarize_window(new, allocations(), ["1001", "1002", "absent"])
    for value in (0, -1, float("nan")):
        invalid = new.copy()
        invalid.loc[0, "weight"] = value
        with pytest.raises(ValueError, match="weight|complete"):
            summarize_window(invalid, allocations(), ["1001", "1002"])
