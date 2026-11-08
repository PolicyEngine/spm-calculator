"""Tests for the step 1 reproduction of Census's 2025 SPM estimates.

Three kinds of test live here:

- property tests of the estimators on synthetic SPM units (Hypothesis);
- tests of the bundled P60-290 workbooks and their parser;
- tests of the committed results file: identities, stated tolerances, the
  claims the note makes in prose, and the note's generated blocks.

A last test rebuilds every number from the public-use zip. It runs only when
the zip sits in the package's ASEC cache and
``SPM_CALCULATOR_CENSUS_SPM_REBUILD=1`` is set.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from spm_calculator import census_spm as c
from spm_calculator import census_spm_report as report

ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = ROOT / "spm_calculator/data/census_spm/reproduction_2025.json"
NOTE_PATH = ROOT / "docs/census-spm-reproduction.md"
SCRIPT_PATH = ROOT / "scripts/reproduce_census_spm.py"

PROPERTY_SETTINGS = settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

UNIT_COLUMNS = sorted({col for e in c.ELEMENTS for col in e.unit_columns})
PERSON_COLUMNS = sorted({col for e in c.ELEMENTS for col in e.person_columns})


# ---------------------------------------------------------------------------
# Synthetic SPM units
# ---------------------------------------------------------------------------


@st.composite
def synthetic_persons(draw, max_units: int = 10, allow_negative=False):
    """People in SPM units, with resources, thresholds, elements, weights.

    Resources sit at, just below or just above the threshold often enough
    for ties to occur.
    """
    n_units = draw(st.integers(1, max_units))
    sizes = draw(
        st.lists(st.integers(1, 4), min_size=n_units, max_size=n_units)
    )
    thresholds = draw(
        st.lists(st.integers(1, 60_000), min_size=n_units, max_size=n_units)
    )
    offsets = draw(
        st.lists(
            st.one_of(
                st.sampled_from([-1, 0, 1]), st.integers(-60_000, 60_000)
            ),
            min_size=n_units,
            max_size=n_units,
        )
    )
    seed = draw(st.integers(0, 2**32 - 1))
    rng = np.random.default_rng(seed)
    rows = []
    for unit, size in enumerate(sizes):
        unit_values = {
            col: float(rng.integers(0, 3) * rng.integers(0, 20_000))
            for col in UNIT_COLUMNS
        }
        if allow_negative:
            unit_values["SPM_STTAX"] = float(rng.integers(-5_000, 5_000))
        for member in range(size):
            row = {
                "SPM_ID": 1000 + unit,
                "SPM_HEAD": int(member == 0),
                "A_AGE": int(rng.integers(0, 90)),
                "SPM_POVTHRESHOLD": float(thresholds[unit]),
                "SPM_RESOURCES": float(thresholds[unit] + offsets[unit]),
                **unit_values,
            }
            for col in PERSON_COLUMNS:
                row[col] = float(rng.integers(0, 2) * rng.integers(0, 15_000))
            rows.append(row)
    persons = pd.DataFrame(rows)
    weight = rng.uniform(0.5, 3_000, size=len(persons))
    replicates = weight[:, None] * rng.uniform(
        0.0, 2.0, size=(len(persons), c.N_REPLICATES)
    )
    weights = pd.DataFrame(
        replicates, columns=list(c.REPLICATE_COLUMNS), index=persons.index
    )
    weights.insert(0, "weight", weight)
    return pd.concat([persons, weights], axis=1)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@PROPERTY_SETTINGS
@given(synthetic_persons())
def test_poor_exactly_when_unit_resources_fall_below_threshold(persons):
    flags = c.poverty_flags(
        persons["SPM_RESOURCES"].to_numpy(),
        persons["SPM_POVTHRESHOLD"].to_numpy(),
    )
    for unit, members in persons.groupby("SPM_ID"):
        resources = members["SPM_RESOURCES"].iloc[0]
        threshold = members["SPM_POVTHRESHOLD"].iloc[0]
        unit_flags = flags[members.index]
        # Every member shares the unit's status.
        assert unit_flags.all() or not unit_flags.any()
        # Poor exactly when resources fall strictly below the threshold.
        assert bool(unit_flags[0]) == (resources < threshold)


@given(
    st.floats(-1e6, 1e6, allow_nan=False),
    st.floats(0, 1e6, allow_nan=False),
)
def test_resources_equal_to_threshold_are_not_poor(resources, threshold):
    assert not c.poverty_flags(np.array([threshold]), np.array([threshold]))[0]
    assert c.poverty_flags(np.array([resources]), np.array([threshold]))[
        0
    ] == (resources < threshold)


@PROPERTY_SETTINGS
@given(synthetic_persons())
def test_group_rates_equal_weighted_averages(persons):
    weights = c.weight_matrix(persons)
    groups = c.age_groups(persons)
    flags = c.poverty_flags(
        persons["SPM_RESOURCES"].to_numpy(),
        persons["SPM_POVTHRESHOLD"].to_numpy(),
    )
    rates = c.group_rates(flags, groups, weights)
    assert rates.shape == (groups.shape[1], weights.shape[1])
    for g in range(groups.shape[1]):
        member = groups[:, g]
        for k in (0, 1, c.N_REPLICATES):
            w = weights[member, k]
            if w.sum() == 0:
                assert math.isnan(rates[g, k])
                continue
            expected = np.average(flags[member].astype(float), weights=w)
            assert rates[g, k] == pytest.approx(expected, rel=1e-12, abs=1e-12)
            assert 0.0 <= rates[g, k] <= 1.0


@PROPERTY_SETTINGS
@given(synthetic_persons(), st.floats(0.01, 1000))
def test_rates_ignore_weight_scale_and_totals_scale_with_it(persons, scale):
    weights = c.weight_matrix(persons)
    groups = c.age_groups(persons)
    flags = c.poverty_flags(
        persons["SPM_RESOURCES"].to_numpy(),
        persons["SPM_POVTHRESHOLD"].to_numpy(),
    ).astype(float)
    base_rates = c.group_rates(flags, groups, weights)
    scaled_rates = c.group_rates(flags, groups, weights * scale)
    np.testing.assert_allclose(
        scaled_rates, base_rates, rtol=1e-10, atol=1e-12
    )
    np.testing.assert_allclose(
        c.group_totals(flags, groups, weights * scale),
        scale * c.group_totals(flags, groups, weights),
        rtol=1e-10,
    )


@PROPERTY_SETTINGS
@given(synthetic_persons())
def test_totals_sum_poor_weights(persons):
    weights = c.weight_matrix(persons)
    flags = c.poverty_flags(
        persons["SPM_RESOURCES"].to_numpy(),
        persons["SPM_POVTHRESHOLD"].to_numpy(),
    )
    everyone = np.ones((len(persons), 1), dtype=bool)
    totals = c.group_totals(flags.astype(float), everyone, weights)
    np.testing.assert_allclose(
        totals[0], weights[flags].sum(axis=0), rtol=1e-12, atol=1e-9
    )


@given(
    st.lists(st.floats(-100, 100, allow_nan=False), min_size=2, max_size=40),
    st.floats(-10, 10, allow_nan=False),
    st.floats(-50, 50, allow_nan=False),
)
def test_replicate_se_matches_formula_and_transforms(values, a, b):
    theta = np.array(values)
    n = len(theta) - 1
    expected = math.sqrt(4.0 / n * sum((x - theta[0]) ** 2 for x in theta[1:]))
    assert c.replicate_se(theta) == pytest.approx(
        expected, rel=1e-9, abs=1e-12
    )
    # SE(a * theta + b) = |a| * SE(theta).
    assert c.replicate_se(a * theta + b) == pytest.approx(
        abs(a) * c.replicate_se(theta), rel=1e-9, abs=1e-9
    )
    assert c.margin_of_error(theta) == pytest.approx(
        1.645 * c.replicate_se(theta), rel=1e-12, abs=1e-12
    )
    # Replicates that equal the full-sample estimate give no error.
    assert c.replicate_se(np.full(len(theta), theta[0])) == 0.0


def test_replicate_se_uses_census_factor_for_160_replicates():
    theta = np.zeros(161)
    theta[1:] = 1.0
    # 4 / 160 * 160 = 4, so SE = 2.
    assert c.replicate_se(theta) == pytest.approx(2.0)
    assert c.REPLICATE_FACTOR == pytest.approx(4.0 / 160)


@given(
    st.lists(st.floats(-1e6, 1e6, allow_nan=False), min_size=1, max_size=20),
    st.data(),
)
def test_counterfactual_resources_round_trip(resources, data):
    r = np.array(resources)
    v = np.array(
        data.draw(
            st.lists(
                st.floats(0, 1e6, allow_nan=False),
                min_size=len(r),
                max_size=len(r),
            )
        )
    )
    np.testing.assert_allclose(
        c.counterfactual_resources(r, v, c.ADDITION) + v, r, atol=1e-6
    )
    np.testing.assert_allclose(
        c.counterfactual_resources(r, v, c.SUBTRACTION) - v, r, atol=1e-6
    )
    with pytest.raises(ValueError):
        c.counterfactual_resources(r, v, "neither")


@PROPERTY_SETTINGS
@given(synthetic_persons())
def test_element_values_sum_person_amounts_within_units(persons):
    for element in c.ELEMENTS:
        values = c.element_values(persons, element)
        expected = np.zeros(len(persons))
        for col in element.unit_columns:
            expected += persons[col].to_numpy()
        for col in element.person_columns:
            expected += (
                persons.groupby("SPM_ID")[col].transform("sum").to_numpy()
            )
        np.testing.assert_array_equal(values, expected)
        # Every member of a unit carries the unit's amount.
        per_unit = pd.Series(values).groupby(persons["SPM_ID"]).nunique()
        assert (per_unit == 1).all()


@PROPERTY_SETTINGS
@given(synthetic_persons())
def test_element_effects_have_the_signs_of_their_kind(persons):
    """Removing a nonnegative addition never lowers poverty; removing a
    nonnegative subtraction never raises it."""
    weights = c.weight_matrix(persons)
    effects = c.estimate_table5(persons, weights)
    for element in c.ELEMENTS:
        estimate = np.array(effects[element.key]["estimate"])
        finite = estimate[np.isfinite(estimate)]
        if element.kind == c.ADDITION:
            assert (finite <= 1e-9).all()
        else:
            assert (finite >= -1e-9).all()


@PROPERTY_SETTINGS
@given(synthetic_persons())
def test_zero_element_has_zero_effect(persons):
    zeroed = persons.copy()
    for col in UNIT_COLUMNS + PERSON_COLUMNS:
        zeroed[col] = 0.0
    effects = c.estimate_table5(zeroed)
    for element in c.ELEMENTS:
        for value in effects[element.key]["estimate"]:
            assert value == 0 or math.isnan(value)
        for value in effects[element.key]["moe"]:
            assert value == 0 or math.isnan(value)


@PROPERTY_SETTINGS
@given(synthetic_persons(allow_negative=True))
def test_state_tax_effect_equals_direct_computation(persons):
    """The state tax effect is the rate minus the rate with the tax added
    back to resources, whatever the tax's sign."""
    weights = c.weight_matrix(persons)
    groups = c.age_groups(persons)
    resources = persons["SPM_RESOURCES"].to_numpy()
    thresholds = persons["SPM_POVTHRESHOLD"].to_numpy()
    base = c.group_rates(
        c.poverty_flags(resources, thresholds), groups, weights
    )
    without = c.group_rates(
        c.poverty_flags(
            resources + persons["SPM_STTAX"].to_numpy(), thresholds
        ),
        groups,
        weights,
    )
    effects = c.estimate_table5(persons, weights)
    np.testing.assert_allclose(
        effects["state_income_tax"]["estimate"],
        100 * (base - without)[:, 0],
        rtol=1e-12,
        atol=1e-12,
    )


def test_negative_state_tax_gives_a_negative_effect():
    """A unit just above its threshold because of a net state tax credit
    falls below it when the credit goes: the effect is -100 points."""
    row = {col: 0.0 for col in UNIT_COLUMNS + PERSON_COLUMNS}
    row.update(
        SPM_ID=1,
        SPM_HEAD=1,
        A_AGE=40,
        SPM_RESOURCES=100.0,
        SPM_POVTHRESHOLD=90.0,
        SPM_STTAX=-20.0,
        weight=1.0,
        **{col: 1.0 for col in c.REPLICATE_COLUMNS},
    )
    effects = c.estimate_table5(pd.DataFrame([row]))
    assert effects["spm_rate"]["estimate"][0] == 0.0
    assert effects["state_income_tax"]["estimate"][0] == -100.0
    assert effects["state_income_tax"]["moe"][0] == 0.0


@given(
    st.dictionaries(
        st.sampled_from(
            [
                "SPM_TOTVAL",
                "SPM_SNAPSUB",
                "SPM_CAPHOUSESUB",
                "SPM_SCHLUNCH",
                "SPM_ENGVAL",
                "SPM_WICVAL",
                "SPM_FEDTAX",
                "SPM_STTAX",
                "SPM_FICA",
                "SPM_CAPWKCCXPNS",
                "SPM_MEDXPNS",
                "SPM_CHILDSUPPD",
            ]
        ),
        st.integers(-100_000, 100_000),
        min_size=12,
        max_size=12,
    ),
    st.integers(1, 10_000),
)
def test_resources_rise_with_additions_and_fall_with_subtractions(
    components, step
):
    additions = {
        "SPM_TOTVAL",
        "SPM_SNAPSUB",
        "SPM_CAPHOUSESUB",
        "SPM_SCHLUNCH",
        "SPM_ENGVAL",
        "SPM_WICVAL",
    }
    frame = pd.DataFrame([components])
    base = c.resources_from_components(frame).iloc[0]
    for col in components:
        bumped = frame.copy()
        bumped[col] += step
        change = c.resources_from_components(bumped).iloc[0] - base
        assert change == (step if col in additions else -step)


# ---------------------------------------------------------------------------
# The refundable CTC rule and its response to the EITC
# ---------------------------------------------------------------------------


@st.composite
def credit_units(draw, max_units: int = 12):
    """Tax units with children, earnings, payroll tax and credits.

    About half the units carry the credit the rule gives them, so that the
    response to the EITC is not masked.
    """
    n = draw(st.integers(1, max_units))
    rng = np.random.default_rng(draw(st.integers(0, 2**32 - 1)))
    earnings = rng.choice(
        [0.0, 1_000.0, 2_500.0, 4_000.0, 8_000.0, 30_000.0, 250_000.0],
        size=n,
    ) * rng.uniform(0.5, 1.5, size=n)
    units = pd.DataFrame(
        {
            "SPM_ID": rng.integers(0, max(1, (n + 1) // 2), size=n),
            "children": rng.integers(0, 6, size=n),
            "other_dependents": rng.integers(0, 3, size=n),
            "earnings": earnings,
            "payroll_tax": earnings
            * rng.choice([0.0, 0.0765, 0.1413, 0.3], size=n),
            "eitc": rng.integers(0, 3, size=n) * rng.uniform(0, 4_000, size=n),
            "nonrefundable_ctc": rng.integers(0, 2, size=n)
            * rng.uniform(0, 5_000, size=n),
        },
        index=pd.Index(np.arange(n) + 100, name="TAX_ID"),
    )
    rule = c.refundable_ctc_rule(units, units["eitc"].to_numpy())
    units["actc"] = np.where(
        rng.random(n) < 0.5, np.round(rule), rng.uniform(0, 5_000, size=n)
    )
    return units


@PROPERTY_SETTINGS
@given(credit_units())
def test_ctc_response_lies_between_zero_and_eitc_and_payroll_tax(units):
    response = c.ctc_response_to_eitc(units)
    assert (response >= 0).all()
    assert (response <= units["eitc"].to_numpy() + 1e-9).all()
    assert (response <= units["payroll_tax"].to_numpy() + 1e-9).all()


@PROPERTY_SETTINGS
@given(credit_units())
def test_ctc_response_needs_three_children_an_eitc_and_a_reproduced_credit(
    units,
):
    response = c.ctc_response_to_eitc(units)
    excluded = (
        (units["children"].to_numpy() < 3)
        | (units["eitc"].to_numpy() == 0)
        | ~c.rule_reproduces_credit(units)
    )
    assert (response[excluded] == 0).all()


@PROPERTY_SETTINGS
@given(credit_units(), st.floats(0, 10_000))
def test_refundable_ctc_rule_stays_in_its_cap_and_falls_with_the_eitc(
    units, extra
):
    eitc = units["eitc"].to_numpy()
    rule = c.refundable_ctc_rule(units, eitc)
    more = c.refundable_ctc_rule(units, eitc + extra)
    cap = c.CTC_2025["refundable_max_per_child"] * units["children"].to_numpy()
    assert (rule >= 0).all()
    assert (rule <= cap + 1e-9).all()
    assert (more <= rule + 1e-9).all()


def test_refundable_ctc_rule_matches_hand_computed_units():
    units = pd.DataFrame(
        {
            "SPM_ID": [1, 1, 2],
            "children": [3, 2, 3],
            "other_dependents": [0, 0, 1],
            "earnings": [3_000.0, 3_000.0, 40_000.0],
            "payroll_tax": [229.5, 229.5, 3_060.0],
            "eitc": [1_000.0, 1_000.0, 2_000.0],
            "nonrefundable_ctc": [0.0, 0.0, 1_000.0],
            "actc": [75.0, 75.0, 5_100.0],
        },
        index=pd.Index([10, 11, 12], name="TAX_ID"),
    )
    # 15% of earnings over $2,500 is $75 for the first two units. Without
    # its EITC, the first unit's payroll tax ($229.50) sets the credit; the
    # second has two children, and the third stays at its $5,100 cap.
    np.testing.assert_allclose(
        c.refundable_ctc_rule(units, units["eitc"].to_numpy()),
        [75.0, 75.0, 5_100.0],
    )
    np.testing.assert_allclose(c.ctc_response_to_eitc(units), [154.5, 0, 0])


def test_ctc_payroll_tax_counts_half_of_self_employment_tax():
    persons = pd.DataFrame(
        {
            "FICA": [765.0, 1_413.0, 2_178.0, 0.0],
            "WSAL_VAL": [10_000.0, 0.0, 10_000.0, 0.0],
        }
    )
    np.testing.assert_allclose(
        c.ctc_payroll_tax(persons), [765.0, 706.5, 1_471.5, 0.0]
    )


@given(
    st.lists(
        st.tuples(st.floats(0, 50_000), st.floats(-10_000, 200_000)),
        min_size=1,
        max_size=20,
    )
)
def test_ctc_payroll_tax_lies_between_half_and_all_of_fica(rows):
    persons = pd.DataFrame(rows, columns=["FICA", "WSAL_VAL"])
    tax = c.ctc_payroll_tax(persons)
    fica = persons["FICA"].to_numpy()
    assert (tax >= 0.5 * fica - 1e-9).all()
    assert (tax <= fica + 1e-9).all()


_ZERO_CREDIT_FIELDS = {
    "WSAL_VAL": 0.0,
    "SEMP_VAL": 0.0,
    "FRSE_VAL": 0.0,
    "FICA": 0.0,
    "EIT_CRED": 0.0,
    "ACTC_CRD": 0.0,
    "CTC_CRD": 0.0,
}


@st.composite
def credit_persons(draw, max_units: int = 6):
    """People in SPM units of one or two tax units, with credit fields.

    Each filer carries the refundable credit the rule gives its unit, and
    resources sit near the threshold often enough for the EITC to matter.
    """
    n_units = draw(st.integers(1, max_units))
    rng = np.random.default_rng(draw(st.integers(0, 2**32 - 1)))
    rows = []
    tax_id = 1
    for spm in range(n_units):
        threshold = float(rng.integers(10_000, 40_000))
        offset = float(rng.integers(-2_000, 9_000))
        for _ in range(int(rng.integers(1, 3))):
            wages = float(rng.choice([0, 1_000, 3_000, 6_000, 20_000]))
            self_employment = float(rng.choice([0, 0, 2_000, -1_000]))
            rows.append(
                {
                    **_ZERO_CREDIT_FIELDS,
                    "SPM_ID": spm,
                    "TAX_ID": tax_id,
                    "DEP_STAT": 0,
                    "A_AGE": 35,
                    "WSAL_VAL": wages,
                    "SEMP_VAL": self_employment,
                    "FICA": 0.0765 * wages + 0.1413 * max(self_employment, 0),
                    "EIT_CRED": float(
                        rng.integers(0, 2) * rng.integers(0, 7_000)
                    ),
                    "SPM_POVTHRESHOLD": threshold,
                    "SPM_RESOURCES": threshold + offset,
                }
            )
            for _ in range(int(rng.integers(0, 6))):
                rows.append(
                    {
                        **_ZERO_CREDIT_FIELDS,
                        "SPM_ID": spm,
                        "TAX_ID": tax_id,
                        "DEP_STAT": 1,
                        "A_AGE": int(rng.integers(0, 20)),
                        "SPM_POVTHRESHOLD": threshold,
                        "SPM_RESOURCES": threshold + offset,
                    }
                )
            tax_id += 1
    persons = pd.DataFrame(rows)
    units = c.ctc_tax_units(persons)
    rule = pd.Series(
        c.refundable_ctc_rule(units, units["eitc"].to_numpy()),
        index=units.index,
    )
    filer = persons["DEP_STAT"] == 0
    persons.loc[filer, "ACTC_CRD"] = persons.loc[filer, "TAX_ID"].map(rule)
    persons["SPM_EITC"] = persons.groupby("SPM_ID")["EIT_CRED"].transform(
        "sum"
    )
    weight = rng.uniform(0.5, 3_000, size=len(persons))
    replicates = weight[:, None] * rng.uniform(
        0.0, 2.0, size=(len(persons), c.N_REPLICATES)
    )
    weights = pd.DataFrame(
        replicates, columns=list(c.REPLICATE_COLUMNS), index=persons.index
    )
    weights.insert(0, "weight", weight)
    return pd.concat([persons, weights], axis=1)


@PROPERTY_SETTINGS
@given(credit_persons())
def test_eitc_with_ctc_response_lies_between_the_eitc_and_zero(persons):
    net = c.eitc_net_of_ctc_response(persons)
    eitc = persons["SPM_EITC"].to_numpy()
    assert (net >= -1e-9).all()
    assert (net <= eitc + 1e-9).all()
    by_unit = persons.assign(net=net).groupby("SPM_ID")["net"].nunique()
    assert by_unit.max() == 1
    eitc_element = next(e for e in c.ELEMENTS if e.key == "eitc")
    alone = c.estimate_table5(persons, elements=[eitc_element])["eitc"]
    with_response = c.credit_interaction(persons)["eitc_with_ctc_response"]
    for a, b in zip(alone["estimate"], with_response["estimate"]):
        if math.isnan(a):
            continue
        assert a - 1e-9 <= b <= 1e-9


def test_ctc_response_can_keep_a_family_out_of_poverty():
    # A filer with $3,000 of wages, a $1,000 EITC and three children, $900
    # above the threshold. Removing the EITC alone makes the family poor;
    # the credit's $154.50 rise keeps it $54.50 above the threshold.
    filer = {
        **_ZERO_CREDIT_FIELDS,
        "DEP_STAT": 0,
        "A_AGE": 30,
        "WSAL_VAL": 3_000.0,
        "FICA": 229.5,
        "EIT_CRED": 1_000.0,
        "ACTC_CRD": 75.0,
    }
    child = {**_ZERO_CREDIT_FIELDS, "DEP_STAT": 1, "A_AGE": 5}
    persons = pd.DataFrame([filer, child, child, child]).assign(
        SPM_ID=1,
        TAX_ID=7,
        SPM_EITC=1_000.0,
        SPM_POVTHRESHOLD=30_000.0,
        SPM_RESOURCES=30_900.0,
        weight=1.0,
    )
    replicates = pd.DataFrame(
        1.0, index=persons.index, columns=list(c.REPLICATE_COLUMNS)
    )
    persons = pd.concat([persons, replicates], axis=1)
    eitc_element = next(e for e in c.ELEMENTS if e.key == "eitc")
    alone = c.estimate_table5(persons, elements=[eitc_element])["eitc"]
    ci = c.credit_interaction(persons)
    assert alone["estimate"][0] == pytest.approx(-100.0)
    assert ci["eitc_with_ctc_response"]["estimate"][0] == pytest.approx(0.0)
    assert ci["units_raised"] == 1
    assert ci["largest_rise_dollars"] == pytest.approx(154.5)
    assert ci["persons_whose_status_changes"] == 4


# ---------------------------------------------------------------------------
# Table 4 definitions
# ---------------------------------------------------------------------------


@st.composite
def coded_persons(draw):
    """People with every code Table 4 reads, drawn from the dictionary."""
    n = draw(st.integers(1, 40))
    seed = draw(st.integers(0, 2**32 - 1))
    rng = np.random.default_rng(seed)
    spm_ids = rng.integers(1, max(2, n // 2) + 1, size=n)
    frame = pd.DataFrame(
        {
            "SPM_ID": spm_ids,
            "A_AGE": rng.integers(0, 86, size=n),
            "A_SEX": rng.integers(1, 3, size=n),
            "SPM_FAMTYPE": rng.integers(1, 6, size=n),
            "PRDTRACE": rng.integers(1, 27, size=n),
            "PEHSPNON": rng.integers(1, 3, size=n),
            "PRCITSHP": rng.integers(1, 6, size=n),
            "A_HGA": rng.integers(31, 47, size=n),
            "SPM_TENMORTSTATUS": rng.integers(1, 4, size=n),
            "GTMETSTA": rng.integers(1, 4, size=n),
            "GTCBSAST": rng.integers(1, 5, size=n),
            "GEREG": rng.integers(1, 5, size=n),
            "COV": rng.integers(0, 3, size=n),
            "WEXP": rng.integers(1, 14, size=n),
            "PRDISFLG": rng.integers(1, 3, size=n),
        }
    )
    # Private and public coverage only for the covered.
    covered = frame["COV"] == 1
    frame["PRIV"] = np.where(covered, rng.integers(1, 3, size=n), 2)
    frame["PUB"] = np.where(
        covered & (frame["PRIV"] == 2), 1, rng.integers(1, 3, size=n)
    )
    frame.loc[~covered, "PUB"] = 2
    frame["SPM_HEAD"] = (~frame["SPM_ID"].duplicated()).astype(int)
    return frame


def _mask(persons, label, section=None):
    for row in c.TABLE4_ROWS:
        if row.label == label and (section is None or row.section == section):
            return np.asarray(row.mask(persons), dtype=bool)
    raise KeyError(label)


@PROPERTY_SETTINGS
@given(coded_persons())
def test_table4_sections_partition_their_universe(persons):
    everyone = np.ones(len(persons), dtype=bool)
    partitions = [
        (everyone, ["Male", "Female"]),
        (everyone, ["Under 18 years", "18 to 64 years", "65 years and older"]),
        (
            everyone,
            [
                "Married couple",
                "Cohabiting partners",
                "Female reference person",
                "Male reference person",
                "Unrelated individuals",
            ],
        ),
        (everyone, ["Native-born", "Foreign-born"]),
        (
            _mask(persons, "Foreign-born"),
            ["Naturalized citizen", "Not a citizen"],
        ),
        (
            _mask(persons, "Total, 25 years old and older"),
            [
                "No high school diploma",
                "High school, no college",
                "Some college",
                "Bachelor's degree or higher",
            ],
        ),
        (
            everyone,
            [
                "Owner/mortgage",
                "Owner/no mortgage/rent free",
                "Renter",
            ],
        ),
        (everyone, ["Northeast", "Midwest", "South", "West"]),
        (
            everyone,
            [
                "With private insurance",
                "With public, no private insurance",
                "Not insured",
            ],
        ),
        (
            _mask(persons, "Total, 18 to 64 years old", "Work Experience"),
            ["All workers", "Did not work"],
        ),
        (
            _mask(persons, "All workers"),
            [
                "Worked full-time, year-round",
                "Less than full-time, year-round",
            ],
        ),
        (
            _mask(persons, "Total, 18 to 64 years old", "Disability Status"),
            ["With a disability", "With no disability"],
        ),
    ]
    for universe, labels in partitions:
        members = np.column_stack([_mask(persons, label) for label in labels])
        assert (members.sum(axis=1) == universe.astype(int)).all(), labels


@PROPERTY_SETTINGS
@given(coded_persons())
def test_principal_city_rows_sit_inside_metro_areas(persons):
    metro = _mask(persons, "Inside metropolitan statistical areas")
    inside = _mask(persons, "Inside principal cities")
    outside = _mask(persons, "Outside principal cities")
    assert not (inside & outside).any()
    assert ((inside | outside) <= metro).all()


def test_every_table4_row_has_a_definition_and_unique_key():
    keys = [(row.section, row.label) for row in c.TABLE4_ROWS]
    assert len(keys) == len(set(keys)) == 49
    assert all(row.definition for row in c.TABLE4_ROWS)
    assert [r.label for r in c.TABLE4_ROWS if not r.identifiable] == [
        "Inside metropolitan statistical areas",
        "Inside principal cities",
        "Outside principal cities",
        "Outside metropolitan statistical areas",
    ]


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def test_ensure_zip_refuses_missing_and_altered_files(tmp_path):
    missing = tmp_path / c.ZIP_NAME
    with pytest.raises(FileNotFoundError):
        c.ensure_zip(missing)
    missing.write_bytes(b"not the Census file")
    with pytest.raises(ValueError, match="SHA-256"):
        c.ensure_zip(missing)


def test_default_zip_path_follows_the_package_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("SPM_CALCULATOR_CPS_CACHE", str(tmp_path))
    assert c.default_zip_path() == tmp_path / c.ZIP_NAME


def _small_frames():
    persons = pd.DataFrame(
        {
            "PH_SEQ": [1, 1, 2],
            "PPPOS": [41, 42, 41],
            "MARSUPWT": [150, 250, 1000],
        }
    )
    households = pd.DataFrame(
        {
            "H_SEQ": [1, 2],
            "GEREG": [1, 3],
            "GTMETSTA": [1, 2],
            "GTCBSAST": [1, 3],
        }
    )
    replicates = pd.DataFrame(
        {
            "h_seq": [1, 1, 2],
            "PPPOS": [41, 42, 41],
            **{
                f"pwwgt{i}": [1.5 + i, 2.5 + i, 10.0 + i]
                for i in range(0, c.N_REPLICATES + 1)
            },
        }
    )
    return persons, households, replicates


def test_assemble_persons_joins_households_and_replicates():
    persons, households, replicates = _small_frames()
    out = c.assemble_persons(persons, households, replicates)
    assert list(out["GEREG"]) == [1, 1, 3]
    assert list(out["weight"]) == [1.5, 2.5, 10.0]
    assert list(out["repwgt_160"]) == [161.5, 162.5, 170.0]
    assert list(out["weight_rep0"]) == [1.5, 2.5, 10.0]


def test_assemble_persons_refuses_missing_records():
    persons, households, replicates = _small_frames()
    with pytest.raises(ValueError, match="household"):
        c.assemble_persons(persons, households.iloc[:1], replicates)
    with pytest.raises(ValueError, match="replicate"):
        c.assemble_persons(persons, households, replicates.iloc[:2])


# ---------------------------------------------------------------------------
# Published tables
# ---------------------------------------------------------------------------


def test_receipt_digests_match_the_bundled_workbooks():
    receipt = c.load_receipt()
    for name, entry in receipt["tables"].items():
        path = c.PUBLISHED_DIR / entry["file"]
        assert c.sha256_file(path) == entry["sha256"]
        assert path.stat().st_size == entry["bytes"]
        assert c.verified_table(name) == path
    micro = receipt["microdata"]
    assert micro["sha256"] == c.ZIP_SHA256
    assert micro["url"] == c.ZIP_URL
    assert micro["bytes"] == c.ZIP_BYTES


def test_parser_refuses_an_altered_workbook(monkeypatch, tmp_path):
    for item in c.PUBLISHED_DIR.iterdir():
        shutil.copy(item, tmp_path / item.name)
    with open(tmp_path / "table_5_spm_program_effect_rates.xlsx", "ab") as f:
        f.write(b"\0")
    monkeypatch.setattr(c, "PUBLISHED_DIR", tmp_path)
    monkeypatch.setattr(c, "PUBLISHED_RECEIPT", tmp_path / "receipt.json")
    with pytest.raises(ValueError, match="SHA-256"):
        c.published_table5()
    c.published_table4()  # The untouched workbook still parses.


def test_published_table5_values():
    table = c.published_table5()
    assert table["spm_rate"]["estimate"] == [13.11, 13.4, 12.28, 15.37]
    assert table["spm_rate"]["moe"] == [0.31, 0.56, 0.34, 0.53]
    assert table["social_security"]["estimate"][3] == -32.13
    assert table["medical_expenses"]["estimate"] == [2.28, 1.99, 1.88, 3.83]
    # "Z" rounds to zero.
    assert table["wic"]["estimate_text"][3] == "Z"
    assert table["wic"]["estimate"][3] == 0.0
    assert set(table) == set(c.TABLE5_LABELS.values())
    assert len(table) == 20


def test_published_table5_reads_the_requested_year():
    # The 2024 block's year label carries a footnote ("....20244").
    table = c.published_table5(2024)
    assert table["spm_rate"]["estimate"] == [13.04, 13.46, 12.23, 15.13]
    with pytest.raises(ValueError, match="no block"):
        c.published_table5(2019)


def test_published_table4_values():
    rows = c.published_table4()
    assert len(rows) == len(c.TABLE4_ROWS)
    first = rows[0]
    assert (
        first["label"],
        first["number_thousands"],
        first["number_moe"],
    ) == (
        "All people",
        44390.0,
        1042.0,
    )
    assert (first["percent"], first["percent_moe"]) == (13.1, 0.3)
    by_key = {(r["section"], r["label"]): r for r in rows}
    assert (
        by_key[("Disability Status", "With a disability")]["percent"] == 25.0
    )
    assert (
        by_key[("Race and Hispanic Origin", "White, not Hispanic")][
            "number_thousands"
        ]
        == 17430.0
    )
    # Census rounds each number to four significant digits.
    for row in rows:
        assert c.round_sig(row["number_thousands"]) == row["number_thousands"]
    # The regions partition everyone, up to that rounding: each number can
    # sit up to half a unit in its fourth digit from the unrounded value.
    regions = [
        by_key[("Region", r)]["number_thousands"]
        for r in ("Northeast", "Midwest", "South", "West")
    ]
    slack = sum(_half_unit(x) for x in regions) + _half_unit(44390.0)
    assert sum(regions) == pytest.approx(44390.0, abs=slack)
    assert slack < 20


def _half_unit(value: float, digits: int = 4) -> float:
    """Half a unit in the last of ``digits`` significant digits."""
    return 0.5 * 10 ** (math.floor(math.log10(abs(value))) - digits + 1)


# ---------------------------------------------------------------------------
# The committed results
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def results():
    return json.loads(RESULTS_PATH.read_text())


def _t5(results, key):
    return next(r for r in results["table5"]["rows"] if r["key"] == key)


def _t4(results, label, section=None):
    return next(
        r
        for r in results["table4"]["rows"]
        if r["label"] == label and (section is None or r["section"] == section)
    )


def test_committed_results_pass_every_identity(results):
    checks = results["identities"]
    assert c.failed_identities(checks) == []
    for name in c.ZERO_CHECKS:
        assert checks[name] == 0, name
    assert checks["persons_with_negative_published_element"] == 0
    assert checks["weight_rep0_max_gap"] <= c.WEIGHT_REP0_TOLERANCE


def test_committed_results_meet_every_stated_tolerance(results):
    assert results["tolerances"] == c.TOLERANCES
    assert c.tolerance_failures(results) == []


def test_headline_rate_and_margin_equal_census_at_two_decimals(results):
    rate = _t5(results, "spm_rate")
    assert round(rate["estimate"][0], 2) == 13.11
    assert round(rate["moe"][0], 2) == 0.31
    assert rate["published_values"]["estimate"][0] == 13.11
    assert rate["published_values"]["moe"][0] == 0.31


def test_table4_all_people_matches_census(results):
    row = _t4(results, "All people")
    assert round(row["percent"], 1) == row["published_values"]["percent"]
    assert (
        c.round_sig(row["number_thousands"])
        == (row["published_values"]["number_thousands"])
    )
    assert row["percent_within_moe"] and row["number_within_moe"]


def test_committed_comparison_follows_from_the_rows(results):
    fresh = json.loads(json.dumps(results))
    for section in ("table5", "table4"):
        for row in fresh[section]["rows"]:
            for key in [k for k in row if k.endswith("_gap") or "within" in k]:
                del row[key]
    c.annotate_gaps(fresh)
    assert report.round_floats(c.summarize(fresh)) == results["comparison"]


def test_committed_published_values_match_the_workbooks(results):
    published5 = c.published_table5()
    for row in results["table5"]["rows"]:
        if row["published_values"] is None:
            assert row["key"] == "state_income_tax"
            continue
        assert row["published_values"] == published5[row["key"]]
    for row, pub in zip(results["table4"]["rows"], c.published_table4()):
        assert (row["section"], row["label"]) == (pub["section"], pub["label"])
        for key in (
            "number_thousands",
            "number_moe",
            "percent",
            "percent_moe",
        ):
            assert row["published_values"][key] == pub[key]


def test_committed_inputs_record_the_pinned_checksums(results):
    inputs = results["inputs"]
    assert inputs["microdata"]["sha256"] == c.ZIP_SHA256
    assert inputs["microdata"]["bytes"] == c.ZIP_BYTES
    receipt = c.load_receipt()
    for name, entry in inputs["published_tables"]["tables"].items():
        assert entry["sha256"] == receipt["tables"][name]["sha256"]


def test_committed_rows_follow_the_module_definitions(results):
    assert [r["label"] for r in results["table4"]["rows"]] == [
        row.label for row in c.TABLE4_ROWS
    ]
    assert [r["definition"] for r in results["table4"]["rows"]] == [
        row.definition for row in c.TABLE4_ROWS
    ]
    keys = [r["key"] for r in results["table5"]["rows"]]
    assert keys == ["spm_rate"] + [e.key for e in c.ELEMENTS]


def test_table4_partitions_hold_on_the_file(results):
    def persons(label, section=None):
        return _t4(results, label, section)["persons"]

    everyone = persons("All people")
    assert persons("Male") + persons("Female") == everyone
    assert (
        persons("With private insurance")
        + persons("With public, no private insurance")
        + persons("Not insured")
        == everyone
    )
    assert persons("All workers") + persons("Did not work") == persons(
        "Total, 18 to 64 years old", "Work Experience"
    )
    # People in the armed forces have no disability status (Table 4, note 6).
    assert persons("With a disability") + persons("With no disability") < (
        persons("Total, 18 to 64 years old", "Disability Status")
    )


def test_effects_have_the_signs_of_their_kind_on_the_file(results):
    for row in results["table5"]["rows"]:
        if row["key"] in ("spm_rate", "state_income_tax"):
            continue
        for value in row["estimate"]:
            if row["kind"] == c.ADDITION:
                assert value <= 0, row["key"]
            else:
                assert value >= 0, row["key"]


# Claims the note makes in prose. Each test pins one claim to the committed
# results, so a rebuild that falsifies a claim fails here.


def test_claim_combined_credits_match_within_a_hundredth(results):
    row = _t5(results, "refundable_tax_credits")
    assert max(row["estimate_gap"]) <= 0.01 + 1e-9


def test_claim_each_credit_alone_exceeds_census_below_65(results):
    for key in ("eitc", "refundable_ctc"):
        row = _t5(results, key)
        for j in range(3):  # All people, under 18, 18 to 64.
            assert abs(row["estimate"][j]) > abs(
                row["published_values"]["estimate"][j]
            ), (key, j)


def test_claim_credit_fields_sum_to_spm_unit_fields(results):
    assert results["identities"]["spm_eitc_vs_eit_cred_max_gap"] == 0
    assert results["identities"]["spm_actc_vs_actc_crd_max_gap"] == 0


def test_claim_fica_carries_the_whole_self_employment_tax(results):
    shares = results["credit_interaction"]["fica_shares"]
    assert shares["wages"] == pytest.approx(c.EMPLOYEE_PAYROLL_RATE, abs=5e-5)
    # Self-employment tax: 15.3 percent of 92.35 percent of net earnings.
    assert shares["self_employment"] == pytest.approx(0.153 * 0.9235, abs=5e-5)


def test_claim_rule_reproduces_every_refundable_credit(results):
    ci = results["credit_interaction"]
    assert ci["rule_matches"] == ci["units_with_credit"]
    assert ci["units_without_credit_not_reproduced_with_eitc"] == 0


def test_claim_payroll_alternative_sets_no_credit_in_the_file(results):
    assert (
        results["credit_interaction"]["three_plus_above_earnings_branch"] == 0
    )


def test_claim_payroll_alternative_leaves_the_eitc_effect_unchanged(results):
    ci = results["credit_interaction"]
    assert ci["units_raised"] > 0
    assert ci["persons_whose_status_changes"] == 0
    assert ci["eitc_with_ctc_response"]["estimate"] == pytest.approx(
        _t5(results, "eitc")["estimate"], abs=1e-6
    )


def test_claim_federal_tax_row_is_tax_before_credits(results):
    main = _t5(results, "federal_income_tax")
    alt = next(
        r
        for r in results["alternatives"]["table5"]["rows"]
        if r["key"] == "federal_income_tax_after_credits"
    )
    assert alt["compares_with"] == "federal_income_tax"
    for j in range(4):
        assert alt["estimate_gap"][j] >= 10 * max(
            main["estimate_gap"][j], 0.01
        )


def test_claim_infants_count_as_not_insured(results):
    main = _t4(results, "Not insured")
    alt = next(
        r
        for r in results["alternatives"]["table4"]["rows"]
        if r["compares_with"] == "Not insured"
    )
    assert main["percent_gap"] == 0
    assert alt["percent_gap"] > main["percent_gap"]


def test_claim_head_code_leaves_cohabiting_rate_unchanged(results):
    main = _t4(results, "Cohabiting partners")
    alt = next(
        r
        for r in results["alternatives"]["table4"]["rows"]
        if r["compares_with"] == "Cohabiting partners"
    )
    assert round(alt["percent"], 1) == round(main["percent"], 1)
    assert main["percent_gap"] > 0


def test_claim_census_residence_rows_place_everyone(results):
    inside = _t4(results, "Inside metropolitan statistical areas")
    outside = _t4(results, "Outside metropolitan statistical areas")
    everyone = _t4(results, "All people")
    assert (
        inside["published_values"]["number_thousands"]
        + outside["published_values"]["number_thousands"]
        == everyone["published_values"]["number_thousands"]
    )
    geography = results["unidentified_geography"]
    assert geography["metro_status_persons"] > 0
    assert geography["principal_city_persons"] > 0


def test_claim_some_units_carry_mixed_family_types(results):
    assert results["identities"]["units_with_varying_famtype"] > 0


def test_claim_state_tax_falls_below_zero_for_some_people(results):
    assert results["identities"]["persons_with_negative_state_tax"] > 0
    assert min(_t5(results, "state_income_tax")["estimate"]) < 0


# ---------------------------------------------------------------------------
# The note
# ---------------------------------------------------------------------------


def test_note_matches_its_rendered_blocks(results):
    note = NOTE_PATH.read_text()
    blocks = report.render_blocks(results)
    assert set(report.extract_blocks(note)) == set(blocks)
    assert report.apply_blocks(note, blocks) == note


def test_apply_blocks_refuses_missing_or_unknown_blocks():
    text = "<!-- BEGIN GENERATED: a -->\nold\n<!-- END GENERATED: a -->\n"
    assert report.apply_blocks(text, {"a": "new"}) == (
        "<!-- BEGIN GENERATED: a -->\nnew\n<!-- END GENERATED: a -->\n"
    )
    with pytest.raises(ValueError):
        report.apply_blocks(text, {"a": "new", "b": "x"})
    with pytest.raises(ValueError):
        report.apply_blocks(text, {})


def test_note_keeps_names_out_and_headings_in_sentence_case():
    for path in (NOTE_PATH, ROOT / "docs/spm-evidence-series.md"):
        text = path.read_text()
        assert "enhanced CPS" not in text
        assert "microimpute" not in text
        for line in text.splitlines():
            if line.startswith("#"):
                words = line.lstrip("#").split()
                # Sentence case: after the first word, capitals only for
                # proper nouns and acronyms.
                allowed = {
                    "Census's",
                    "SPM",
                    "PolicyEngine",
                    "Table",
                    "Microcosm",
                    "CPS",
                    "ASEC",
                }
                for word in words[1:]:
                    stripped = word.strip("():,")
                    if stripped and stripped[0].isupper():
                        assert stripped in allowed or stripped.isupper(), (
                            path.name,
                            line,
                        )


def _load_script():
    spec = importlib.util.spec_from_file_location("reproduce", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_renders_the_note_without_microdata(tmp_path, capsys):
    script = _load_script()
    note = tmp_path / "note.md"
    note.write_text(NOTE_PATH.read_text())
    status = script.main(
        ["--render-only", "--output", str(RESULTS_PATH), "--note", str(note)]
    )
    assert status == 0
    assert note.read_text() == NOTE_PATH.read_text()
    assert "45 of 45" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Full rebuild from the public-use file
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("SPM_CALCULATOR_CENSUS_SPM_REBUILD") != "1"
    or not c.default_zip_path().exists(),
    reason=(
        "Set SPM_CALCULATOR_CENSUS_SPM_REBUILD=1 with the 2026 ASEC zip in "
        "the package cache to rebuild from microdata."
    ),
)
def test_rebuild_from_public_use_file_matches_committed_results(results):
    script = _load_script()
    rebuilt = script.rebuild(c.default_zip_path(), download=False)
    assert script.without_software(rebuilt) == script.without_software(results)
