"""Canonical SPM measurement on an actual, explicitly linked Microcosm Frame.

Microcosm owns membership, source roles and typed population weights. This
module neither calibrates weights nor constructs benefit/resource amounts.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Mapping, Optional

from spm_calculator.errors import SPMInputError
from spm_calculator.release import SPMUnit, canonical_bytes
from spm_calculator.rolling_forecast import SPMForecast

OUTPUT_COLUMNS = {
    "threshold": "spm_forecast_threshold",
    "housing_portion": "spm_forecast_housing_portion",
    "is_in_poverty": "spm_forecast_is_in_poverty",
    "forecast_id": "spm_forecast_id",
    "forecast_sha256": "spm_forecast_sha256",
    "scenario": "spm_forecast_scenario",
    "national_status": "spm_forecast_national_status",
    "geography_status": "spm_forecast_geography_status",
    "housing_share_status": "spm_forecast_housing_share_status",
}
PERSON_COLUMNS = {
    "age": "age",
    "independent_minor_role": "is_spm_independent_minor_role",
    "head": "is_household_head",
    "spouse": "is_household_spouse",
}


def _frame_api():
    try:
        from microcosm.frame import Frame, wmean, wsum
    except ImportError as error:
        raise ImportError(
            "Microcosm integration requires the optional microcosm-frame package"
        ) from error
    return Frame, wmean, wsum


def _weight_source(frame, entity, weight_entity):
    """Check the caller's expected source; let Frame resolve all weights."""
    resolved = frame.resolve_weights(entity)
    if entity in frame.weighted_entities:
        source = entity
    elif (
        entity != frame.schema.person_entity
        and frame.schema.person_entity in frame.weighted_entities
    ):
        source = frame.schema.person_entity
    else:
        candidates = [
            name
            for name in frame.schema.group_entities
            if name in frame.weighted_entities
        ]
        if len(candidates) != 1:
            raise ValueError(
                "SPM weights require one unambiguous declared source"
            )
        source = candidates[0]
    if source != weight_entity:
        raise ValueError(
            f"Frame resolves {entity!r} weights from {source!r}, "
            f"not requested {weight_entity!r}"
        )
    return {
        "source_entity": source,
        "target_entity": entity,
        "kind": resolved.kind.value,
        "source_values_sha256": hashlib.sha256(
            frame.weights_for(source).values.tobytes()
        ).hexdigest(),
        "resolved_values_sha256": hashlib.sha256(
            resolved.values.tobytes()
        ).hexdigest(),
    }


def _bool(value, name):
    # numpy/pandas booleans expose item(); integers are not role declarations.
    scalar = value.item() if hasattr(value, "item") else value
    if not isinstance(scalar, bool):
        raise SPMInputError(
            "SPM_COMPOSITION_REQUIRED",
            f"SPM composition role {name!r} must be nonmissing bool",
        )
    return scalar


def _age(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(value)
        or value < 0
        or int(value) != value
    ):
        raise SPMInputError(
            "SPM_COMPOSITION_REQUIRED",
            "SPM composition age must be a nonnegative integer",
        )
    return int(value)


@dataclass(frozen=True)
class FrameSPMInputs:
    """Validated input transport shared with the actual Axiom runtime."""

    units: tuple
    persons: tuple
    provenance: dict
    max_unit_size: int


def prepare_frame_inputs(
    frame,
    forecast: SPMForecast,
    *,
    year: int,
    unit_entity: str,
    weight_entity: str,
    membership_provenance: str,
    scenario=None,
    columns: Optional[Mapping[str, str]] = None,
    person_columns: Optional[Mapping[str, str]] = None,
    geography_kind="county",
    geography_id=None,
    county_vintage="2020",
    as_of=None,
):
    """Validate primitive roles, native membership and selected-year location.

    Unit columns contain tenure, county (the default), and optional measured
    resources. Counts are derived only within the existing SPM membership.
    A supplied independence role takes precedence over explicit head/spouse
    structure. Missing roles never silently classify every minor as dependent.
    """
    Frame, _, _ = _frame_api()
    if not isinstance(frame, Frame):
        raise TypeError("Expected an actual microcosm.frame.Frame")
    if not isinstance(forecast, SPMForecast):
        raise TypeError("Expected a verified SPMForecast")
    frame.revalidate()
    if (
        isinstance(year, bool)
        or not isinstance(year, Integral)
        or year not in forecast.years
    ):
        raise SPMInputError(
            "SPM_YEAR_UNAVAILABLE", f"Forecast has no entry for {year!r}"
        )
    year = int(year)
    try:
        forecast.entry(year, scenario=scenario, as_of=as_of)
    except SPMInputError:
        raise
    except ValueError as error:
        if str(error).startswith("Unknown forecast scenario:"):
            raise SPMInputError(
                "SPM_SCENARIO_UNAVAILABLE", str(error)
            ) from error
        raise
    scenario = forecast.default_scenario if scenario is None else scenario
    if unit_entity not in frame.schema.group_entities:
        raise ValueError(
            "SPM units must be an explicitly declared group entity"
        )
    if (
        not isinstance(membership_provenance, str)
        or not membership_provenance.strip()
    ):
        raise ValueError("Explicit SPM membership provenance is required")
    if geography_kind not in {"county", "metro", "national"}:
        raise ValueError(
            "SPM geography must be county, metro or explicit national"
        )
    if geography_kind != "metro" and geography_id is not None:
        raise ValueError("Only explicit metro geography takes geography_id")
    weight_provenance = _weight_source(frame, unit_entity, weight_entity)
    mapping = {"tenure": "spm_tenure"}
    if geography_kind == "county":
        mapping["county_fips"] = "county_fips"
    elif geography_kind == "metro" and geography_id is None:
        mapping["geography_id"] = "geography_id"
    if columns is not None:
        mapping = dict(columns)
    allowed = {"tenure", "resources"}
    if geography_kind == "county":
        allowed.add("county_fips")
    if geography_kind == "metro" and geography_id is None:
        allowed.add("geography_id")
    required = allowed - {"resources"}
    if not required <= set(mapping) or not set(mapping) <= allowed:
        raise ValueError(
            "Unit columns must name the selected geography and tenure inputs"
        )
    table = frame.table(unit_entity)
    for column in mapping.values():
        if column not in table:
            if (
                mapping.get("county_fips") == column
                or mapping.get("geography_id") == column
            ):
                raise SPMInputError(
                    "SPM_GEOGRAPHY_REQUIRED",
                    f"SPM geography input {column!r} is absent from {unit_entity!r}",
                )
            raise ValueError(
                f"SPM input {column!r} is absent from {unit_entity!r}"
            )
    person_mapping = dict(PERSON_COLUMNS)
    if person_columns is not None:
        if not set(person_columns) <= set(PERSON_COLUMNS):
            raise ValueError("Unsupported person composition column")
        person_mapping.update(person_columns)
    person = frame.person
    if person_mapping["age"] not in person:
        raise SPMInputError(
            "SPM_COMPOSITION_REQUIRED", "Missing SPM composition age"
        )
    role = person_mapping["independent_minor_role"]
    explicit_role = role in person
    if not explicit_role and not all(
        person_mapping[k] in person for k in ("head", "spouse")
    ):
        raise SPMInputError(
            "SPM_COMPOSITION_REQUIRED",
            "Missing SPM composition: supply independence roles or explicit head and spouse structure",
        )
    id_column = frame.schema.id_column(unit_entity)
    membership_column = frame.schema.membership_column(unit_entity)
    person_id_column = frame.schema.person_id_column
    counts = {value: [0, 0] for value in table[id_column]}
    persons = []
    for row in person.to_dict(orient="records"):
        age = _age(row[person_mapping["age"]])
        independent = (
            _bool(row[role], role)
            if explicit_role
            else _bool(row[person_mapping["head"]], person_mapping["head"])
            | _bool(row[person_mapping["spouse"]], person_mapping["spouse"])
        )
        unit_id = row[membership_column]
        adult = age >= 18 or (age >= 15 and independent)
        counts[unit_id][0 if adult else 1] += 1
        persons.append(
            {
                "person_id": str(row[person_id_column]),
                "unit_id": str(unit_id),
                "age": age,
                "independent_minor_role": independent,
            }
        )
    for entity, ids in (
        ("person", [p["person_id"] for p in persons]),
        (unit_entity, [str(x) for x in table[id_column]]),
    ):
        if len(ids) != len(set(ids)):
            raise ValueError(
                f"Ambiguous string representation of {entity} IDs"
            )
    units, assignments = [], []
    for row in table.to_dict(orient="records"):
        adults, children = counts[row[id_column]]
        if adults < 1:
            raise SPMInputError(
                "SPM_COMPOSITION_REQUIRED",
                f"Missing SPM composition: unit {row[id_column]!r} has no classified adult",
            )
        kind, identity = geography_kind, geography_id
        assignment = None
        if kind == "county":
            county = row[mapping["county_fips"]]
            if county is None or (
                isinstance(county, str) and not county.strip()
            ):
                raise SPMInputError(
                    "SPM_GEOGRAPHY_REQUIRED", "Supply a five-digit county FIPS"
                )
            try:
                assignment = forecast.resolve_county(
                    year,
                    county,
                    county_vintage=county_vintage,
                    scenario=scenario,
                    as_of=as_of,
                )
            except SPMInputError:
                raise
            except ValueError as error:
                raise SPMInputError(
                    "SPM_GEOGRAPHY_UNAVAILABLE", str(error)
                ) from error
            kind, identity = assignment["kind"], assignment["area_id"]
        elif kind == "metro" and identity is None:
            identity = row[mapping["geography_id"]]
        if kind == "metro" and (
            identity is None
            or (isinstance(identity, str) and not identity.strip())
        ):
            raise SPMInputError(
                "SPM_GEOGRAPHY_REQUIRED", "Supply an SPM area id"
            )
        tenure = row[mapping["tenure"]]
        unit = SPMUnit(
            unit_id=str(row[id_column]),
            num_adults=adults,
            num_children=children,
            tenure=tenure,
            year=year,
            resources=(
                row[mapping["resources"]] if "resources" in mapping else None
            ),
            geography_kind=kind,
            geography_id=identity,
        )
        try:
            forecast.geography_factor(
                year,
                tenure,
                kind=kind,
                geoid=identity,
                scenario=scenario,
                as_of=as_of,
            )
        except SPMInputError:
            raise
        except ValueError as error:
            raise SPMInputError(
                "SPM_GEOGRAPHY_UNAVAILABLE", str(error)
            ) from error
        units.append(unit)
        assignments.append(assignment)
    if not units:
        raise ValueError("At least one populated SPM unit is required")
    return FrameSPMInputs(
        units=tuple(units),
        persons=tuple(persons),
        max_unit_size=max(sum(value) for value in counts.values()),
        provenance={
            "forecast_id": forecast.forecast_id,
            "forecast_sha256": forecast.content_sha256,
            "scenario": scenario,
            "year": year,
            "unit_entity": unit_entity,
            "membership_column": membership_column,
            "membership_provenance": membership_provenance,
            "composition": {
                "rule": "age >= 18 or (age >= 15 and independence role)",
                "role_source": (
                    role
                    if explicit_role
                    else {k: person_mapping[k] for k in ("head", "spouse")}
                ),
                "person_membership_inputs_sha256": hashlib.sha256(
                    canonical_bytes(persons)
                ).hexdigest(),
                "unit_count": len(units),
                "person_count": len(persons),
            },
            "weights": weight_provenance,
            "county_assignments": assignments,
            "role": "population SPM measurement; not CE estimation or population certification",
        },
    )


def _attach_results(frame, prepared, results, *, execution=None):
    Frame, _, _ = _frame_api()
    unit_entity = prepared.provenance["unit_entity"]
    if len(results) != len(prepared.units):
        raise ValueError(
            "SPM result count differs from native unit membership"
        )
    if [result["unit_id"] for result in results] != [
        unit.unit_id for unit in prepared.units
    ]:
        raise ValueError(
            "SPM results do not match native unit membership order"
        )
    table = frame.table(unit_entity).copy()
    for field, column in OUTPUT_COLUMNS.items():
        table[column] = [result[field] for result in results]
    tables = {entity: frame.table(entity) for entity in frame.entities}
    tables.update({name: frame.link(name) for name in frame.links})
    tables[unit_entity] = table
    metadata = dict(frame.metadata)
    metadata["spm_forecast_application"] = {
        **prepared.provenance,
        "unit_results": results,
        "execution": execution or {"provider": "canonical SPMForecast"},
    }
    return Frame(
        tables,
        frame.schema,
        {
            entity: frame.weights_for(entity)
            for entity in frame.weighted_entities
        },
        frame.strata,
        mass_log=frame.mass_log,
        metadata=metadata,
    )


def apply_forecast_to_frame(frame, forecast: SPMForecast, **kwargs):
    """Return a new Frame with final canonical amounts; preserve all weights."""
    prepared = prepare_frame_inputs(frame, forecast, **kwargs)
    results = []
    for unit, assignment in zip(
        prepared.units, prepared.provenance["county_assignments"]
    ):
        result = forecast.calculate_unit(
            unit,
            scenario=prepared.provenance["scenario"],
            as_of=kwargs.get("as_of"),
        )
        if assignment is not None:
            result["provenance"]["county_assignment"] = assignment
        results.append(result)
    return _attach_results(frame, prepared, results)


def summarize_spm_units(
    frame, *, unit_entity: str, weight_entity: str
) -> dict:
    """Use Frame accounting for a unit-denominator, not person, poverty rate."""
    Frame, wmean, wsum = _frame_api()
    if not isinstance(frame, Frame):
        raise TypeError("Expected an actual microcosm.frame.Frame")
    frame.revalidate()
    provenance = _weight_source(frame, unit_entity, weight_entity)
    threshold_column = OUTPUT_COLUMNS["threshold"]
    poverty_column = OUTPUT_COLUMNS["is_in_poverty"]
    if frame.column_entity(threshold_column) != unit_entity:
        raise ValueError("Forecast thresholds are owned by a different entity")
    result = {
        "entity": unit_entity,
        "weights": provenance,
        "mean_threshold": wmean(frame, threshold_column, entity=unit_entity),
    }
    if frame.table(unit_entity)[poverty_column].notna().all():
        result["poor_units"] = wsum(frame, poverty_column, entity=unit_entity)
        result["unit_poverty_rate"] = wmean(
            frame, poverty_column, entity=unit_entity
        )
    else:
        result["poor_units"] = result["unit_poverty_rate"] = None
    return result
