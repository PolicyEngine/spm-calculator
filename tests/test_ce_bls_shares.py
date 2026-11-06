"""BLS's published threshold components beside the replication's.

Invariants (stated in the PR and docs/ce-inkind-imputation.md):

1. ``band_mask`` selects the rows of ``estimate_thresholds``.
2. A unit's components sum to its FCSUti, and its shelter, utilities, LIHEAP
   and rental assistance to its SU.
3. ``BandComponents.threshold`` reproduces ``estimate_thresholds``, and the
   mean over implicates reproduces the mean threshold.
4. BLS's published shares, thresholds and tenure distribution satisfy
   T_h / 0.82 = C + SU_h + 0.2 F and F = C + sum_h P_h SU_h in every year.
5. ``level_gap`` terms sum to the difference between two thresholds.
6. Imputed and non-imputed shares of growth beyond inflation sum to one.
7. ``apply_bls_paper_definition`` lowers each unit's FCSUti by exactly the
   amounts it removes, and a second application changes nothing.
"""

import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from spm_calculator.ce_bls_shares import (
    COMMODITIES,
    COMPONENTS,
    DEFINITION_COLUMNS,
    IMPUTED,
    SHELTER_UTILITIES,
    TENURE_COMPONENTS,
    TENURES,
    BandComponents,
    apply_bls_paper_definition,
    band_components,
    band_definition_pieces,
    band_fixed_growth_effect,
    band_mask,
    bls_band_components,
    growth_percent,
    growth_without_imputed,
    imputed_share_beyond_inflation,
    level_gap,
    mean_components,
    read_threshold_shares,
    removed_by_bls_paper_definition,
    shelter_pieces,
    unit_components,
)
from spm_calculator.ce_inkind_stage import add_in_kind, prepare_out_of_pocket
from spm_calculator.ce_threshold import estimate_thresholds
from spm_calculator.equivalence_scale import REFERENCE_RAW_SCALE
from spm_calculator.published_thresholds import (
    get_published_thresholds,
    get_tenure_shares,
)
from tests.test_ce_inkind import PROPERTY, ce_frame, flat_cpi, in_kind_table

YEARS = range(2019, 2026)
SHELTER_COLUMNS = ("OWNDWE", "RNTXRP", "RNTAPY", "OTHLOD")


def definition_frame(seed: int, n: int = 60) -> pd.DataFrame:
    """A CE frame whose shelter summary holds the FMLI pieces it should."""
    rng = np.random.default_rng(seed)
    frame = ce_frame(seed, n=n)
    for suffix in ("PQ", "CQ"):
        total = 0.0
        for stem, scale in zip(SHELTER_COLUMNS, (2000, 2000, 30, 400)):
            frame[f"{stem}{suffix}"] = rng.uniform(0, scale, n)
            total = total + frame[f"{stem}{suffix}"]
        frame[f"SHELT{suffix}"] = total
        frame[f"FDMAP{suffix}"] = rng.uniform(0, 40, n)
        frame[f"FDAWAY{suffix}"] = frame[f"FDMAP{suffix}"] + rng.uniform(
            0, 300, n
        )
        frame[f"FDHOME{suffix}"] = rng.uniform(0, 1000, n)
        frame[f"FOOD{suffix}"] = (
            frame[f"FDAWAY{suffix}"] + (frame[f"FDHOME{suffix}"])
        )
    frame["EMRTPNOP"] = rng.uniform(0, 500, n)
    frame["EMRTPNOC"] = rng.uniform(0, 500, n)
    frame["MRTPRNOP"] = rng.uniform(0, 50, n)
    frame["MRTPRNOC"] = rng.uniform(0, 50, n)
    return frame


def staged(seed: int, n: int = 60, *, scale: float = 500.0) -> pd.DataFrame:
    """A normalized frame with random in-kind amounts added."""
    raw = definition_frame(seed, n)
    run = prepare_out_of_pocket(raw, 2024, cpi_series=flat_cpi())
    rng = np.random.default_rng(seed + 1)
    amounts = rng.uniform(0, scale, (len(raw), len(IMPUTED)))
    frame, _ = add_in_kind(
        run.expenditures, in_kind_table(raw["NEWID"], amounts)
    )
    return frame


# ---------------------------------------------------------------------------
# Invariants 1-3: the band and its components
# ---------------------------------------------------------------------------


@PROPERTY
@given(
    seed=st.integers(0, 10_000),
    n=st.integers(1, 80),
    scale=st.floats(0, 3000),
)
def test_components_reproduce_the_estimator(seed, n, scale):
    """Invariants 1 and 3, including tiny samples and empty tenures."""
    frame = staged(seed, n, scale=scale)
    thresholds, estimation = estimate_thresholds(frame)
    mask = band_mask(frame["fcsuti_2a2c"], frame["ce_weight"])
    assert mask.sum() == estimation["band_rows"]
    band = frame.loc[mask]
    weights = band["ce_weight"]
    assert np.average(band["fcsuti_2a2c"], weights=weights) == pytest.approx(
        estimation["fcsuti_mean"], rel=1e-12
    )
    assert band["fcsuti_2a2c"].min() == estimation["band_fcsuti_min"]
    assert band["fcsuti_2a2c"].max() == estimation["band_fcsuti_max"]
    components = band_components(frame)
    assert components.fcsuti == pytest.approx(
        estimation["fcsuti_mean"], rel=1e-9
    )
    for tenure in TENURES:
        assert components.threshold(tenure) == pytest.approx(
            thresholds[tenure], rel=1e-9
        )


@PROPERTY
@given(seed=st.integers(0, 10_000))
def test_unit_components_sum_to_fcsuti_and_su(seed):
    """Invariant 2. unit_components raises when the sums fail, so a frame
    with a changed column has to fail too."""
    frame = staged(seed)
    units = unit_components(frame)
    np.testing.assert_allclose(
        units[list(COMPONENTS)].sum(axis=1), frame["fcsuti_2a2c"]
    )
    np.testing.assert_allclose(
        units[list(SHELTER_UTILITIES)].sum(axis=1), frame["su_2a2c"]
    )
    broken = frame.copy()
    broken["su_2a2c"] = broken["su_2a2c"] + 1.0
    with pytest.raises(ValueError, match="do not sum"):
        unit_components(broken)


def test_components_without_the_stage_hold_no_imputed_amounts():
    raw = definition_frame(3)
    run = prepare_out_of_pocket(raw, 2024, cpi_series=flat_cpi())
    components = band_components(run.expenditures)
    assert components.imputed_total == 0.0
    assert components.pooled["internet"] == 0.0
    for tenure in TENURES:
        assert components.threshold(tenure) == pytest.approx(
            run.result["thresholds"][tenure], rel=1e-9
        )


@PROPERTY
@given(seeds=st.lists(st.integers(0, 10_000), min_size=1, max_size=5))
def test_mean_components_reproduce_the_mean_threshold(seeds):
    """Invariant 3: thresholds are linear in the components."""
    items = [band_components(staged(seed)) for seed in seeds]
    mean = mean_components(items)
    for tenure in TENURES:
        assert mean.threshold(tenure) == pytest.approx(
            np.mean([item.threshold(tenure) for item in items]), rel=1e-12
        )
        assert mean.imputed_term(tenure) == pytest.approx(
            np.mean([item.imputed_term(tenure) for item in items]), rel=1e-12
        )
    with pytest.raises(ValueError):
        mean_components([])


@PROPERTY
@given(
    pooled=st.lists(
        st.floats(0, 40_000),
        min_size=len(COMPONENTS),
        max_size=len(COMPONENTS),
    ),
    tenure_values=st.lists(
        st.floats(0, 40_000),
        min_size=len(TENURES) * len(TENURE_COMPONENTS),
        max_size=len(TENURES) * len(TENURE_COMPONENTS),
    ),
)
def test_imputed_term_adds_imputed_pieces(pooled, tenure_values):
    """A threshold holds each commodity at 1.2 and each shelter or utility
    component at its tenure's mean plus a fifth of the pooled mean."""
    pooled = dict(zip(COMPONENTS, pooled))
    values = iter(tenure_values)
    by_tenure = {
        t: {c: next(values) for c in TENURE_COMPONENTS} for t in TENURES
    }
    band = BandComponents(pooled, by_tenure, {t: 1 / 3 for t in TENURES})
    for tenure in TENURES:
        h = by_tenure[tenure]
        expected = 0.82 * (
            1.2 * sum(pooled[c] for c in COMMODITIES)
            + sum(h[c] + 0.2 * pooled[c] for c in SHELTER_UTILITIES)
        )
        assert band.threshold(tenure) == pytest.approx(expected, abs=1e-6)
        assert band.imputed_term(tenure) == pytest.approx(
            0.82
            * (
                1.2 * (pooled["nslp"] + pooled["wic"] + pooled["broadband"])
                + h["rental_assistance"]
                + 0.2 * pooled["rental_assistance"]
                + h["liheap"]
                + 0.2 * pooled["liheap"]
            ),
            abs=1e-6,
        )


# ---------------------------------------------------------------------------
# Invariant 4: BLS's published values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("year", YEARS)
def test_published_values_satisfy_both_identities(year):
    """Each year's shares, thresholds and tenure distribution fit together."""
    band, checks = bls_band_components(
        read_threshold_shares()[year],
        get_published_thresholds(year),
        get_tenure_shares(year),
    )
    assert abs(checks["fcsuti_error_dollars"]) < 0.002
    for tenure in TENURES:
        assert abs(checks["threshold_error_dollars"][tenure]) < 0.002
        assert band.threshold(tenure) == pytest.approx(
            get_published_thresholds(year)[tenure], abs=0.002
        )
    assert max(checks["shared_component_spread_dollars"].values()) < 0.002
    assert sum(band.tenure_mix.values()) == pytest.approx(1.0, abs=1e-8)


def test_published_mix_is_the_band_mix():
    """Moving one point of the band from owners without mortgages to renters
    breaks identity (2) by tens of dollars, so no other mix fits."""
    year = 2025
    shares = read_threshold_shares()[year]
    thresholds = get_published_thresholds(year)
    mix = get_tenure_shares(year)
    moved = dict(mix)
    moved["renter"] += 0.01
    moved["owner_without_mortgage"] -= 0.01
    with pytest.raises(ValueError, match="identity"):
        bls_band_components(shares, thresholds, moved)


def test_workbook_internet_rows_follow_the_tenure_invariant_one():
    """The row holding equal dollars across tenures changes in 2025, and
    the leaf rows overshoot by the broadband row in 2023 and 2024 only."""
    shares = read_threshold_shares()
    for year in YEARS:
        _, checks = bls_band_components(
            shares[year],
            get_published_thresholds(year),
            get_tenure_shares(year),
        )
        expected = "internet_total_row" if year == 2025 else "internet_oop_row"
        assert checks["internet_row"] == expected
        overshoot = checks["leaf_rows_above_threshold_dollars"]
        for tenure in TENURES:
            broadband = (
                shares[year][tenure]["broadband"]
                * get_published_thresholds(year)[tenure]
                / 0.82
            )
            if year in (2023, 2024):
                assert overshoot[tenure] == pytest.approx(broadband, abs=1e-3)
                assert overshoot[tenure] > 0
            else:
                assert overshoot[tenure] == pytest.approx(0.0, abs=1e-3)


def test_share_rows_cover_the_revised_columns():
    shares = read_threshold_shares()
    assert sorted(shares) == list(YEARS)
    assert shares[2019]["renter"]["food"] == pytest.approx(0.27739, abs=1e-5)
    assert shares[2025]["owner_with_mortgage"]["other"] == pytest.approx(
        0.16437, abs=1e-5
    )
    # BLS's n/a rows read as zero.
    assert shares[2022]["owner_with_mortgage"]["rental_assistance"] == 0.0
    assert shares[2022]["renter"]["broadband"] == 0.0


def synthetic_shares(band: BandComponents):
    """Shares for a BandComponents, in the workbook's layout."""
    thresholds = {t: band.threshold(t) for t in TENURES}
    shares = {}
    for tenure in TENURES:
        k = band.median_share / thresholds[tenure]
        row = {c: band.pooled[c] * k for c in COMMODITIES}
        row["internet_oop_row"] = (
            band.pooled["internet"] + band.pooled["broadband"]
        ) * k
        row["internet_total_row"] = row["internet_oop_row"]
        for component in TENURE_COMPONENTS:
            row[component] = band.by_tenure[tenure][component] * k
        row["other"] = 0.2 * band.fcsuti * k
        shares[tenure] = row
    return shares, thresholds


@PROPERTY
@given(
    seed=st.integers(0, 10_000),
    renter=st.floats(0.2, 0.6),
    no_mortgage=st.floats(0.05, 0.2),
)
def test_bls_components_round_trip(seed, renter, no_mortgage):
    """Components a share table implies are the ones that made it."""
    rng = np.random.default_rng(seed)
    mix = {
        "renter": renter,
        "owner_without_mortgage": no_mortgage,
        "owner_with_mortgage": 1 - renter - no_mortgage,
    }
    by_tenure = {
        t: {c: float(rng.uniform(100, 9000)) for c in TENURE_COMPONENTS}
        for t in TENURES
    }
    pooled = {c: float(rng.uniform(100, 9000)) for c in COMMODITIES}
    for component in TENURE_COMPONENTS:
        pooled[component] = sum(
            mix[t] * by_tenure[t][component] for t in TENURES
        )
    band = BandComponents(pooled, by_tenure, mix)
    shares, thresholds = synthetic_shares(band)
    recovered, checks = bls_band_components(shares, thresholds, mix)
    for component in COMPONENTS:
        assert recovered.pooled[component] == pytest.approx(
            band.pooled[component], abs=1e-6
        )
    for tenure in TENURES:
        assert recovered.threshold(tenure) == pytest.approx(
            thresholds[tenure], abs=1e-6
        )
    assert abs(checks["fcsuti_error_dollars"]) < 1e-6


def test_bls_components_reject_shares_that_differ_across_tenures():
    year = 2022
    shares = read_threshold_shares()[year]
    shares["renter"]["food"] *= 1.01
    with pytest.raises(ValueError, match="food"):
        bls_band_components(
            shares, get_published_thresholds(year), get_tenure_shares(year)
        )


def test_read_rejects_a_workbook_without_the_rows(tmp_path):
    import openpyxl

    workbook = openpyxl.Workbook()
    workbook.active.append(["Renters"])
    path = tmp_path / "shares.xlsx"
    workbook.save(path)
    with pytest.raises(ValueError, match="no rows"):
        read_threshold_shares(path)


# ---------------------------------------------------------------------------
# Invariants 5-6: gaps and growth
# ---------------------------------------------------------------------------


@PROPERTY
@given(a=st.integers(0, 10_000), b=st.integers(0, 10_000))
def test_level_gap_terms_sum_to_the_threshold_gap(a, b):
    """Invariant 5."""
    ours, theirs = band_components(staged(a)), band_components(staged(b))
    for tenure in TENURES:
        gap = level_gap(ours, theirs, tenure)
        assert sum(gap.values()) == pytest.approx(
            ours.threshold(tenure) - theirs.threshold(tenure), abs=1e-6
        )


@PROPERTY
@given(
    a=st.integers(0, 10_000),
    b=st.integers(0, 10_000),
    price=st.floats(1.0, 1.05),
)
def test_shares_of_growth_beyond_inflation_sum_to_one(a, b, price):
    """Invariant 6: imputed plus non-imputed growth beyond prices is all of
    it. Random windows can have growth beyond prices near zero, where the
    ratio has no meaning."""
    base, target = band_components(staged(a)), band_components(staged(b))
    for tenure in TENURES:
        beyond = target.threshold(tenure) - price * base.threshold(tenure)
        if abs(beyond) < 1.0:
            continue
        imputed = imputed_share_beyond_inflation(base, target, tenure, price)
        rest = (
            (target.threshold(tenure) - target.imputed_term(tenure))
            - price * (base.threshold(tenure) - base.imputed_term(tenure))
        ) / beyond
        assert imputed + rest == pytest.approx(1.0, rel=1e-9)


def scaled_band(band: BandComponents, factor: float) -> BandComponents:
    return BandComponents(
        {c: v * factor for c, v in band.pooled.items()},
        {
            t: {c: v * factor for c, v in band.by_tenure[t].items()}
            for t in TENURES
        },
        band.tenure_mix,
    )


@PROPERTY
@given(seed=st.integers(0, 10_000), factor=st.floats(1.01, 1.5))
def test_uniform_growth_leaves_no_band_fixed_effect(seed, factor):
    """When every component grows alike, removing the imputed terms changes
    nothing and they supply their proportional share of growth beyond a
    flat price level."""
    base = band_components(staged(seed))
    target = scaled_band(base, factor)
    for tenure in TENURES:
        assert band_fixed_growth_effect(base, target, tenure) == pytest.approx(
            0.0, abs=1e-9
        )
        assert growth_without_imputed(base, target, tenure) == pytest.approx(
            growth_percent(base.threshold(tenure), target.threshold(tenure)),
            abs=1e-9,
        )
        assert imputed_share_beyond_inflation(
            base, target, tenure, 1.0
        ) == pytest.approx(
            base.imputed_term(tenure) / base.threshold(tenure), rel=1e-9
        )


def test_growth_with_no_imputed_amounts_has_no_band_fixed_effect():
    run = prepare_out_of_pocket(
        definition_frame(5), 2024, cpi_series=flat_cpi()
    )
    base = band_components(run.expenditures)
    target = scaled_band(base, 1.2)
    for tenure in TENURES:
        assert base.imputed_term(tenure) == 0.0
        assert band_fixed_growth_effect(base, target, tenure) == pytest.approx(
            0.0, abs=1e-9
        )


# ---------------------------------------------------------------------------
# Invariant 7: BLS's written definitions
# ---------------------------------------------------------------------------


@PROPERTY
@given(seed=st.integers(0, 10_000))
def test_definition_removes_exactly_what_it_names(seed):
    """Invariant 7, unit by unit, through the replication's own stages."""
    raw = definition_frame(seed)
    removed = removed_by_bls_paper_definition(raw)
    before = prepare_out_of_pocket(raw, 2024, cpi_series=flat_cpi())
    after = prepare_out_of_pocket(
        apply_bls_paper_definition(raw), 2024, cpi_series=flat_cpi()
    )
    a, b = before.expenditures, after.expenditures
    # Each unit's own price factor can change with the CPI weights, so
    # compare in nominal quarterly dollars.
    scale = REFERENCE_RAW_SCALE / a["equiv_scale"]
    assert (b["equiv_scale"] == a["equiv_scale"]).all()
    nominal_before = a["fcsuti_2a2c"] / a["inflation_factor"] / scale / 4
    nominal_after = b["fcsuti_2a2c"] / b["inflation_factor"] / scale / 4
    expected = removed.loc[a.index].sum(axis=1)
    np.testing.assert_allclose(
        nominal_before - nominal_after, expected, atol=1e-6
    )
    su_before = a["su_2a2c"] / a["inflation_factor"] / scale / 4
    su_after = b["su_2a2c"] / b["inflation_factor"] / scale / 4
    su_expected = removed.loc[
        a.index, ["other_lodging", "rent_as_pay", "vacation_home_principal"]
    ].sum(axis=1)
    np.testing.assert_allclose(su_before - su_after, su_expected, atol=1e-6)


@PROPERTY
@given(seed=st.integers(0, 10_000))
def test_definition_applied_twice_changes_nothing(seed):
    once = apply_bls_paper_definition(definition_frame(seed))
    twice = apply_bls_paper_definition(once)
    pd.testing.assert_frame_equal(once, twice)
    assert (removed_by_bls_paper_definition(once).to_numpy() == 0).all()


def test_definition_with_nothing_to_remove_reproduces_the_thresholds():
    raw = definition_frame(11)
    for stem in ("OTHLOD", "RNTAPY", "FDMAP"):
        for suffix in ("PQ", "CQ"):
            raw[f"{stem}{suffix}"] = 0.0
    raw["MRTPRNOP"] = raw["MRTPRNOC"] = 0.0
    for suffix in ("PQ", "CQ"):
        raw[f"SHELT{suffix}"] = raw[f"OWNDWE{suffix}"] + raw[f"RNTXRP{suffix}"]
    before = prepare_out_of_pocket(raw, 2024, cpi_series=flat_cpi())
    after = prepare_out_of_pocket(
        apply_bls_paper_definition(raw), 2024, cpi_series=flat_cpi()
    )
    assert after.result["thresholds"] == before.result["thresholds"]


def test_definition_keeps_missing_food_missing():
    raw = definition_frame(13)
    raw.loc[raw.index[:3], ["FOODPQ", "FDAWAYPQ"]] = np.nan
    out = apply_bls_paper_definition(raw)
    assert out["FOODPQ"].iloc[:3].isna().all()
    assert out["FDAWAYPQ"].iloc[:3].isna().all()
    assert out["FOODPQ"].iloc[3:].notna().all()


def test_definition_needs_its_columns():
    raw = definition_frame(17).drop(columns=["OTHLODPQ"])
    with pytest.raises(ValueError, match="OTHLODPQ"):
        apply_bls_paper_definition(raw)


def test_definition_columns_cover_the_pieces():
    raw = definition_frame(19)
    assert set(DEFINITION_COLUMNS) <= set(raw.columns)


@PROPERTY
@given(seed=st.integers(0, 10_000))
def test_shelter_pieces_sum_to_shelter(seed):
    frame = staged(seed)
    pieces = shelter_pieces(frame)
    np.testing.assert_allclose(
        pieces.sum(axis=1), unit_components(frame)["shelter"]
    )
    band = band_definition_pieces(frame)
    components = band_components(frame)
    shelter_names = [p for p in band["pooled"] if p != "meals_as_pay"]
    assert sum(band["pooled"][p] for p in shelter_names) == pytest.approx(
        components.pooled["shelter"], rel=1e-9
    )
    for tenure in TENURES:
        assert sum(band[tenure][p] for p in shelter_names) == pytest.approx(
            components.by_tenure[tenure]["shelter"], rel=1e-9
        )


def test_shelter_pieces_reject_a_frame_that_fails_the_identity():
    raw = definition_frame(23)
    raw["SHELTPQ"] = raw["SHELTPQ"] + 1.0
    run = prepare_out_of_pocket(raw, 2024, cpi_series=flat_cpi())
    with pytest.raises(ValueError, match="pieces"):
        shelter_pieces(run.expenditures)
