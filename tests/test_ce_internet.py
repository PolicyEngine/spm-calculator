"""Home internet in the CE in-kind replication (``ce_internet``).

Invariants:

1. Zero internet spending reproduces the out-of-pocket run exactly, and an
   all-zero in-kind table reproduces the run with home internet exactly.
2. Without an internet weight, the composite price factor equals
   ``get_fcsuti_inflation_factor`` exactly; when every series is the same
   index, the factor is that index's ratio whatever the weights. With every
   other series flat, the factor is ``1 - w + w * r``, where ``w`` is
   internet's weight and ``r`` the ratio of CUUR0000SEEE03 between the
   two years.
3. Internet's CPI weight is its spending share among units with children,
   as ``compute_fcsuti_weights_from_ce`` would give it.
4. Internet enters FCSUti at its three-month cost times the run's
   annualization factor, as the FMLI ``*PQ`` + ``*CQ`` pairs do (4 under
   the default ``quarter4``, 2 under the legacy ``pqcq2``), and leaves
   SU's spending alone.
5. Unit costs equal the sum of their MTBI UCC 690114 records, in the same
   bundle and quarter as the FMLI file.
6. The committed receipts keep three stages apart: the archived
   out-of-pocket thresholds, those with home internet, and those with home
   internet and in-kind benefits. No imputed total includes internet.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from spm_calculator import ce_threshold
from spm_calculator.ce_bls_shares import (
    ACCOUNTINGS,
    IMPUTED,
    band_components,
    unit_components,
)
from spm_calculator.ce_decomposition import BLS_FCSUTI_INDEX, TENURES
from spm_calculator.ce_inkind_stage import (
    IN_KIND_OMITTED,
    OMITTED_APPROXIMATION,
    OutOfPocketRun,
    add_in_kind,
    prepare_out_of_pocket,
    replicate_with_in_kind,
    zero_in_kind,
)
from spm_calculator.ce_internet import (
    INTERNET_COLUMN,
    INTERNET_COMPONENT,
    INTERNET_CPI_RECEIPT,
    INTERNET_CPI_SERIES,
    INTERNET_UCC,
    METHODOLOGY_PREFIX,
    add_home_internet,
    composite_inflation_factor,
    internet_cpi_weights,
    load_internet_cpi,
    mtbi_member,
    read_internet_costs,
    with_internet_cpi,
)
from spm_calculator.ce_replicates import (
    IDENTITY_TOLERANCE,
    replicate_estimates,
    reweight,
)
from spm_calculator.fcsuti_cpi import (
    CPI_SERIES,
    FCSUTI_WEIGHTS,
    compute_fcsuti_weights_from_ce,
    get_fcsuti_inflation_factor,
)
from tests.test_ce_inkind import PROPERTY, STAGE_COLUMNS, ce_frame, flat_cpi

ROOT = Path(__file__).resolve().parent.parent
CPI_STORE = ROOT / "spm_calculator/data/bls/cpi_annual.json"
CURRENT = ROOT / "spm_calculator/data/current"
ARCHIVED_RECEIPT = CURRENT / "ce_replication_2019_2025.json"
REPLICATION_RECEIPT = CURRENT / "ce_inkind_replication_2019_2025.json"
COMPONENTS_RECEIPT = CURRENT / "ce_inkind_bls_components_2019_2025.json"


def pinned_cpi():
    store = json.loads(CPI_STORE.read_text())["series"]
    series = {
        sid: pd.Series({int(year): value for year, value in values.items()})
        for sid, values in store.items()
    }
    return with_internet_cpi(series)


def with_internet(raw: pd.DataFrame, seed: int, share: float = 0.7):
    rng = np.random.default_rng(seed + 1)
    frame = raw.copy()
    cost = rng.uniform(0, 400, len(frame))
    cost[rng.uniform(size=len(frame)) > share] = 0.0
    frame[INTERNET_COLUMN] = cost
    return frame


def flat_with_internet():
    return with_internet_cpi(
        flat_cpi(), pd.Series({year: 100.0 for year in range(2014, 2027)})
    )


# Invariant 1


@PROPERTY
@given(seed=st.integers(0, 10_000))
def test_zero_internet_reproduces_out_of_pocket_exactly(seed):
    raw = with_internet(ce_frame(seed, year=2021), seed, share=0.0)
    raw.loc[raw.index[: len(raw) // 2], "ce_year"] = 2022
    cpi = pinned_cpi()
    run = prepare_out_of_pocket(raw, 2024, cpi_series=cpi)
    expanded = add_home_internet(run, cpi)
    pd.testing.assert_frame_equal(
        expanded.expenditures, run.expenditures, check_exact=True
    )
    assert expanded.result["thresholds"] == run.result["thresholds"]
    assert expanded.result["estimation"] == run.result["estimation"]
    construction = expanded.result["construction"]
    assert (
        construction["cpi_component_weights"]
        == (run.result["construction"]["cpi_component_weights"])
    )
    assert (
        construction["inflation_factors"]
        == (run.result["construction"]["inflation_factors"])
    )
    assert expanded.result["without_home_internet"] == {
        "methodology_id": run.result["methodology_id"],
        "thresholds": run.result["thresholds"],
    }


def test_runs_with_internet_have_their_own_identity():
    raw = with_internet(ce_frame(3), 3)
    cpi = flat_with_internet()
    run = prepare_out_of_pocket(raw, 2024, cpi_series=cpi)
    expanded = add_home_internet(run, cpi)
    assert expanded.result["methodology_id"].startswith(METHODOLOGY_PREFIX)
    config = dict(expanded.result["methodology_config"])
    assert config.pop("home_internet")["ucc"] == INTERNET_UCC
    assert config == run.result["methodology_config"]
    approximations = expanded.result["construction"]["approximations"]
    assert "BLS in-kind benefit imputations omitted" in approximations
    assert not any("home internet" in item for item in approximations)
    assert not any("quarterly treatment" in item for item in approximations)
    staged = replicate_with_in_kind(expanded, zero_in_kind(raw["NEWID"]))
    assert staged["thresholds"] == expanded.result["thresholds"]
    assert (
        staged["out_of_pocket"]["thresholds"]
        == (expanded.result["thresholds"])
    )
    assert (
        staged["without_home_internet"]["thresholds"]
        == (run.result["thresholds"])
    )
    assert (
        "in-kind benefits from the in-kind stage"
        in (staged["construction"]["approximations"])
    )
    assert "home_internet" in staged["methodology_config"]


@PROPERTY
@given(seed=st.integers(0, 10_000))
def test_zero_in_kind_reproduces_the_internet_run_exactly(seed):
    raw = with_internet(ce_frame(seed, year=2021), seed)
    raw.loc[raw.index[: len(raw) // 2], "ce_year"] = 2022
    cpi = pinned_cpi()
    expanded = add_home_internet(
        prepare_out_of_pocket(raw, 2024, cpi_series=cpi), cpi
    )
    zero = replicate_with_in_kind(expanded, zero_in_kind(raw["NEWID"]))
    assert zero["thresholds"] == expanded.result["thresholds"]
    assert zero["estimation"] == expanded.result["estimation"]
    frame, _ = add_in_kind(expanded.expenditures, zero_in_kind(raw["NEWID"]))
    for column in STAGE_COLUMNS:
        np.testing.assert_array_equal(
            frame[column], expanded.expenditures[column]
        )


def test_expenditures_must_carry_internet():
    raw = ce_frame(4)
    cpi = flat_with_internet()
    run = prepare_out_of_pocket(raw, 2024, cpi_series=cpi)
    with pytest.raises(ValueError, match=INTERNET_COLUMN):
        add_home_internet(run, cpi)


@pytest.mark.parametrize("cpi", [None, "without_internet"])
def test_home_internet_needs_the_internet_cpi(cpi):
    """A missing internet series raises a ValueError that names it, not a
    TypeError or KeyError from deep in the composite."""
    raw = with_internet(ce_frame(5), 5)
    run = prepare_out_of_pocket(raw, 2024, cpi_series=flat_cpi())
    series = flat_cpi() if cpi == "without_internet" else None
    with pytest.raises(ValueError, match=INTERNET_CPI_SERIES):
        add_home_internet(run, series)


# Invariant 2


@pytest.mark.parametrize("from_year", range(2014, 2026))
def test_composite_matches_the_package_factor_without_internet(from_year):
    cpi = pinned_cpi()
    weights = compute_fcsuti_weights_from_ce(ce_frame(from_year))
    for to_year in (2019, 2022, 2025):
        assert composite_inflation_factor(
            from_year, to_year, weights, cpi
        ) == get_fcsuti_inflation_factor(
            from_year, to_year, weights=weights, cpi_series=cpi
        )


@PROPERTY
@given(seed=st.integers(0, 10_000))
def test_one_index_for_every_series_gives_its_ratio(seed):
    raw = with_internet(ce_frame(seed), seed)
    index = pd.Series(BLS_FCSUTI_INDEX)
    cpi = {sid: index for sid in [*CPI_SERIES.values(), INTERNET_CPI_SERIES]}
    weights = internet_cpi_weights(raw, compute_fcsuti_weights_from_ce(raw))
    for year in range(2014, 2025):
        assert composite_inflation_factor(
            year, 2025, weights, cpi
        ) == pytest.approx(index[2025] / index[year], rel=1e-12)


def rising_internet():
    return pd.Series(
        {year: 100.0 + (year - 2014) ** 2 for year in range(2014, 2027)}
    )


def test_internet_is_priced_with_seee03():
    assert INTERNET_CPI_SERIES == "CUUR0000SEEE03"
    assert pinned_cpi()[INTERNET_CPI_SERIES].equals(load_internet_cpi())


@PROPERTY
@given(
    weight=st.floats(0.001, 0.2),
    from_year=st.integers(2014, 2025),
    to_year=st.integers(2014, 2025),
)
def test_internet_series_alone_moves_a_flat_composite(
    weight, from_year, to_year
):
    internet = rising_internet()
    cpi = with_internet_cpi(flat_cpi(), internet)
    weights = {c: w * (1 - weight) for c, w in FCSUTI_WEIGHTS.items()}
    weights[INTERNET_COMPONENT] = weight
    expected = (1 - weight) + weight * internet[to_year] / internet[from_year]
    assert composite_inflation_factor(
        from_year, to_year, weights, cpi
    ) == pytest.approx(expected, rel=1e-12)


def test_internet_series_reaches_every_unit_price_factor():
    raw = with_internet(ce_frame(5, year=2021), 5)
    raw.loc[raw.index[: len(raw) // 2], "ce_year"] = 2022
    internet = rising_internet()
    cpi = with_internet_cpi(flat_cpi(), internet)
    expanded = add_home_internet(
        prepare_out_of_pocket(raw, 2024, cpi_series=cpi), cpi
    )
    construction = expanded.result["construction"]
    weight = construction["cpi_component_weights"][INTERNET_COMPONENT]
    assert weight > 0
    factors = construction["inflation_factors"]
    assert sorted(factors) == [2021, 2022]
    for year, factor in factors.items():
        assert factor == pytest.approx(
            (1 - weight) + weight * internet[2024] / internet[year],
            rel=1e-12,
        )
    np.testing.assert_array_equal(
        expanded.expenditures["inflation_factor"],
        expanded.expenditures["ce_year"].map(factors),
    )


# Invariant 3


@PROPERTY
@given(seed=st.integers(0, 10_000))
def test_internet_weight_is_its_spending_share(seed):
    """Moving internet into apparel's columns gives the same total."""
    raw = with_internet(ce_frame(seed), seed)
    weights = internet_cpi_weights(raw, compute_fcsuti_weights_from_ce(raw))
    merged = raw.copy()
    merged["APPARCQ"] = merged["APPARCQ"] + merged[INTERNET_COLUMN]
    expected = compute_fcsuti_weights_from_ce(merged)
    assert sum(weights.values()) == pytest.approx(1.0, rel=1e-12)
    for component, value in expected.items():
        mine = weights[component]
        if component == "apparel":
            mine += weights["internet"]
        assert mine == pytest.approx(value, rel=1e-12)


def test_no_internet_spending_keeps_the_weights():
    raw = with_internet(ce_frame(5), 5, share=0.0)
    weights = compute_fcsuti_weights_from_ce(raw)
    assert internet_cpi_weights(raw, weights) == weights


def test_internet_weight_ignores_units_without_children():
    raw = with_internet(ce_frame(6), 6, share=1.0)
    raw.loc[raw.index[::4], "PERSLT18"] = 0
    weights = compute_fcsuti_weights_from_ce(raw)
    childless = raw["PERSLT18"] == 0
    louder = raw.copy()
    for column in (INTERNET_COLUMN, "TELEPHPQ", "TELEPHCQ"):
        louder.loc[childless, column] = (
            50 * louder.loc[childless, column] + 1_000
        )
    expected = internet_cpi_weights(raw, weights)
    assert expected[INTERNET_COMPONENT] > 0
    assert internet_cpi_weights(louder, weights) == expected


# Invariant 4


def test_internet_shifts_thresholds_by_known_amounts():
    """Identical families at flat prices: the lift is analytic."""
    raw = ce_frame(11).iloc[:3].copy()
    for column in raw.columns:
        if column.endswith(("PQ", "CQ")):
            raw[column] = 0.0
    raw["FOODPQ"] = raw["FOODCQ"] = 100.0
    raw["SHELTPQ"] = raw["SHELTCQ"] = 300.0
    raw["TELEPHPQ"] = raw["TELEPHCQ"] = 20.0
    raw["UTILPQ"] = raw["UTILCQ"] = 20.0
    raw["PERSLT18"], raw["FAM_SIZE"] = 2, 4
    raw[INTERNET_COLUMN] = 150.0
    cpi = flat_with_internet()
    run = prepare_out_of_pocket(raw, 2023, cpi_series=cpi)
    expanded = add_home_internet(run, cpi)
    fcsuti = 4 * (100 + 100 + 300 + 300 + 20 + 20)
    for tenure in TENURES:
        assert run.result["thresholds"][tenure] == pytest.approx(
            0.82 * 1.2 * fcsuti
        )
        assert expanded.result["thresholds"][tenure] == pytest.approx(
            0.82 * 1.2 * (fcsuti + 4 * 150)
        )
    np.testing.assert_allclose(
        expanded.expenditures["su_2a2c"], run.expenditures["su_2a2c"]
    )


@PROPERTY
@given(seed=st.integers(0, 10_000))
def test_su_keeps_its_spending_at_the_new_price_factor(seed):
    raw = with_internet(ce_frame(seed, year=2020), seed)
    raw.loc[raw.index[::3], "ce_year"] = 2023
    cpi = pinned_cpi()
    run = prepare_out_of_pocket(raw, 2024, cpi_series=cpi)
    expanded = add_home_internet(run, cpi)
    before, after = run.expenditures, expanded.expenditures
    np.testing.assert_allclose(
        after["su_2a2c"] / after["inflation_factor"],
        before["su_2a2c"] / before["inflation_factor"],
        rtol=1e-12,
    )
    np.testing.assert_allclose(
        after["fcsuti_threshold_year"] / after["inflation_factor"],
        before["fcsuti"] + 4 * before[INTERNET_COLUMN],
        rtol=1e-12,
    )
    untouched = [
        c
        for c in before.columns
        if c
        not in (
            "fcsuti",
            "inflation_factor",
            "fcsuti_threshold_year",
            "fcsuti_2a2c",
            "su_2a2c",
        )
    ]
    pd.testing.assert_frame_equal(after[untouched], before[untouched])


@pytest.mark.parametrize(
    ("annualization", "factor"), [("quarter4", 4.0), ("pqcq2", 2.0)]
)
def test_internet_follows_the_runs_annualization(annualization, factor):
    raw = with_internet(ce_frame(12, year=2021), 12)
    cpi = flat_with_internet()
    run = prepare_out_of_pocket(
        raw, 2023, annualization=annualization, cpi_series=cpi
    )
    expanded = add_home_internet(run, cpi)
    np.testing.assert_allclose(
        expanded.expenditures["fcsuti"],
        run.expenditures["fcsuti"]
        + factor * run.expenditures[INTERNET_COLUMN],
        rtol=1e-12,
    )


def test_home_internet_cannot_be_added_twice():
    raw = with_internet(ce_frame(13), 13)
    cpi = flat_with_internet()
    expanded = add_home_internet(
        prepare_out_of_pocket(raw, 2024, cpi_series=cpi), cpi
    )
    with pytest.raises(ValueError, match="does not omit home internet"):
        add_home_internet(expanded, cpi)


def test_stage_replaces_each_omission_in_place():
    raw = with_internet(ce_frame(14), 14)
    cpi = flat_with_internet()
    run = prepare_out_of_pocket(raw, 2024, cpi_series=cpi)
    expanded = add_home_internet(run, cpi)
    replaced = {
        "home internet and BLS in-kind benefit imputations omitted": (
            "home internet omitted; in-kind benefits from the in-kind stage"
        ),
        "BLS in-kind benefit imputations omitted": (
            "in-kind benefits from the in-kind stage"
        ),
    }
    for base, omission in zip((run, expanded), replaced):
        before = base.result["construction"]["approximations"]
        assert omission in before
        staged = replicate_with_in_kind(base, zero_in_kind(raw["NEWID"]))
        after = staged["construction"]["approximations"]
        assert after == [replaced.get(item, item) for item in before]


def test_stage_appends_the_omission_its_run_would_carry():
    raw = with_internet(ce_frame(14), 14)
    cpi = flat_with_internet()
    run = prepare_out_of_pocket(raw, 2024, cpi_series=cpi)
    expanded = add_home_internet(run, cpi)
    appended = {
        OMITTED_APPROXIMATION: (
            "home internet omitted; in-kind benefits from the in-kind stage"
        ),
        IN_KIND_OMITTED: "in-kind benefits from the in-kind stage",
    }
    for base, expected in zip((run, expanded), appended.values()):
        construction = base.result["construction"]
        kept = [
            item
            for item in construction["approximations"]
            if item not in appended
        ]
        bare = OutOfPocketRun(
            result={
                **base.result,
                "construction": {**construction, "approximations": kept},
            },
            expenditures=base.expenditures,
            median_share=base.median_share,
        )
        staged = replicate_with_in_kind(bare, zero_in_kind(raw["NEWID"]))
        assert staged["construction"]["approximations"] == [*kept, expected]


# Invariant 5


def _write_bundle(path: Path, members: dict[str, pd.DataFrame]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, frame in members.items():
            archive.writestr(name, frame.to_csv(index=False))
    return path


def test_costs_sum_every_record_for_the_ucc(tmp_path):
    fmli = pd.DataFrame({"NEWID": [101, 102, 103]})
    mtbi = pd.DataFrame(
        {
            "NEWID": [101, 101, 102, 103, 103],
            "UCC": ["690114", "690114", "690116", "270102", "690114"],
            "COST": [40.0, 25.5, 99.0, 80.0, 60.0],
        }
    )
    bundle = _write_bundle(
        tmp_path / "intrvw19.zip",
        {"intrvw19/fmli192.csv": fmli, "intrvw19/mtbi192.csv": mtbi},
    )
    fmli.attrs["source"] = {
        "bundle_path": str(bundle),
        "member": "intrvw19/fmli192.csv",
    }
    costs = read_internet_costs(fmli)
    assert costs.tolist() == [65.5, 0.0, 60.0]
    assert costs.name == INTERNET_COLUMN


def test_costs_reject_units_missing_from_fmli(tmp_path):
    fmli = pd.DataFrame({"NEWID": [101]})
    mtbi = pd.DataFrame({"NEWID": [999], "UCC": [690114], "COST": [10.0]})
    bundle = _write_bundle(
        tmp_path / "b.zip", {"fmli191x.csv": fmli, "mtbi191x.csv": mtbi}
    )
    fmli.attrs["source"] = {
        "bundle_path": str(bundle),
        "member": "fmli191x.csv",
    }
    with pytest.raises(ValueError, match="not in fmli191x.csv"):
        read_internet_costs(fmli)


def _costs_from(tmp_path, fmli: pd.DataFrame, mtbi: pd.DataFrame):
    bundle = _write_bundle(
        tmp_path / "c.zip", {"fmli192.csv": fmli, "mtbi192.csv": mtbi}
    )
    fmli.attrs["source"] = {
        "bundle_path": str(bundle),
        "member": "fmli192.csv",
    }
    return read_internet_costs(fmli)


def test_costs_keep_negative_records(tmp_path):
    fmli = pd.DataFrame({"NEWID": [101, 102]})
    mtbi = pd.DataFrame(
        {"NEWID": [101, 101, 102], "UCC": [690114] * 3, "COST": [50, -10, -5]}
    )
    assert _costs_from(tmp_path, fmli, mtbi).tolist() == [40.0, -5.0]


def test_costs_reject_repeated_newids(tmp_path):
    fmli = pd.DataFrame({"NEWID": [101, 101]})
    mtbi = pd.DataFrame({"NEWID": [101], "UCC": [690114], "COST": [10.0]})
    with pytest.raises(ValueError, match="NEWID repeats"):
        _costs_from(tmp_path, fmli, mtbi)


@pytest.mark.parametrize("bad", [np.inf, np.nan])
def test_costs_reject_nonfinite_values(tmp_path, bad):
    fmli = pd.DataFrame({"NEWID": [101]})
    mtbi = pd.DataFrame({"NEWID": [101], "UCC": [690114], "COST": [bad]})
    with pytest.raises(ValueError, match="must be finite"):
        _costs_from(tmp_path, fmli, mtbi)


def test_mtbi_member_sits_beside_fmli():
    assert mtbi_member("intrvw17/intrvw17/fmli172.csv") == (
        "intrvw17/intrvw17/mtbi172.csv"
    )
    assert mtbi_member("FMLI191X.CSV") == "MTBI191X.CSV"
    with pytest.raises(ValueError):
        mtbi_member("intrvw19/memi192.csv")


@pytest.mark.parametrize(
    ("year", "quarter"), [(2017, 2), (2019, 1), (2024, 3)]
)
def test_costs_equal_the_mtbi_records(year, quarter):
    cache = ce_threshold._default_cache_dir()
    try:
        fmli = ce_threshold.load_ce_quarter(
            year, quarter, cache_dir=cache, allow_download=False
        )
    except FileNotFoundError:
        pytest.skip("CE bundle not cached")
    costs = read_internet_costs(fmli)
    member = Path(fmli.attrs["source"]["member"]).name
    mtbi = ce_threshold._read_bundle_member(
        Path(fmli.attrs["source"]["bundle_path"]), mtbi_member(member)
    )
    rows = mtbi[mtbi["UCC"].astype(str).str.strip() == str(INTERNET_UCC)]
    expected = rows.groupby("NEWID")["COST"].sum()
    by_unit = pd.Series(costs.to_numpy(), index=fmli["NEWID"].to_numpy())
    assert (
        by_unit[by_unit != 0]
        .sort_index()
        .round(6)
        .equals(expected[expected != 0].sort_index().astype(float).round(6))
    )
    assert np.isclose(by_unit.sum(), rows["COST"].sum())


# The pinned price series


def test_internet_cpi_is_the_pinned_bls_response():
    series = load_internet_cpi()
    assert series.name == INTERNET_CPI_SERIES
    assert list(series.index) == list(range(2005, 2026))
    assert series[2019] == 77.090
    assert series[2025] == 85.686
    document = json.loads(INTERNET_CPI_RECEIPT.read_text())
    assert document["generated_by"] == "scripts/fetch_internet_cpi.py"
    assert all(
        exchange["response"]["status"] == "REQUEST_SUCCEEDED"
        for exchange in document["exchanges"]
    )


def test_internet_cpi_is_added_once():
    cpi = pinned_cpi()
    with pytest.raises(ValueError, match="already present"):
        with_internet_cpi(cpi)


# The replicate path


@PROPERTY
@given(seed=st.integers(0, 10_000))
def test_replicates_add_internet_as_the_public_run_does(seed):
    """Each replicate with internet equals add_home_internet on its sample."""
    frame = with_internet(ce_frame(seed, n=120, year=2021), seed)
    frame.loc[frame.index[::2], "ce_year"] = 2023
    cpi = pinned_cpi()
    tables = [
        zero_in_kind(frame["NEWID"]),
    ]
    rng = np.random.default_rng(seed)
    full = frame["FINLWT21"].to_numpy(dtype=float)
    # Uneven factors, so each replicate's CPI shares differ from the full
    # sample's and a replicate priced with full-sample weights fails.
    keep = rng.integers(0, 2, (len(frame), 2)).astype(bool)
    weights = np.where(
        keep, full[:, None] * rng.uniform(0.3, 1.9, (len(frame), 2)), 0
    )
    estimates = replicate_estimates(
        frame, 2024, tables, weights=weights, cpi_series=cpi
    )
    assert estimates.identity_gap <= IDENTITY_TOLERANCE
    for position in range(3):
        sample = (
            frame
            if position == 0
            else reweight(frame, weights[:, position - 1])
        )
        run = add_home_internet(
            prepare_out_of_pocket(sample, 2024, cpi_series=cpi), cpi
        )
        assert estimates.without[position] == run.result["thresholds"]
        assert estimates.with_stage[0][position] == run.result["thresholds"]
        assert run.result["construction"]["home_internet"]["cpi_weight"] > 0
        band = band_components(run.expenditures)
        assert band.threshold("renter") == pytest.approx(
            run.result["thresholds"]["renter"], rel=IDENTITY_TOLERANCE
        )


@PROPERTY
@given(seed=st.integers(0, 10_000))
def test_unit_components_carry_internet_at_four_times_its_cost(seed):
    """Internet is its own component, outside every imputed term, and the
    components still sum to FCSUti."""
    frame = with_internet(ce_frame(seed, n=80, year=2021), seed)
    cpi = pinned_cpi()
    expanded = add_home_internet(
        prepare_out_of_pocket(frame, 2023, cpi_series=cpi), cpi
    ).expenditures
    components = unit_components(expanded)
    np.testing.assert_allclose(
        components["internet"],
        4
        * expanded[INTERNET_COLUMN]
        * expanded["inflation_factor"]
        * (ce_threshold.REFERENCE_RAW_SCALE / expanded["equiv_scale"]),
        rtol=1e-12,
    )
    assert "internet" not in IMPUTED
    assert (components[list(IMPUTED)] == 0).all().all()


def test_unit_components_reject_internet_left_out_of_fcsuti():
    """An out-of-pocket frame carries the internet column, but its FCSUti
    leaves home internet out; unit_components says so."""
    frame = with_internet(ce_frame(21, n=80, year=2021), 21, share=1.0)
    cpi = pinned_cpi()
    run = prepare_out_of_pocket(frame, 2023, cpi_series=cpi)
    assert (run.expenditures[INTERNET_COLUMN] > 0).any()
    with pytest.raises(ValueError, match="leaves home internet out"):
        unit_components(run.expenditures)
    unit_components(run.expenditures.drop(columns=INTERNET_COLUMN))


# Invariant 6: the committed receipts


def test_replication_receipt_separates_internet_from_benefits():
    """The first stage is the archived replication; each stage's effect
    follows from the recorded thresholds."""
    receipt = json.loads(REPLICATION_RECEIPT.read_text())
    archived = json.loads(ARCHIVED_RECEIPT.read_text())
    for target, result in receipt["results"].items():
        expected = archived["results"][target]["variants"][
            "exclude_unresolved"
        ]
        assert result["without_home_internet"] == expected["thresholds"]
        assert (
            result["methodology_id_without_home_internet"]
            == expected["methodology_id"]
        )
        assert result["methodology_id_without"].startswith(METHODOLOGY_PREFIX)
        effects = result["stage_effects"]
        for tenure in TENURES:
            base = result["without_home_internet"][tenure]
            internet = result["without_in_kind"][tenure]
            both = result["with_in_kind"][tenure]
            assert effects["home_internet_dollars"][tenure] == internet - base
            assert effects["home_internet_percent"][tenure] == pytest.approx(
                100 * (internet / base - 1), rel=1e-12
            )
            assert effects["in_kind_dollars"][tenure] == both - internet
            assert (
                effects["in_kind_percent"][tenure]
                == result["in_kind_lift_percent"][tenure]
            )
        home = result["home_internet"]
        assert home["ucc"] == INTERNET_UCC
        assert home["cpi_series"] == INTERNET_CPI_SERIES
        assert home["units_with_negative_cost"] == 0
        assert 0 < home["weighted_share_reporting"] < 1
        weights = result["cpi_component_weights"]
        assert weights["internet"] == home["cpi_weight"] > 0
        assert sum(weights.values()) == pytest.approx(1, abs=1e-12)
        deflated = result["fcsuti_deflated"]
        assert set(deflated["without_home_internet"]) == set(TENURES)


def test_components_receipt_keeps_internet_out_of_imputed_totals():
    """Every imputed total is the five benefits alone; the internet record
    sets ours beside BLS's in both accountings; and each run's first stage
    matches the replication receipt."""
    receipt = json.loads(COMPONENTS_RECEIPT.read_text())
    replication = json.loads(REPLICATION_RECEIPT.read_text())["results"]
    for year in receipt["bls"]["years"].values():
        pooled = year["band"]["pooled"]
        assert year["imputed_total"] == pytest.approx(
            sum(pooled[c] for c in IMPUTED), rel=1e-12
        )
    first_stage = {
        "package": lambda r: r["without_home_internet"],
        "fcsuti": lambda r: r["fcsuti_deflated"]["without_home_internet"],
    }
    for name, run in receipt["runs"].items():
        for target, year in run["years"].items():
            if name in first_stage:
                assert year["without_home_internet"]["thresholds"] == (
                    first_stage[name](replication[target])
                )
            stage = year["with_in_kind"]
            pooled = stage["band"]["pooled"]
            assert pooled["internet"] > 0
            assert stage["imputed_total"] == pytest.approx(
                sum(pooled[c] for c in IMPUTED), rel=1e-12
            )
            published = receipt["bls"]["years"][target]["published_thresholds"]
            record = year["home_internet"]
            assert sorted(record) == sorted(ACCOUNTINGS)
            for accounting in ACCOUNTINGS:
                assert sorted(record[accounting]) == sorted(TENURES)
                for tenure, entry in record[accounting].items():
                    assert entry["ours_percent_of_threshold"] == pytest.approx(
                        100
                        * entry["ours_dollars"]
                        / stage["thresholds"][tenure],
                        rel=1e-12,
                    )
                    assert entry["bls_percent_of_threshold"] == pytest.approx(
                        100 * entry["bls_dollars"] / published[tenure],
                        rel=1e-12,
                    )
            for accounting in year["level_gap_percent_of_bls"].values():
                for gap in accounting.values():
                    assert gap["imputed"] == pytest.approx(
                        sum(gap["terms"][c] for c in IMPUTED), rel=1e-12
                    )
