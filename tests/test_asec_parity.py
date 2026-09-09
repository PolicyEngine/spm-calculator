"""Optional source parity checks against a real Census CPS ASEC HDFStore.

Use the archived Census national source and the file's geography factors to
check the published Census amounts. Current canonical forecast thresholds use
the revised BLS source and are tested separately.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from spm_calculator.equivalence_scale import spm_equivalence_scale
from spm_calculator.published_thresholds import get_published_thresholds
from spm_calculator.validation import spm_threshold_match, spm_unit_id_match

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


def test_asec_source_thresholds_match_census_within_tolerance():
    _, spm_unit = _load_asec_tables()

    base_thresholds = get_published_thresholds(
        2024, series="census-published-pre-correction"
    )
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
