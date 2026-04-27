"""Validation helpers for SPM IDs and thresholds."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .units import _resolve_column, spm_unit_id


def spm_unit_id_match(
    persons: pd.DataFrame,
    *,
    reference_spm_unit_id: str = "SPM_ID",
    predicted_spm_unit_id: str | pd.Series | np.ndarray | None = None,
    household_id: str = "household_id",
    max_mismatching_household_ids: int = 10,
    **spm_unit_id_kwargs: Any,
) -> dict[str, Any]:
    """Compare SPM unit assignments to reference IDs within households.

    Unit IDs are arbitrary labels, so this validates that each household's
    person partition matches the reference partition after relabeling.
    If ``predicted_spm_unit_id`` is not supplied, IDs are inferred with
    ``spm_unit_id`` while disabling native-ID preservation.
    """
    household_column = _resolve_column(
        persons,
        household_id,
        ("household_id", "person_household_id", "H_SEQ", "PH_SEQ"),
        required=True,
    )
    reference_column = _resolve_column(
        persons,
        reference_spm_unit_id,
        ("SPM_ID", "person_spm_unit_id", "spm_unit_id"),
        required=True,
    )
    reference = persons[reference_column]

    if predicted_spm_unit_id is None:
        inference_kwargs = dict(spm_unit_id_kwargs)
        inference_kwargs.setdefault("household_id", household_column)
        inference_kwargs.setdefault("native_person_spm_unit_id", None)
        inference_kwargs.setdefault("native_spm_unit_id", None)
        predicted = spm_unit_id(persons, **inference_kwargs)
        if isinstance(predicted, tuple):
            predicted = predicted[0]
        predicted_source = "inferred"
    elif isinstance(predicted_spm_unit_id, str):
        predicted = persons[predicted_spm_unit_id]
        predicted_source = predicted_spm_unit_id
    else:
        predicted = pd.Series(
            predicted_spm_unit_id,
            index=persons.index,
            name="predicted_spm_unit_id",
        )
        predicted_source = "provided_array"

    work = pd.DataFrame(
        {
            "household_id": persons[household_column],
            "reference": reference,
            "predicted": predicted,
        },
        index=persons.index,
    )

    matching_households = 0
    matching_persons = 0
    mismatching_household_ids: list[Any] = []
    for household_value, household_rows in work.groupby(
        "household_id",
        sort=False,
    ):
        household_match = _canonical_partition(
            household_rows["reference"]
        ) == _canonical_partition(household_rows["predicted"])
        if household_match:
            matching_households += 1
            matching_persons += len(household_rows)
            continue
        if len(mismatching_household_ids) < max_mismatching_household_ids:
            mismatching_household_ids.append(household_value)

    total_households = int(work["household_id"].nunique(dropna=False))
    total_persons = int(len(work))
    mismatching_households = total_households - matching_households
    return {
        "match": mismatching_households == 0,
        "reference_column": reference_column,
        "predicted_source": predicted_source,
        "household_column": household_column,
        "households": total_households,
        "matching_households": int(matching_households),
        "mismatching_households": int(mismatching_households),
        "household_match_rate": _safe_rate(
            matching_households,
            total_households,
        ),
        "persons": total_persons,
        "persons_in_matching_households": int(matching_persons),
        "person_weighted_household_match_rate": _safe_rate(
            matching_persons,
            total_persons,
        ),
        "mismatching_household_ids": mismatching_household_ids,
    }


def spm_threshold_match(
    calculated: pd.Series | np.ndarray | list[float],
    reference: pd.Series | np.ndarray | list[float],
    *,
    rtol: float = 1e-4,
    atol: float = 1.0,
    max_mismatching_indices: int = 10,
) -> dict[str, Any]:
    """Compare calculated thresholds to reference values within tolerance."""
    calculated_series = _as_numeric_series(calculated)
    reference_series = _as_numeric_series(reference)
    if len(calculated_series) != len(reference_series):
        raise ValueError("calculated and reference must have the same length")

    reference_series = pd.Series(
        reference_series.to_numpy(),
        index=calculated_series.index,
    )
    calculated_values = calculated_series.to_numpy(dtype=float)
    reference_values = reference_series.to_numpy(dtype=float)
    matches = np.isclose(
        calculated_values,
        reference_values,
        rtol=rtol,
        atol=atol,
        equal_nan=False,
    )
    abs_error = np.abs(calculated_values - reference_values)
    with np.errstate(divide="ignore", invalid="ignore"):
        rel_error = np.where(
            reference_values != 0,
            abs_error / np.abs(reference_values),
            np.nan,
        )

    mismatching_index = calculated_series.index[~matches]
    mismatching_indices = list(
        mismatching_index[:max_mismatching_indices].tolist()
    )
    n = len(calculated_series)
    matching = int(matches.sum())
    return {
        "match": bool(matches.all()),
        "rtol": float(rtol),
        "atol": float(atol),
        "values": int(n),
        "matching_values": matching,
        "mismatching_values": int(n - matching),
        "match_rate": _safe_rate(matching, n),
        "max_abs_error": float(np.nanmax(abs_error)) if n else 0.0,
        "max_rel_error": float(np.nanmax(rel_error)) if n else 0.0,
        "mismatching_indices": mismatching_indices,
    }


def _canonical_partition(values: pd.Series) -> tuple[int, ...]:
    codes, _ = pd.factorize(values, sort=False)
    return tuple(int(code) for code in codes)


def _as_numeric_series(
    values: pd.Series | np.ndarray | list[float],
) -> pd.Series:
    series = values if isinstance(values, pd.Series) else pd.Series(values)
    return pd.to_numeric(series, errors="coerce")


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return float(numerator / denominator)
