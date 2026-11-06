"""Tests for replicate-weight standard errors (``spm_calculator.ce_replicates``).

Invariants, stated in the module docstring:

1. A replicate variance is nonnegative, zero when every replicate equals
   the full sample, unchanged by a common shift or by reordering the
   replicates, and scaled by ``1 / (1 - k) ** 2`` under Fay's ``k``.
2. Rubin's total variance is at least the mean within-implicate variance
   and at least ``(1 + 1/M)`` times the between-implicate variance; the
   fraction of missing information lies in [0, 1]; the degrees of freedom
   lie between zero and the complete-data value and never exceed Rubin's.
3. With every replicate weight equal to the full-sample weight, every
   replicate reproduces the full-sample thresholds exactly.
4. Each replicate's band means reproduce its thresholds.
5. Results are deterministic.

Differential tests hold the replicate path to the public stage functions,
and the statistics to independent reference implementations. Receipt
tests recompute every standard error from the replicates the receipt
stores.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from spm_calculator.ce_bls_shares import band_components
from spm_calculator.ce_inkind_stage import (
    IN_KIND_COMPONENTS,
    add_in_kind,
    prepare_out_of_pocket,
    replicate_with_in_kind,
)
from spm_calculator.ce_replicates import (
    CE_FAY,
    IDENTITY_TOLERANCE,
    REPLICATE_WEIGHTS,
    REPLICATES,
    STRATA,
    Combined,
    check_standard_brr,
    combine_implicates,
    combine_replicated,
    replicate_estimates,
    replicate_variance,
    replicate_weight_matrix,
    reweight,
)
from spm_calculator.ce_threshold import TENURES
from spm_calculator.published_thresholds import (
    get_published_thresholds,
    get_standard_errors,
)
from tests.test_ce_inkind import (
    PROPERTY,
    ROOT,
    ce_frame,
    flat_cpi,
    in_kind_table,
    sha256,
)

CURRENT = ROOT / "spm_calculator/data/current"
RECEIPT = CURRENT / "ce_replicate_uncertainty_2019_2025.json"
REPLICATION_RECEIPT = CURRENT / "ce_inkind_replication_2019_2025.json"
COMPONENTS_RECEIPT = CURRENT / "ce_inkind_bls_components_2019_2025.json"
YEARS = tuple(str(year) for year in range(2019, 2026))
RUNS = ("package", "fcsuti")
AMOUNTS = ("imputed_total", "rental_assistance_per_renter", "school_lunch")
PIPELINE = settings(
    max_examples=6,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
NU_COM = float(STRATA)

values = st.floats(-1e4, 1e4, allow_nan=False, allow_infinity=False)
variances = st.floats(0, 1e8, allow_nan=False, allow_infinity=False)


# ---------------------------------------------------------------------------
# Synthetic inputs
# ---------------------------------------------------------------------------


def half_sample_weights(frame: pd.DataFrame, seed: int, replicates: int):
    """Random half samples at twice the full-sample weight, BRR style."""
    rng = np.random.default_rng(seed)
    full = frame["FINLWT21"].to_numpy(dtype=float)
    halves = rng.integers(0, 2, (len(frame), replicates)).astype(bool)
    return np.where(halves, 2 * full[:, None], 0.0)


def in_kind_tables(frame: pd.DataFrame, seed: int, implicates: int = 2):
    rng = np.random.default_rng(seed + 1)
    return [
        in_kind_table(
            frame["NEWID"],
            rng.uniform(0, 600, (len(frame), len(IN_KIND_COMPONENTS))),
        )
        for _ in range(implicates)
    ]


def rubin_reference(estimates, within, nu_com=NU_COM):
    """Rubin's rules and Barnard-Rubin df, written with numpy."""
    q = np.asarray(estimates, dtype=float)
    u = np.asarray(within, dtype=float)
    m = len(q)
    between = float(q.var(ddof=1))
    total = float(u.mean()) + (1 + 1 / m) * between
    fraction = (1 + 1 / m) * between / total if total > 0 else 0.0
    nu_obs = (nu_com + 1) / (nu_com + 3) * nu_com * (1 - fraction)
    if fraction == 0:
        return float(q.mean()), total, nu_obs
    nu_m = (m - 1) / fraction**2
    df = 0.0 if nu_obs == 0 else nu_m * nu_obs / (nu_m + nu_obs)
    return float(q.mean()), total, df


@st.composite
def implicate_sets(draw, smallest_variance=0.0):
    m = draw(st.integers(2, 8))
    estimates = draw(st.lists(values, min_size=m, max_size=m))
    within = draw(
        st.lists(
            st.floats(smallest_variance, 1e8),
            min_size=m,
            max_size=m,
        )
    )
    return estimates, within


# ---------------------------------------------------------------------------
# Invariant 1: replicate variances
# ---------------------------------------------------------------------------


@PROPERTY
@given(estimate=values, replicates=st.lists(values, min_size=1, max_size=60))
def test_replicate_variance_is_nonnegative_and_matches_numpy(
    estimate, replicates
):
    variance = replicate_variance(estimate, replicates)
    assert variance >= 0
    expected = float(np.mean((np.asarray(replicates) - estimate) ** 2))
    assert variance == pytest.approx(expected, rel=1e-9, abs=1e-12)


@PROPERTY
@given(estimate=values, count=st.integers(1, 60))
def test_replicates_equal_to_the_estimate_have_zero_variance(estimate, count):
    assert replicate_variance(estimate, [estimate] * count) == 0.0


@PROPERTY
@given(
    estimate=values,
    replicates=st.lists(values, min_size=1, max_size=60),
    shift=values,
    data=st.data(),
)
def test_replicate_variance_ignores_shift_and_order(
    estimate, replicates, shift, data
):
    variance = replicate_variance(estimate, replicates)
    shifted = replicate_variance(
        estimate + shift, [value + shift for value in replicates]
    )
    assert shifted == pytest.approx(variance, rel=1e-9, abs=1e-6)
    order = data.draw(st.permutations(replicates))
    assert replicate_variance(estimate, order) == variance


@PROPERTY
@given(
    estimate=values,
    replicates=st.lists(values, min_size=1, max_size=60),
    fay=st.floats(0, 0.9),
)
def test_fay_coefficient_scales_the_variance(estimate, replicates, fay):
    standard = replicate_variance(estimate, replicates)
    assert replicate_variance(estimate, replicates, fay) == pytest.approx(
        standard / (1 - fay) ** 2, rel=1e-12, abs=1e-300
    )


def test_ce_fay_weights_multiply_the_variance_by_four():
    replicates = [1.0, 3.0, -2.0, 5.0]
    assert replicate_variance(0.5, replicates, CE_FAY) == pytest.approx(
        4 * replicate_variance(0.5, replicates)
    )


@pytest.mark.parametrize("fay", (-0.1, 1.0, 1.5))
def test_fay_coefficient_outside_its_range_raises(fay):
    with pytest.raises(ValueError, match="Fay"):
        replicate_variance(0.0, [1.0], fay)


def test_replicate_variance_rejects_empty_and_nonfinite_input():
    with pytest.raises(ValueError, match="At least one"):
        replicate_variance(0.0, [])
    with pytest.raises(ValueError, match="finite"):
        replicate_variance(0.0, [math.nan])
    with pytest.raises(ValueError, match="finite"):
        replicate_variance(math.inf, [1.0])


# ---------------------------------------------------------------------------
# Invariant 2: Rubin's rules
# ---------------------------------------------------------------------------


@PROPERTY
@given(implicate_sets())
def test_rubin_total_bounds_and_degrees_of_freedom(case):
    estimates, within = case
    combined = combine_implicates(estimates, within)
    m = len(estimates)
    assert combined.total >= combined.within >= 0
    assert combined.total >= (1 + 1 / m) * combined.between
    assert 0 <= combined.fraction_missing <= 1
    assert 0 <= combined.df < NU_COM
    if combined.df_rubin is not None:
        assert combined.df <= combined.df_rubin * (1 + 1e-12)
    assert combined.standard_error == math.sqrt(combined.total)


@PROPERTY
@given(implicate_sets(smallest_variance=1e-6))
def test_rubin_matches_a_reference_implementation(case):
    # Zero within-variance cases sit in test_rubin_degenerate_cases: there
    # a last-bit difference in the mean moves the df between its limits.
    estimates, within = case
    combined = combine_implicates(estimates, within)
    estimate, total, df = rubin_reference(estimates, within)
    assert combined.estimate == pytest.approx(estimate, rel=1e-12, abs=1e-9)
    assert combined.total == pytest.approx(total, rel=1e-9, abs=1e-9)
    assert combined.df == pytest.approx(df, rel=1e-6, abs=1e-9)


@PROPERTY
@given(implicate_sets(), st.data())
def test_rubin_ignores_implicate_order(case, data):
    estimates, within = case
    order = data.draw(st.permutations(range(len(estimates))))
    combined = combine_implicates(estimates, within)
    reordered = combine_implicates(
        [estimates[i] for i in order], [within[i] for i in order]
    )
    assert reordered == combined


@PROPERTY
@given(estimate=values, within=st.lists(variances, min_size=2, max_size=8))
def test_equal_implicates_have_no_between_variance(estimate, within):
    combined = combine_implicates([estimate] * len(within), within)
    assert combined.between == 0
    assert combined.df_rubin is None
    assert combined.df == pytest.approx(NU_COM * (NU_COM + 1) / (NU_COM + 3))


def test_rubin_degenerate_cases():
    no_variance = combine_implicates([2.0, 2.0, 2.0], [0.0, 0.0, 0.0])
    assert no_variance.total == 0 and no_variance.fraction_missing == 0
    between_only = combine_implicates([1.0, 2.0, 3.0], [0.0, 0.0, 0.0])
    assert between_only.fraction_missing == 1
    assert between_only.df_rubin == 2
    assert between_only.df == 0
    with pytest.raises(ValueError, match="two or more"):
        combine_implicates([1.0], [1.0])
    with pytest.raises(ValueError, match="nonnegative"):
        combine_implicates([1.0, 2.0], [1.0, -1.0])


def test_combine_replicated_pools_each_implicates_replicate_variance():
    by_implicate = [[10.0, 11.0, 9.0, 12.0], [11.0, 10.0, 13.0, 11.0]]
    combined = combine_replicated(by_implicate)
    within = [replicate_variance(v[0], v[1:]) for v in by_implicate]
    assert combined == combine_implicates([10.0, 11.0], within)
    assert isinstance(combined, Combined)


# ---------------------------------------------------------------------------
# Replicate weights as CE PUMD stores them
# ---------------------------------------------------------------------------


def pumd_weights(rows: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame(index=range(rows))
    for number, name in enumerate(REPLICATE_WEIGHTS):
        frame[name] = rng.uniform(100, 9000, rows)
    for row in range(rows):
        blank = rng.permutation(REPLICATES)[: REPLICATES // 2]
        for number in blank:
            frame.iat[row, number] = np.nan
    return frame


def test_blank_replicate_weights_read_as_zero():
    frame = pumd_weights(5, 0)
    as_text = frame.apply(
        lambda column: column.map(
            lambda v: "." if pd.isna(v) else repr(float(v))
        )
    )
    first_blank = int(np.flatnonzero(frame.iloc[0].isna().to_numpy())[0])
    as_text.iat[0, first_blank] = ""
    as_text.iat[1, first_blank] = (
        " . "
        if as_text.iat[1, first_blank] == "."
        else as_text.iat[1, first_blank]
    )
    numeric = replicate_weight_matrix(frame)
    assert np.array_equal(numeric, replicate_weight_matrix(as_text))
    assert np.array_equal(numeric, frame.fillna(0.0).to_numpy())
    check_standard_brr(numeric)


@pytest.mark.parametrize("bad", ("x", "-5", "inf"))
def test_unreadable_or_negative_replicate_weights_raise(bad):
    frame = pumd_weights(3, 1).astype(object)
    frame.iat[1, 2] = bad
    with pytest.raises(ValueError):
        replicate_weight_matrix(frame)


def test_missing_replicate_weight_columns_raise():
    frame = pumd_weights(2, 2).drop(columns=["WTREP17"])
    with pytest.raises(ValueError, match="WTREP17"):
        replicate_weight_matrix(frame)


def test_fay_weights_fail_the_standard_brr_check():
    every = np.full((3, REPLICATES), 500.0)
    with pytest.raises(ValueError, match="Fay"):
        check_standard_brr(every)
    uneven = replicate_weight_matrix(pumd_weights(3, 3))
    uneven[2, np.flatnonzero(uneven[2] == 0)[0]] = 10.0
    with pytest.raises(ValueError, match="23"):
        check_standard_brr(uneven)
    with pytest.raises(ValueError, match="44"):
        check_standard_brr(np.ones((2, 43)))


def test_reweight_drops_zero_weight_rows():
    frame = ce_frame(5, n=8)
    weights = np.array([0, 1, 2, 0, 3, 0, 4, 5], dtype=float)
    out = reweight(frame, weights)
    assert list(out["NEWID"]) == list(frame["NEWID"][weights > 0])
    assert list(out["FINLWT21"]) == [1, 2, 3, 4, 5]
    assert list(frame["FINLWT21"]) != list(out["FINLWT21"])


# ---------------------------------------------------------------------------
# Invariants 3-5: the replicate pipeline
# ---------------------------------------------------------------------------


@PIPELINE
@given(seed=st.integers(0, 10_000))
def test_full_sample_weights_reproduce_the_full_sample(seed):
    frame = ce_frame(seed, n=120)
    full = frame["FINLWT21"].to_numpy(dtype=float)
    estimates = replicate_estimates(
        frame,
        2024,
        in_kind_tables(frame, seed),
        weights=np.repeat(full[:, None], 3, axis=1),
        cpi_series=flat_cpi(),
    )
    assert all(r == estimates.without[0] for r in estimates.without)
    for runs, bands in zip(estimates.with_stage, estimates.bands):
        assert all(r == runs[0] for r in runs)
        assert all(b == bands[0] for b in bands)
    for tenure in TENURES:
        values = [r[tenure] for r in estimates.without]
        assert replicate_variance(values[0], values[1:]) == 0.0


@PIPELINE
@given(seed=st.integers(0, 10_000))
def test_replicates_match_the_public_stage_functions(seed):
    frame = ce_frame(seed, n=120)
    tables = in_kind_tables(frame, seed)
    weights = half_sample_weights(frame, seed, 3)
    estimates = replicate_estimates(
        frame, 2024, tables, weights=weights, cpi_series=flat_cpi()
    )
    assert estimates.replicates == (1, 2, 3)
    assert estimates.identity_gap <= IDENTITY_TOLERANCE
    for position in range(4):
        sample = (
            frame
            if position == 0
            else reweight(frame, weights[:, position - 1])
        )
        run = prepare_out_of_pocket(sample, 2024, cpi_series=flat_cpi())
        assert estimates.without[position] == run.result["thresholds"]
        for implicate, table in enumerate(tables):
            staged = replicate_with_in_kind(run, table)["thresholds"]
            assert estimates.with_stage[implicate][position] == staged
            frame_with, _ = add_in_kind(run.expenditures, table)
            band = band_components(frame_with)
            assert estimates.bands[implicate][position] == band
            for tenure in TENURES:
                assert band.threshold(tenure) == pytest.approx(
                    staged[tenure], rel=IDENTITY_TOLERANCE
                )


def test_replicate_estimates_are_deterministic():
    frame = ce_frame(11, n=120)
    tables = in_kind_tables(frame, 11)
    weights = half_sample_weights(frame, 11, 4)
    runs = [
        replicate_estimates(
            frame.copy(), 2024, tables, weights=weights, cpi_series=flat_cpi()
        )
        for _ in range(2)
    ]
    assert runs[0] == runs[1]


def test_replicate_subset_and_frame_columns():
    frame = ce_frame(12, n=120)
    weights = half_sample_weights(frame, 12, REPLICATES)
    with_columns = frame.copy()
    for number, name in enumerate(REPLICATE_WEIGHTS):
        with_columns[name] = np.where(
            weights[:, number] > 0, weights[:, number], np.nan
        )
    subset = replicate_estimates(
        with_columns, 2024, replicates=[2, 7], cpi_series=flat_cpi()
    )
    explicit = replicate_estimates(
        frame,
        2024,
        weights=weights,
        replicates=[2, 7],
        cpi_series=flat_cpi(),
    )
    assert subset == explicit
    assert subset.replicates == (2, 7) and subset.with_stage == ()
    with pytest.raises(ValueError, match="1..44"):
        replicate_estimates(frame, 2024, weights=weights, replicates=[45])
    with pytest.raises(ValueError, match="one row per"):
        replicate_estimates(frame, 2024, weights=weights[:-1])


# ---------------------------------------------------------------------------
# The committed receipt
# ---------------------------------------------------------------------------


def _reject_constant(name):
    raise ValueError(f"receipt holds {name}")


def committed_receipt() -> dict:
    return json.loads(RECEIPT.read_text(), parse_constant=_reject_constant)


def test_receipt_is_complete_and_current():
    receipt = committed_receipt()
    assert receipt["complete"] is True
    assert receipt["targets"] == [int(year) for year in YEARS]
    assert receipt["replicates_run"] == REPLICATES
    for path, digest in receipt["code_sha256"].items():
        assert sha256(ROOT / path) == digest, path
    inputs = receipt["inputs"]
    assert inputs["replication_receipt"]["sha256"] == sha256(
        REPLICATION_RECEIPT
    )
    assert inputs["components_receipt"]["sha256"] == sha256(COMPONENTS_RECEIPT)
    method = receipt["method"]
    assert (method["replicates"], method["fay_coefficient"]) == (44, 0.0)
    assert method["complete_data_df"] == STRATA


def test_receipt_checks_hold():
    checks = committed_receipt()["checks"]
    assert checks["standard_brr"]["quarters"] == 44
    assert checks["half_sample_patterns"]["distinct_patterns"] == 2 * STRATA
    assert (
        checks["threshold_identity_largest_relative_gap"]
        <= checks["threshold_identity_tolerance"]
        == IDENTITY_TOLERANCE
    )
    full = checks["full_sample"]
    assert full["out_of_pocket_matches_replication_receipt"] is True
    assert (
        full["with_in_kind_largest_relative_gap"]
        <= full["with_in_kind_tolerance"]
    )
    assert full["amounts_largest_relative_gap"] <= full["amounts_tolerance"]
    assert checks["replicate_weight_sum_largest_relative_gap"] < 1e-6


def brr_check(block: dict, replicates: list[float]):
    assert len(replicates) == REPLICATES + 1
    assert block["estimate"] == replicates[0]
    squares = math.fsum((v - replicates[0]) ** 2 for v in replicates[1:])
    assert block["standard_error"] == pytest.approx(
        math.sqrt(squares / REPLICATES), rel=1e-12
    )
    assert block["df"] == STRATA


def rubin_check(block: dict, by_implicate: list[list[float]]):
    combined = combine_replicated(by_implicate).to_dict()
    for key, value in combined.items():
        if value is None:
            assert block[key] is None, key
        else:
            assert block[key] == pytest.approx(value, rel=1e-12), key
    assert block["by_implicate"] == [v[0] for v in by_implicate]


def test_receipt_standard_errors_recompute_from_its_replicates():
    receipt = committed_receipt()
    replication = json.loads(REPLICATION_RECEIPT.read_text())
    for run in RUNS:
        for year in YEARS:
            record = receipt["runs"][run]["years"][year]
            stored = record["replicates"]
            expected = replication["results"][year]
            if run == "fcsuti":
                expected = expected["fcsuti_deflated"]
            for tenure in TENURES:
                without = stored["without_in_kind"][tenure]
                brr_check(record["without_in_kind"][tenure], without)
                assert without[0] == expected["without_in_kind"][tenure]
                with_stage = stored["with_in_kind"][tenure]
                rubin_check(record["with_in_kind"][tenure], with_stage)
                for implicate, values in enumerate(with_stage):
                    assert values[0] == pytest.approx(
                        expected["with_in_kind_by_implicate"][implicate][
                            tenure
                        ],
                        rel=1e-12,
                    )
                lift = [
                    [100 * (w / o - 1) for w, o in zip(values, without)]
                    for values in with_stage
                ]
                rubin_check(record["in_kind_lift_percent"][tenure], lift)
            for name in AMOUNTS:
                rubin_check(record["amounts"][name], stored["amounts"][name])


def test_receipt_bls_comparison():
    receipt = committed_receipt()
    for run in RUNS:
        ratios = {"without_in_kind": [], "with_in_kind": []}
        for year in YEARS:
            record = receipt["runs"][run]["years"][year]
            errors = get_standard_errors(int(year))
            assert record["bls"]["standard_errors"] == errors
            assert record["bls"]["thresholds"] == get_published_thresholds(
                int(year)
            )
            for stage in ratios:
                for tenure in TENURES:
                    ratio = record["ratio_to_bls_standard_error"][stage][
                        tenure
                    ]
                    assert ratio == pytest.approx(
                        record[stage][tenure]["standard_error"]
                        / errors[tenure],
                        rel=1e-12,
                    )
                    ratios[stage].append(ratio)
        for stage, values in ratios.items():
            assert receipt["runs"][run]["ratio_to_bls_standard_error_range"][
                stage
            ] == [min(values), max(values)]


def growth(base, target):
    return 100 * (target / base - 1)


def test_receipt_growth_recomputes_from_its_replicates():
    receipt = committed_receipt()
    components = json.loads(COMPONENTS_RECEIPT.read_text())
    for run in RUNS:
        years = receipt["runs"][run]["years"]
        for span, block in receipt["runs"][run]["growth"].items():
            base, target = span.split("-")
            a, b = years[base]["replicates"], years[target]["replicates"]
            for tenure in TENURES:
                without = [
                    growth(x, y)
                    for x, y in zip(
                        a["without_in_kind"][tenure],
                        b["without_in_kind"][tenure],
                    )
                ]
                brr_check(block["without_in_kind"][tenure], without)
                with_stage = [
                    [growth(x, y) for x, y in zip(first, last)]
                    for first, last in zip(
                        a["with_in_kind"][tenure], b["with_in_kind"][tenure]
                    )
                ]
                rubin_check(block["with_in_kind"][tenure], with_stage)
                change = [
                    [g - h for g, h in zip(values, without)]
                    for values in with_stage
                ]
                rubin_check(block["stage_change_points"][tenure], change)
        assert sorted(receipt["runs"][run]["growth"]) == sorted(
            ["2022-2025"]
            + [f"{year - 1}-{year}" for year in range(2020, 2026)]
        )
        span = receipt["runs"][run]["growth"]["2022-2025"]
        recorded = components["runs"][run]["growth_2022_2025"]["by_tenure"]
        first = years["2022"]["replicates"]
        last = years["2025"]["replicates"]
        for tenure in TENURES:
            assert span["stage_change_points"][tenure][
                "from_mean_thresholds"
            ] == pytest.approx(
                recorded[tenure]["stage_change_points"], rel=1e-9
            )
            assert span["stage_change_points"][tenure][
                "by_implicate"
            ] == pytest.approx(
                recorded[tenure]["stage_change_by_implicate"], rel=1e-9
            )
            net = [
                [
                    growth(t0 - c0, t1 - c1)
                    for t0, c0, t1, c1 in zip(
                        first["with_in_kind"][tenure][m],
                        first["imputed_terms"][tenure][m],
                        last["with_in_kind"][tenure][m],
                        last["imputed_terms"][tenure][m],
                    )
                ]
                for m in range(len(first["with_in_kind"][tenure]))
            ]
            removed = span["growth_without_imputed_terms"][tenure]
            rubin_check(removed, net)
            assert removed["from_mean_thresholds"] == pytest.approx(
                recorded[tenure]["growth_without_imputed_terms"], rel=1e-9
            )
            assert removed["by_implicate"] == pytest.approx(
                recorded[tenure]["growth_without_imputed_terms_by_implicate"],
                rel=1e-9,
            )
        rises = receipt["runs"][run]["amount_rise_2022_2025"]
        for name in AMOUNTS:
            first = years["2022"]["replicates"]["amounts"][name]
            last = years["2025"]["replicates"]["amounts"][name]
            rubin_check(
                rises[name],
                [[y - x for x, y in zip(p, q)] for p, q in zip(first, last)],
            )
            assert rises[name]["estimate"] == pytest.approx(
                components["runs"][run]["growth_2022_2025"][name]["rise"],
                rel=1e-9,
            )


def test_receipt_intervals_use_t_quantiles():
    stats = pytest.importorskip("scipy.stats")
    receipt = committed_receipt()
    block = receipt["runs"]["package"]["growth"]["2022-2025"]
    for tenure in TENURES:
        for key in ("without_in_kind", "with_in_kind", "stage_change_points"):
            entry = block[key][tenure]
            assert entry["t_975"] == pytest.approx(
                float(stats.t.ppf(0.975, entry["df"])), rel=1e-12
            )
