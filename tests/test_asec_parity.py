"""Optional parity checks against a real Census CPS ASEC HDFStore."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from spm_calculator import (
    SPMCalculator,
    spm_equivalence_scale,
    spm_threshold_match,
    spm_unit_id_match,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("SPM_CALCULATOR_ASEC_H5"),
    reason=(
        "Set SPM_CALCULATOR_ASEC_H5 to a Census CPS ASEC HDFStore to run "
        "full ASEC parity checks"
    ),
)


def _load_asec_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    pytest.importorskip("tables")
    path = Path(os.environ["SPM_CALCULATOR_ASEC_H5"]).expanduser()
    with pd.HDFStore(path) as store:
        return store["person"], store["spm_unit"]


def test_asec_spm_unit_id_inference_matches_census_above_floor():
    person, _ = _load_asec_tables()

    report = spm_unit_id_match(
        person,
        household_id="PH_SEQ",
        reference_spm_unit_id="SPM_ID",
    )

    min_household_match_rate = float(
        os.environ.get("SPM_CALCULATOR_ASEC_ID_MATCH_FLOOR", "0.99")
    )
    assert report["household_match_rate"] >= min_household_match_rate, report
    if "PECOHAB" in person.columns:
        assert report["match"], report


def test_asec_thresholds_match_census_within_tolerance():
    _, spm_unit = _load_asec_tables()

    calculator = SPMCalculator(year=2024)
    base_thresholds = calculator.get_base_thresholds()
    tenure = (
        pd.to_numeric(
            spm_unit["SPM_TENMORTSTATUS"],
            errors="coerce",
        )
        .fillna(3)
        .astype(int)
        .map(
            {
                1: "owner_with_mortgage",
                2: "owner_without_mortgage",
                3: "renter",
            }
        )
        .fillna("renter")
    )
    calculated = (
        np.array([base_thresholds[value] for value in tenure], dtype=float)
        * spm_equivalence_scale(
            pd.to_numeric(
                spm_unit["SPM_NUMADULTS"],
                errors="coerce",
            )
            .fillna(0)
            .to_numpy(dtype=float),
            pd.to_numeric(
                spm_unit["SPM_NUMKIDS"],
                errors="coerce",
            )
            .fillna(0)
            .to_numpy(dtype=float),
        )
        * pd.to_numeric(
            spm_unit["SPM_GEOADJ"],
            errors="coerce",
        )
        .fillna(1)
        .to_numpy(dtype=float)
    )

    report = spm_threshold_match(
        calculated,
        spm_unit["SPM_POVTHRESHOLD"],
        atol=1.0,
        rtol=1e-4,
    )
    assert report["match"], report
