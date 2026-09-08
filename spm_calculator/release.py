"""Portable, immutable SPM releases and a standard-library-only consumer.

The content digest detects changes; it is not a signature or proof of source
authenticity. Supply an independently retained expected digest for replay.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path
from types import MappingProxyType
from typing import Optional

TENURES = ("owner_with_mortgage", "owner_without_mortgage", "renter")
SCHEMA_VERSION = 1
DEFAULT_RELEASE = "spm-2026-09-08"


def _date(value, label):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", value
    ):
        raise ValueError(f"{label} must be an ISO calendar date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"Invalid {label}: {value}") from error


def _number(value, label, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(
            f"{label} must be finite" + (" and positive" if positive else "")
        )
    return float(value)


def _year(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1900 <= value <= 9999
    ):
        raise ValueError("year must be an integer from 1900 to 9999")
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _hash(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def canonical_bytes(document):
    """Canonical contract encoding (UTF-8, sorted keys, compact JSON)."""
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def release_digest(document):
    """Digest all document fields except the content digest itself."""
    return hashlib.sha256(
        canonical_bytes(
            {k: v for k, v in document.items() if k != "content_sha256"}
        )
    ).hexdigest()


def seal_release(document):
    """Return a validated copy with its computed integrity digest."""
    copy = json.loads(canonical_bytes(document))
    copy["content_sha256"] = release_digest(copy)
    return SPMRelease.from_dict(copy).to_dict()


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _validate(document):
    if (
        not isinstance(document, dict)
        or type(document.get("schema_version")) is not int
        or document.get("schema_version") != SCHEMA_VERSION
    ):
        raise ValueError("Unsupported SPM release schema_version")
    _text(document.get("release_id"), "release_id")
    created = _date(document.get("created_on"), "created_on")
    information = _date(document.get("information_date"), "information_date")
    if information > created:
        raise ValueError("information_date cannot follow created_on")
    if document.get("units") != "USD/year" or document.get(
        "reference_family"
    ) != {"adults": 2, "children": 2}:
        raise ValueError(
            "Releases require USD/year and a two-adult, two-child reference family"
        )
    sources = document.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Release must identify its sources")
    source_dates = {}
    for source in sources:
        identity = _text(source.get("id"), "source id")
        if identity in source_dates:
            raise ValueError(f"Duplicate source id: {identity}")
        _text(source.get("url"), "source URL")
        _hash(source.get("sha256"), "source sha256")
        available = _date(source.get("available_on"), "source available_on")
        if (
            source.get("publication_date") is not None
            and _date(source["publication_date"], "publication_date")
            > available
        ):
            raise ValueError("Source availability cannot precede publication")
        if available > information:
            raise ValueError(
                "Source is unavailable at the release information date"
            )
        source_dates[identity] = available
    entries = document.get("years")
    if not isinstance(entries, dict) or not entries:
        raise ValueError("Release must contain year entries")
    for year, entry in entries.items():
        if not isinstance(year, str) or not re.fullmatch(r"\d{4}", year):
            raise ValueError("Entry years must be four-digit strings")
        _year(int(year))
        if entry.get("status") not in {"published", "nowcast", "forecast"}:
            raise ValueError(
                "Entry status must be published, nowcast or forecast"
            )
        _text(entry.get("methodology_id"), "methodology_id")
        available = _date(entry.get("available_on"), "entry available_on")
        if available > information:
            raise ValueError(
                "Entry is unavailable at release information date"
            )
        ids = entry.get("source_ids")
        if (
            not isinstance(ids, list)
            or not ids
            or any(i not in source_dates for i in ids)
        ):
            raise ValueError("Entry must refer to known source ids")
        if any(source_dates[i] > available for i in ids):
            raise ValueError(
                "Entry availability precedes its source availability"
            )
        for field in ("thresholds", "housing_shares"):
            values = entry.get(field)
            if not isinstance(values, dict) or set(values) != set(TENURES):
                raise ValueError(
                    f"{field} must contain exactly the three tenures"
                )
            for tenure, value in values.items():
                value = _number(value, f"{field}.{tenure}", positive=True)
                if field == "housing_shares" and value >= 1:
                    raise ValueError("housing shares must be less than one")
        share = entry.get("housing_share_provenance")
        if (
            not isinstance(share, dict)
            or share.get("source_id") not in source_dates
        ):
            raise ValueError("Housing shares require a known source")
        _year(share.get("reference_year"))
        if share.get("status") not in {"published", "carried", "assumed"}:
            raise ValueError(
                "Housing shares require published/carried/assumed status"
            )
        if share["status"] == "published" and share["reference_year"] != int(
            year
        ):
            raise ValueError(
                "Published housing shares must match the entry reference year"
            )
        if (
            share["source_id"] not in ids
            or source_dates[share["source_id"]] > available
        ):
            raise ValueError(
                "Housing share source must be included and available for the entry"
            )
        _text(share.get("note"), "housing share note")
        uncertainty = entry.get("uncertainty")
        if not isinstance(uncertainty, dict) or "kind" not in uncertainty:
            raise ValueError(
                "Uncertainty must be explicit, including when unavailable"
            )
        if uncertainty["kind"] == "published_standard_error":
            errors = uncertainty.get("standard_errors", {})
            if set(errors) != set(TENURES) or any(
                _number(v, "standard error") < 0 for v in errors.values()
            ):
                raise ValueError(
                    "Published standard errors must cover all tenures and be nonnegative"
                )
        elif uncertainty["kind"] != "unavailable":
            raise ValueError("Unsupported uncertainty kind")
    geographies = document.get("geographies")
    if not isinstance(geographies, dict):
        raise ValueError("geographies must be an explicit object")
    for kind, geography in geographies.items():
        if kind not in {"metro", "congressional_district", "state", "county"}:
            raise ValueError(f"Unsupported bundled geography: {kind}")
        _text(geography.get("id"), "geography id")
        _year(geography.get("year"))
        if geography.get("source_id") not in source_dates:
            raise ValueError("Geography must refer to a known source")
        areas = geography.get("areas")
        if not isinstance(areas, dict) or not areas:
            raise ValueError("Bundled geography must contain areas")
        for identity, area in areas.items():
            _text(identity, "area id")
            _text(area.get("name"), "area name")
            _number(area.get("rent_index"), "rent_index", positive=True)
    expected = _hash(document.get("content_sha256"), "content_sha256")
    if release_digest(document) != expected:
        raise ValueError("SPM release content hash mismatch")


def equivalence_factor(num_adults, num_children):
    """Scale preclassified SPM adults/children; do not infer from ages."""
    for value, name, minimum in (
        (num_adults, "num_adults", 1),
        (num_children, "num_children", 0),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < minimum
        ):
            raise ValueError(f"{name} must be an integer >= {minimum}")
    from .equivalence_scale import spm_equivalence_scale

    try:
        return _number(
            spm_equivalence_scale(num_adults, num_children),
            "equivalence factor",
            positive=True,
        )
    except OverflowError as error:
        raise ValueError(
            "Composition exceeds supported numeric range"
        ) from error


@dataclass(frozen=True)
class SPMUnit:
    unit_id: str
    num_adults: int
    num_children: int
    tenure: str
    year: int
    resources: Optional[float] = None
    geography_kind: str = "national"
    geography_id: Optional[str] = None
    geographic_adjustment: Optional[float] = None
    geography_vintage: Optional[str] = None

    def __post_init__(self):
        _text(self.unit_id, "unit_id")
        _year(self.year)
        equivalence_factor(self.num_adults, self.num_children)
        if self.tenure not in TENURES:
            raise ValueError(f"Unknown tenure: {self.tenure}")
        if self.resources is not None:
            _number(self.resources, "resources")
        if self.geographic_adjustment is not None:
            _number(
                self.geographic_adjustment,
                "geographic_adjustment",
                positive=True,
            )
            if (
                self.geography_id is not None
                or self.geography_kind != "national"
            ):
                raise ValueError(
                    "Choose an explicit adjustment or a named geography"
                )
        elif self.geography_kind == "national":
            if self.geography_id is not None:
                raise ValueError("National geography does not take an area id")
        elif (
            self.geography_kind
            not in {"metro", "congressional_district", "state", "county"}
            or not self.geography_id
        ):
            raise ValueError(
                "Named geography requires a supported kind and area id"
            )


@dataclass(frozen=True, init=False)
class SPMRelease:
    """Immutable canonical bytes; every data accessor returns a new copy."""

    _json: bytes
    _identity: tuple
    _entries: object
    _geographies: object

    @classmethod
    def from_dict(cls, document, *, expected_sha256=None, as_of=None):
        try:
            snapshot = json.loads(canonical_bytes(document))
            _validate(snapshot)
        except (TypeError, KeyError, AttributeError) as error:
            raise ValueError(f"Malformed SPM release: {error}") from error
        if expected_sha256 is not None and snapshot["content_sha256"] != _hash(
            expected_sha256, "expected_sha256"
        ):
            raise ValueError("Release does not match expected_sha256")
        obj = object.__new__(cls)
        object.__setattr__(obj, "_json", canonical_bytes(snapshot))
        object.__setattr__(
            obj,
            "_identity",
            (
                snapshot["release_id"],
                snapshot["content_sha256"],
                snapshot["information_date"],
            ),
        )
        object.__setattr__(
            obj,
            "_entries",
            MappingProxyType(
                {
                    int(year): canonical_bytes(entry)
                    for year, entry in snapshot["years"].items()
                }
            ),
        )
        object.__setattr__(
            obj,
            "_geographies",
            MappingProxyType(
                {
                    kind: (
                        canonical_bytes(
                            {k: v for k, v in geo.items() if k != "areas"}
                        ),
                        MappingProxyType(
                            {
                                identity: canonical_bytes(area)
                                for identity, area in geo["areas"].items()
                            }
                        ),
                    )
                    for kind, geo in snapshot["geographies"].items()
                }
            ),
        )
        obj._check_as_of(as_of)
        return obj

    def to_dict(self):
        return json.loads(self._json)

    @property
    def release_id(self):
        return self._identity[0]

    @property
    def content_sha256(self):
        return self._identity[1]

    @property
    def years(self):
        return tuple(sorted(self._entries))

    @property
    def latest_published_year(self):
        years = [
            year
            for year, encoded in self._entries.items()
            if json.loads(encoded)["status"] == "published"
        ]
        if not years:
            raise ValueError("Release contains no published base year")
        return max(years)

    def _check_as_of(self, as_of):
        if as_of is not None and _date(as_of, "as_of") < _date(
            self._identity[2], "information_date"
        ):
            raise ValueError(
                "Release information date follows requested as_of"
            )

    def entry(self, year, *, allow_estimated=False, as_of=None):
        _year(year)
        self._check_as_of(as_of)
        encoded = self._entries.get(year)
        if encoded is None:
            raise ValueError(
                f"Release {self.release_id} has no entry for {year}"
            )
        entry = json.loads(encoded)
        if entry["status"] != "published" and not allow_estimated:
            raise ValueError("Estimated entry requires allow_estimated=True")
        return entry

    def geography_factor(
        self,
        year,
        tenure,
        *,
        kind="national",
        geoid=None,
        missing="error",
        allow_estimated=False,
    ):
        entry = self.entry(year, allow_estimated=allow_estimated)
        if tenure not in TENURES or missing not in {"error", "national"}:
            raise ValueError("Invalid tenure or missing-geography policy")
        if kind == "national":
            if geoid is not None:
                raise ValueError("National geography has no area id")
            return {
                "factor": 1.0,
                "kind": "national",
                "status": "explicit_national",
            }
        packed = self._geographies.get(kind)
        geography = json.loads(packed[0]) if packed else None
        identity = str(geoid)
        if kind == "congressional_district" and identity.isdigit():
            identity = str(int(identity))
        encoded_area = packed[1].get(identity) if packed else None
        area = json.loads(encoded_area) if encoded_area else None
        if area is None:
            if missing == "national":
                return {
                    "factor": 1.0,
                    "kind": kind,
                    "area_id": identity,
                    "status": "explicit_national_fallback",
                    "reason": "requested area unavailable in release",
                }
            raise ValueError(
                f"Geography {kind}:{identity} unavailable in release"
            )
        share = entry["housing_shares"][tenure]
        return {
            "factor": 1 - share + share * area["rent_index"],
            "kind": kind,
            "area_id": identity,
            "name": area["name"],
            "rent_index": area["rent_index"],
            "geography_release_id": geography["id"],
            "year": geography["year"],
            "source_id": geography["source_id"],
            "status": "pinned_rent_index",
            "housing_share_provenance": entry["housing_share_provenance"],
        }

    def calculate_unit(self, unit, *, allow_estimated=False, as_of=None):
        if not isinstance(unit, SPMUnit):
            raise TypeError("calculate_unit requires an SPMUnit")
        entry = self.entry(
            unit.year, allow_estimated=allow_estimated, as_of=as_of
        )
        geography = (
            {
                "factor": unit.geographic_adjustment,
                "kind": "explicit",
                "status": "caller_supplied",
                "vintage": unit.geography_vintage,
            }
            if unit.geographic_adjustment is not None
            else self.geography_factor(
                unit.year,
                unit.tenure,
                kind=unit.geography_kind,
                geoid=unit.geography_id,
                allow_estimated=allow_estimated,
            )
        )
        scale = equivalence_factor(unit.num_adults, unit.num_children)
        base = entry["thresholds"][unit.tenure]
        share = entry["housing_shares"][unit.tenure]
        adjusted_share = geography["factor"] + share - 1
        if adjusted_share < 0:
            raise ValueError(
                "Geographic adjustment implies a negative housing portion"
            )
        unadjusted = base * scale
        threshold = unadjusted * geography["factor"]
        housing_portion = unadjusted * adjusted_share
        for amount, label in (
            (unadjusted, "unadjusted threshold"),
            (threshold, "threshold"),
            (housing_portion, "housing portion"),
        ):
            _number(amount, label)
        return {
            "unit_id": unit.unit_id,
            "release_id": self.release_id,
            "release_sha256": self.content_sha256,
            "year": unit.year,
            "tenure": unit.tenure,
            "status": entry["status"],
            "methodology_id": entry["methodology_id"],
            "reference_threshold": base,
            "equivalence_factor": scale,
            "geographic_factor": geography["factor"],
            "unadjusted_threshold": unadjusted,
            "threshold": threshold,
            "housing_portion": housing_portion,
            "housing_share": share,
            "resources": unit.resources,
            "is_in_poverty": (
                None if unit.resources is None else unit.resources < threshold
            ),
            "provenance": {
                "information_date": self._identity[2],
                "geography": geography,
                "housing_share": entry["housing_share_provenance"],
                "uncertainty": entry["uncertainty"],
                "source_ids": entry["source_ids"],
            },
        }


def load_release(path=None, *, expected_sha256=None, as_of=None):
    """Load a local or bundled release. Never fetch network data."""
    if path is None:
        raw = (
            resources.files("spm_calculator")
            .joinpath(f"data/releases/{DEFAULT_RELEASE}.json")
            .read_text(encoding="utf-8")
        )
    else:
        raw = Path(path).read_text(encoding="utf-8")
    document = json.loads(raw, object_pairs_hook=_no_duplicate_keys)
    return SPMRelease.from_dict(
        document, expected_sha256=expected_sha256, as_of=as_of
    )
