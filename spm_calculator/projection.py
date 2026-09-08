"""Threshold projection from explicitly dated statistical inputs.

This module constructs estimates; it neither forecasts missing expenditure
inputs nor establishes a historical real-time experiment. Retrospective
mode is the default. Callers must record actual availability dates or a
documented conservative bound (such as the archived acquisition date),
never an inferred historical release date. Frozen commitments are separate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Mapping, Optional, Union

TENURES = ("renter", "owner_with_mortgage", "owner_without_mortgage")


def _date(value: str) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Dates must be ISO YYYY-MM-DD strings")
    return date.fromisoformat(value)


def _year(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("Year must be a positive integer")


def _positive(value: float) -> float:
    if isinstance(value, bool):
        raise ValueError("Projection values must be finite and positive")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Projection values must be numeric") from error
    if not math.isfinite(result) or result <= 0:
        raise ValueError("Projection values must be finite and positive")
    return result


@dataclass(frozen=True)
class ProjectionInput:
    """Immutable input with its own year, method and availability date.

    ``values`` is exactly three tenure thresholds for published/replication
    inputs or one index level for price inputs. ``source_id`` should bind
    the input to the caller's checksummed release/replication manifest.
    """

    year: int
    values: Union[float, Mapping[str, float]]
    kind: str
    available_on: str
    source_id: str
    methodology_id: str

    def __post_init__(self) -> None:
        _year(self.year)
        _date(self.available_on)
        if self.kind not in ("published", "replication", "price"):
            raise ValueError(
                "Input kind must be published, replication or price"
            )
        for field in ("source_id", "methodology_id"):
            if (
                not isinstance(getattr(self, field), str)
                or not getattr(self, field).strip()
            ):
                raise ValueError(f"{field} must be a nonempty string")
        if self.kind == "price":
            object.__setattr__(self, "values", _positive(self.values))
        else:
            if not isinstance(self.values, Mapping) or set(self.values) != set(
                TENURES
            ):
                raise ValueError(
                    "Threshold inputs require exactly three tenures"
                )
            object.__setattr__(
                self,
                "values",
                MappingProxyType(
                    {
                        tenure: _positive(self.values[tenure])
                        for tenure in TENURES
                    }
                ),
            )

    def to_dict(self) -> dict:
        """Return an isolated JSON-compatible provenance record."""
        return {
            "year": self.year,
            "values": (
                dict(self.values)
                if isinstance(self.values, Mapping)
                else self.values
            ),
            "kind": self.kind,
            "available_on": self.available_on,
            "source_id": self.source_id,
            "methodology_id": self.methodology_id,
        }


def project_thresholds(
    official_base: ProjectionInput,
    target_year: int,
    *,
    as_of: str,
    method: str,
    replicated_base: Optional[ProjectionInput] = None,
    replicated_target: Optional[ProjectionInput] = None,
    price_base: Optional[ProjectionInput] = None,
    price_target: Optional[ProjectionInput] = None,
    blend_weight: float = 0.5,
    evaluation_mode: str = "retrospective",
) -> dict:
    """Anchor a replication ratio, price ratio, or blend to official levels.

    ``blend_weight`` is the replication-ratio share. A prospective label
    describes the caller's declared experiment, not a timestamp commitment;
    every input is still checked against ``as_of``. This operation does not
    publish a release entry or infer any sampling/forecast interval.
    """
    _year(target_year)
    cutoff = _date(as_of)
    if official_base.kind != "published":
        raise ValueError("official_base must be a published input")
    if target_year <= official_base.year:
        raise ValueError("Target year must be later than official base year")
    if evaluation_mode not in ("retrospective", "prospective"):
        raise ValueError(
            "evaluation_mode must be retrospective or prospective"
        )
    if method not in ("replication_ratio", "price_only", "blend"):
        raise ValueError("Unknown projection method")
    if (
        isinstance(blend_weight, bool)
        or not isinstance(blend_weight, (float, int))
        or not math.isfinite(blend_weight)
        or not 0 <= blend_weight <= 1
    ):
        raise ValueError("blend_weight must be finite and in [0, 1]")
    supplied = {
        "official_base": official_base,
        "replicated_base": replicated_base,
        "replicated_target": replicated_target,
        "price_base": price_base,
        "price_target": price_target,
    }
    required = {"official_base"}
    if method in ("replication_ratio", "blend"):
        required.update(("replicated_base", "replicated_target"))
    if method in ("price_only", "blend"):
        required.update(("price_base", "price_target"))
    unused = [
        name
        for name, value in supplied.items()
        if value is not None and name not in required
    ]
    if unused:
        raise ValueError(f"Projection received unused inputs: {unused}")
    for name in required:
        item = supplied[name]
        if not isinstance(item, ProjectionInput):
            raise ValueError(f"Projection requires {name}")
        expected_year = (
            target_year if name.endswith("target") else official_base.year
        )
        expected_kind = (
            "published"
            if name == "official_base"
            else ("price" if name.startswith("price") else "replication")
        )
        if item.year != expected_year or item.kind != expected_kind:
            raise ValueError(
                f"{name} must have year={expected_year}, kind={expected_kind}"
            )
        if _date(item.available_on) > cutoff:
            raise ValueError(
                f"{name} was available on {item.available_on}, after as_of={as_of}"
            )
    for base, target in (
        (replicated_base, replicated_target),
        (price_base, price_target),
    ):
        if (
            base is not None
            and target is not None
            and base.methodology_id != target.methodology_id
        ):
            raise ValueError(
                "Base and target inputs must use the same methodology"
            )
    ratios = {}
    for tenure in TENURES:
        if method == "replication_ratio":
            factor = (
                replicated_target.values[tenure]
                / replicated_base.values[tenure]
            )
        elif method == "price_only":
            factor = price_target.values / price_base.values
        else:
            factor = (
                blend_weight
                * replicated_target.values[tenure]
                / replicated_base.values[tenure]
                + (1 - blend_weight) * price_target.values / price_base.values
            )
        ratios[tenure] = factor
    thresholds = {
        tenure: _positive(official_base.values[tenure] * ratios[tenure])
        for tenure in TENURES
    }
    return {
        "target_year": target_year,
        "base_year": official_base.year,
        "as_of": as_of,
        "methodology_id": f"anchored_{method}_v1",
        "evaluation_mode": evaluation_mode,
        "thresholds": thresholds,
        "growth_factors": ratios,
        "blend_weight": blend_weight if method == "blend" else None,
        "inputs": {
            name: supplied[name].to_dict() for name in sorted(required)
        },
        "uncertainty": {
            "status": "unavailable",
            "reason": "Input uncertainty and forecast errors not estimated",
        },
    }
