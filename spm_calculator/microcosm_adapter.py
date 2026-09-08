"""Optional release application to an actual Microcosm Frame.

This adapter preserves existing SPM membership and declared survey/population
weights. It neither builds population data nor estimates CE thresholds.
"""

from __future__ import annotations

import hashlib
from typing import Mapping, Optional

from spm_calculator.release import SPMRelease, SPMUnit

DEFAULT_COLUMNS = {
    "num_adults": "spm_num_adults",
    "num_children": "spm_num_children",
    "tenure": "spm_tenure",
}
OUTPUT_COLUMNS = {
    "threshold": "spm_release_threshold",
    "housing_portion": "spm_release_housing_portion",
    "is_in_poverty": "spm_release_is_in_poverty",
    "release_id": "spm_release_id",
    "release_sha256": "spm_release_sha256",
    "status": "spm_release_status",
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
    """Validate an explicit source against Microcosm's inheritance contract.

    Resolution and all weighted arithmetic remain Microcosm operations.
    A requested sibling's weights are never used merely because they exist.
    """
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
        "resolved_values_sha256": hashlib.sha256(
            resolved.values.tobytes()
        ).hexdigest(),
    }


def apply_release_to_frame(
    frame,
    release: SPMRelease,
    *,
    year: int,
    unit_entity: str,
    weight_entity: str,
    membership_provenance: str,
    columns: Optional[Mapping[str, str]] = None,
    geography_kind: str = "national",
    allow_estimated: bool = False,
    as_of=None,
):
    """Return a new Frame with release results on existing SPM-unit rows.

    ``columns`` maps SPMUnit field names to columns owned by ``unit_entity``.
    It must include num_adults, num_children and tenure; optional fields are
    resources, geography_kind, geography_id and geographic_adjustment. Counts
    must already use SPM classification and sum to the linked membership.
    No age-based reconstruction, calibration, imputation or reweighting occurs.
    """
    Frame, _, _ = _frame_api()
    if not isinstance(frame, Frame):
        raise TypeError("Expected an actual microcosm.frame.Frame")
    frame.revalidate()
    if unit_entity not in frame.schema.group_entities:
        raise ValueError(
            "SPM units must be an explicitly declared group entity"
        )
    if (
        not isinstance(membership_provenance, str)
        or not membership_provenance.strip()
    ):
        raise ValueError("Explicit SPM membership provenance is required")
    weight_provenance = _weight_source(frame, unit_entity, weight_entity)
    mapping = dict(DEFAULT_COLUMNS if columns is None else columns)
    required = set(DEFAULT_COLUMNS)
    allowed = required | {
        "resources",
        "geography_kind",
        "geography_id",
        "geographic_adjustment",
    }
    if not required <= set(mapping) or not set(mapping) <= allowed:
        raise ValueError(
            "Column mapping must name the required supported SPMUnit fields"
        )
    table = frame.table(unit_entity)
    for name in mapping.values():
        if name not in table:
            raise ValueError(
                f"SPM input column {name!r} is absent from {unit_entity!r}"
            )
    id_column = frame.schema.id_column(unit_entity)
    membership_column = frame.schema.membership_column(unit_entity)
    member_counts = frame.person.groupby(membership_column, sort=False).size()
    results = []
    for row in table.to_dict(orient="records"):
        kwargs = {field: row[column] for field, column in mapping.items()}
        kwargs.setdefault("geography_kind", geography_kind)
        unit = SPMUnit(unit_id=str(row[id_column]), year=year, **kwargs)
        if (
            unit.num_adults + unit.num_children
            != member_counts.loc[row[id_column]]
        ):
            raise ValueError(
                f"SPM counts do not match linked membership for {unit.unit_id!r}"
            )
        results.append(
            release.calculate_unit(
                unit, allow_estimated=allow_estimated, as_of=as_of
            )
        )
    out_table = table.copy()
    for field, name in OUTPUT_COLUMNS.items():
        if field == "release_sha256":
            values = [release.content_sha256] * len(results)
        else:
            values = [result[field] for result in results]
        out_table[name] = values
    tables = {entity: frame.table(entity) for entity in frame.entities}
    tables.update({name: frame.link(name) for name in frame.links})
    tables[unit_entity] = out_table
    provenance = {
        "release_id": release.release_id,
        "release_sha256": release.content_sha256,
        "year": year,
        "unit_entity": unit_entity,
        "membership_column": membership_column,
        "membership_provenance": membership_provenance,
        "counts_classification": "supplied SPM adults/children; no age reconstruction",
        "weights": weight_provenance,
        "role": "population SPM unit threshold application; not CE estimation",
        "unit_results": results,
    }
    metadata = dict(frame.metadata)
    metadata["spm_release_application"] = provenance
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


def summarize_spm_units(
    frame, *, unit_entity: str, weight_entity: str
) -> dict:
    """Weighted SPM-unit statistics, not a person-level poverty-rate estimate.

    Microcosm resolves the exact entity's weights and performs all weighted
    sums/means. This function does not multiply by weights independently.
    """
    Frame, wmean, wsum = _frame_api()
    if not isinstance(frame, Frame):
        raise TypeError("Expected an actual microcosm.frame.Frame")
    frame.revalidate()
    provenance = _weight_source(frame, unit_entity, weight_entity)
    threshold_column = OUTPUT_COLUMNS["threshold"]
    poverty_column = OUTPUT_COLUMNS["is_in_poverty"]
    if frame.column_entity(threshold_column) != unit_entity:
        raise ValueError("Release thresholds are owned by a different entity")
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
        result["poor_units"] = None
        result["unit_poverty_rate"] = None
    return result
