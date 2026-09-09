"""Immutable rolling-window research forecasts with an offline consumer.

Estimation is separate: loading and calculating need only Python's standard
library. A content digest detects changes, but is not a source signature.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from types import MappingProxyType

from .release import (
    TENURES,
    SPMUnit,
    _date,
    _hash,
    _no_duplicate_keys,
    _number,
    _text,
    _year,
    canonical_bytes,
    equivalence_factor,
    release_digest,
)

DEFAULT_FORECAST = "rolling_forecast_2026_09_09.json"
METHOD = "rolling_ce_acs_v1"


def forecast_digest(document):
    """Hash canonical document content, excluding content_sha256 itself."""
    return release_digest(document)


def _counts(window, observed, projected, total):
    counts = [window.get(observed), window.get(projected)]
    if (
        any(type(n) is not int or n < 0 for n in counts)
        or sum(counts) != total
    ):
        raise ValueError(f"Window counts must sum to {total}")


def _validate(document):
    if (
        type(document.get("schema_version")) is not int
        or document["schema_version"] != 2
    ):
        raise ValueError("Unsupported forecast schema_version")
    if document.get("method") != METHOD:
        raise ValueError("Unsupported forecast method")
    if document.get("units") != "USD/year" or document.get(
        "reference_family"
    ) != {"adults": 2, "children": 2}:
        raise ValueError(
            "Forecast requires annual dollars and the reference family"
        )
    assumptions = document.get("assumptions")
    if not isinstance(assumptions, dict):
        raise ValueError("Forecast requires explicit assumptions")
    if (
        _hash(document.get("assumption_sha256"), "assumption_sha256")
        != hashlib.sha256(canonical_bytes(assumptions)).hexdigest()
    ):
        raise ValueError("Forecast assumption hash mismatch")
    _text(document.get("forecast_id"), "forecast_id")
    information = _date(document.get("information_date"), "information_date")
    if information > _date(document.get("created_on"), "created_on"):
        raise ValueError("information_date cannot follow created_on")
    _hash(document.get("base_release_sha256"), "base_release_sha256")
    areas = document.get("areas")
    if not isinstance(areas, dict) or not areas:
        raise ValueError("Forecast must identify its areas")
    for identity, area in areas.items():
        _text(identity, "area id")
        _text(area.get("name"), "area name")
        if area.get("area_type") not in {
            "msa",
            "state_metro_residual",
            "state_nonmetro",
            "modeled_residual_metro",
        }:
            raise ValueError("Invalid area type")
    sources = document.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Forecast must identify its sources")
    source_ids = set()
    for source in sources:
        identity = _text(source.get("id"), "source id")
        if identity in source_ids:
            raise ValueError("Duplicate source id")
        source_ids.add(identity)
        _text(source.get("url"), "source URL")
        _hash(source.get("sha256"), "source sha256")
        if (
            _date(source.get("available_on"), "source available_on")
            > information
        ):
            raise ValueError("Source follows forecast information date")
    scenarios = document.get("scenarios")
    if not isinstance(scenarios, dict) or not scenarios:
        raise ValueError("Forecast must contain scenarios")
    if document.get("default_scenario") not in scenarios:
        raise ValueError("Unknown default scenario")
    year_set = None
    for identity, scenario in scenarios.items():
        _text(identity, "scenario id")
        _text(scenario.get("label"), "scenario label")
        if _number(scenario.get("real_growth_rate"), "real_growth_rate") <= -1:
            raise ValueError("Real growth must exceed -100%")
        if identity == "ce_trend" and scenario.get("shrinkage") != 0.5:
            raise ValueError("ce_trend identifies the 0.5-shrunk scenario")
        if identity == "zero_real" and scenario["real_growth_rate"] != 0:
            raise ValueError("zero_real requires zero real growth")
        entries = scenario.get("years")
        if not isinstance(entries, dict) or not entries:
            raise ValueError("Scenario must contain year entries")
        if year_set is not None and set(entries) != year_set:
            raise ValueError("Scenarios must cover identical years")
        year_set = set(entries)
        for year, entry in entries.items():
            if not isinstance(year, str) or not re.fullmatch(r"\d{4}", year):
                raise ValueError("Entry years must be four-digit strings")
            target = _year(int(year))
            for field in ("thresholds", "housing_shares"):
                values = entry.get(field)
                if not isinstance(values, dict) or set(values) != set(TENURES):
                    raise ValueError(f"{field} must contain all three tenures")
                for value in values.values():
                    number = _number(value, field, positive=True)
                    if field == "housing_shares" and number >= 1:
                        raise ValueError("Housing shares must be below one")
            indices = entry.get("rent_indices")
            geography = entry.get("geography_by_area")
            if (
                not isinstance(indices, dict)
                or not indices
                or set(indices) - set(areas)
                or not isinstance(geography, dict)
                or set(geography) != set(indices)
            ):
                raise ValueError("Every year requires complete area coverage")
            for area_id, value in geography.items():
                if value.get("status") not in {
                    "published_anchor",
                    "modeled",
                    "modeled_unanchored",
                }:
                    raise ValueError("Invalid area geography status")
                anchor = value.get("anchor_status")
                if anchor not in {"published_anchor", "modeled_unanchored"}:
                    raise ValueError("Invalid area anchor status")
                if type(value.get("official_published_area")) is not bool:
                    raise ValueError("Area publication status must be boolean")
                if value["official_published_area"] != (
                    anchor == "published_anchor"
                ):
                    raise ValueError(
                        "Modeled area cannot claim an official anchor"
                    )
                if (
                    value["status"] == "published_anchor"
                    and anchor != "published_anchor"
                ) or (
                    anchor == "modeled_unanchored"
                    and value["status"] != "modeled_unanchored"
                ):
                    raise ValueError("Inconsistent area and anchor statuses")
                refs = value.get("source_ids")
                if (
                    not isinstance(refs, list)
                    or not refs
                    or set(refs) - source_ids
                ):
                    raise ValueError("Area must identify known sources")
            for value in indices.values():
                _number(value, "rent index", positive=True)
            diagnostics = entry.get("median_diagnostics", {})
            if not isinstance(diagnostics, dict):
                raise ValueError("median_diagnostics must be an object")
            for area_id, diagnostic in diagnostics.items():
                if area_id not in indices or not isinstance(diagnostic, dict):
                    raise ValueError("Invalid area median diagnostic")
                for flag in (
                    "thin_support",
                    "median_topcode_warning",
                    "local_median_topcode_warning",
                    "rent_index_topcode_warning",
                ):
                    if (
                        flag in diagnostic
                        and type(diagnostic[flag]) is not bool
                    ):
                        raise ValueError(f"Diagnostic {flag} must be boolean")
                for field in (
                    "unique_records",
                    "kish_effective_count",
                    "expected_whole_record_count",
                    "topcoded_weight_share",
                ):
                    if field in diagnostic:
                        value = _number(diagnostic[field], field)
                        if value < 0 or (
                            field == "topcoded_weight_share" and value > 1
                        ):
                            raise ValueError(f"Invalid diagnostic {field}")
            if entry.get("national_status") not in {"published", "forecast"}:
                raise ValueError("Invalid national status")
            if entry.get("geography_status") not in {
                "published_anchor",
                "modeled",
                "mixed",
            }:
                raise ValueError("Invalid geography_status")
            if entry.get("housing_share_status") not in {
                "published_anchor",
                "modeled",
            }:
                raise ValueError("Invalid housing_share_status")
            ce = entry["ce_window"]
            if (
                ce.get("start") != f"{target - 5}Q2"
                or ce.get("end") != f"{target}Q1"
            ):
                raise ValueError("CE window must match the SPM reference year")
            _counts(ce, "observed_quarters", "projected_quarters", 20)
            acs = entry["acs_window"]
            if acs.get("start") != target - 5 or acs.get("end") != target - 1:
                raise ValueError(
                    "ACS window must match the SPM reference year"
                )
            _counts(acs, "observed_years", "projected_years", 5)
    assignment = document.get("county_assignments")
    if not isinstance(assignment, dict):
        raise ValueError("Forecast requires county assignment provenance")
    for field in ("county_vintage", "boundary_vintage", "assignment_method"):
        _text(assignment.get(field), field)
    maps, year_maps = assignment.get("maps"), assignment.get("year_maps")
    if (
        not isinstance(maps, dict)
        or not maps
        or not isinstance(year_maps, dict)
        or set(year_maps) != year_set
    ):
        raise ValueError("Incomplete county assignment year coverage")
    for mapping in maps.values():
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError("Empty county assignment map")
        for county, area_id in mapping.items():
            if (
                not isinstance(county, str)
                or not re.fullmatch(r"\d{5}", county)
                or area_id not in areas
            ):
                raise ValueError("Invalid county assignment")
    for scenario in scenarios.values():
        for year, entry in scenario["years"].items():
            if year_maps[year] not in maps or set(
                maps[year_maps[year]].values()
            ) - set(entry["rent_indices"]):
                raise ValueError(
                    "County assigned to an area unavailable that year"
                )
    actual = hashlib.sha256(
        canonical_bytes({k: v for k, v in assignment.items() if k != "sha256"})
    ).hexdigest()
    if _hash(assignment.get("sha256"), "assignment sha256") != actual:
        raise ValueError("County assignment hash mismatch")
    expected = _hash(document.get("content_sha256"), "content_sha256")
    if forecast_digest(document) != expected:
        raise ValueError("SPM forecast content hash mismatch")


def seal_forecast(document):
    """Copy, seal and validate an assembled research forecast."""
    snapshot = json.loads(canonical_bytes(document))
    snapshot["content_sha256"] = forecast_digest(snapshot)
    return SPMForecast.from_dict(snapshot).to_dict()


@dataclass(frozen=True, init=False)
class SPMForecast:
    """Immutable projected inputs; accessors always return detached copies."""

    _json: bytes
    _identity: tuple
    _entries: object
    _calculation_entries: object
    _areas: object
    _assignments: object

    @classmethod
    def from_dict(cls, document, *, expected_sha256=None, as_of=None):
        try:
            snapshot = json.loads(canonical_bytes(document))
            _validate(snapshot)
        except (TypeError, KeyError, AttributeError) as error:
            raise ValueError(f"Malformed SPM forecast: {error}") from error
        if expected_sha256 is not None and snapshot["content_sha256"] != _hash(
            expected_sha256, "expected_sha256"
        ):
            raise ValueError("Forecast does not match expected_sha256")
        obj = object.__new__(cls)
        object.__setattr__(obj, "_json", canonical_bytes(snapshot))
        object.__setattr__(
            obj,
            "_identity",
            (
                snapshot["forecast_id"],
                snapshot["content_sha256"],
                snapshot["information_date"],
                snapshot["default_scenario"],
                snapshot["base_release_sha256"],
            ),
        )
        object.__setattr__(
            obj,
            "_entries",
            MappingProxyType(
                {
                    identity: MappingProxyType(
                        {
                            int(year): canonical_bytes(entry)
                            for year, entry in scenario["years"].items()
                        }
                    )
                    for identity, scenario in snapshot["scenarios"].items()
                }
            ),
        )
        object.__setattr__(
            obj,
            "_areas",
            MappingProxyType(
                {
                    identity: canonical_bytes(area)
                    for identity, area in snapshot["areas"].items()
                }
            ),
        )
        # Unit calculations decode only one area's immutable inputs. Decoding
        # every area's support diagnostics per household is unnecessarily costly.
        object.__setattr__(
            obj,
            "_calculation_entries",
            MappingProxyType(
                {
                    identity: MappingProxyType(
                        {
                            int(year): MappingProxyType(
                                {
                                    "entry": canonical_bytes(
                                        {
                                            k: v
                                            for k, v in entry.items()
                                            if k
                                            not in {
                                                "rent_indices",
                                                "geography_by_area",
                                                "median_diagnostics",
                                            }
                                        }
                                    ),
                                    "areas": MappingProxyType(
                                        {
                                            code: canonical_bytes(
                                                {
                                                    "rent_index": value,
                                                    "geography": entry[
                                                        "geography_by_area"
                                                    ][code],
                                                    "diagnostics": entry.get(
                                                        "median_diagnostics",
                                                        {},
                                                    ).get(code, {}),
                                                }
                                            )
                                            for code, value in entry[
                                                "rent_indices"
                                            ].items()
                                        }
                                    ),
                                }
                            )
                            for year, entry in scenario["years"].items()
                        }
                    )
                    for identity, scenario in snapshot["scenarios"].items()
                }
            ),
        )
        obj._check_as_of(as_of)
        assignment = snapshot["county_assignments"]
        object.__setattr__(
            obj,
            "_assignments",
            MappingProxyType(
                {
                    "metadata": canonical_bytes(
                        {
                            k: v
                            for k, v in assignment.items()
                            if k not in {"maps", "year_maps"}
                        }
                    ),
                    "year_maps": MappingProxyType(assignment["year_maps"]),
                    "maps": MappingProxyType(
                        {
                            name: MappingProxyType(rows)
                            for name, rows in assignment["maps"].items()
                        }
                    ),
                }
            ),
        )
        return obj

    def to_dict(self):
        return json.loads(self._json)

    @property
    def forecast_id(self):
        return self._identity[0]

    @property
    def content_sha256(self):
        return self._identity[1]

    @property
    def default_scenario(self):
        return self._identity[3]

    @property
    def years(self):
        return tuple(sorted(self._entries[self.default_scenario]))

    def _check_as_of(self, as_of):
        if as_of is not None and _date(as_of, "as_of") < _date(
            self._identity[2], "information_date"
        ):
            raise ValueError(
                "Forecast information date follows requested as_of"
            )

    def entry(self, year, *, scenario=None, as_of=None):
        identity = self._validate_selection(year, scenario, as_of)
        return json.loads(self._entries[identity][year])

    def _validate_selection(self, year, scenario, as_of):
        _year(year)
        self._check_as_of(as_of)
        identity = self.default_scenario if scenario is None else scenario
        if identity not in self._entries:
            raise ValueError(f"Unknown forecast scenario: {identity}")
        if year not in self._entries[identity]:
            raise ValueError(f"Forecast has no entry for {year}")
        return identity

    def _calculation_entry(self, year, scenario, as_of, geoid=None):
        identity = self._validate_selection(year, scenario, as_of)
        packed = self._calculation_entries[identity][year]
        entry = json.loads(packed["entry"])
        code = str(geoid)
        selected = packed["areas"].get(code)
        area = json.loads(selected) if selected is not None else None
        entry["rent_indices"] = (
            {} if area is None else {code: area["rent_index"]}
        )
        entry["geography_by_area"] = (
            {} if area is None else {code: area["geography"]}
        )
        entry["median_diagnostics"] = (
            {} if area is None else {code: area["diagnostics"]}
        )
        return entry

    def _geography(self, entry, tenure, kind, geoid):
        if tenure not in TENURES:
            raise ValueError(f"Unknown tenure: {tenure}")
        if kind == "national":
            if geoid is not None:
                raise ValueError("National geography has no area id")
            return {"factor": 1.0, "kind": kind, "status": "explicit_national"}
        if kind != "metro":
            raise ValueError(f"Forecast geography is unsupported: {kind}")
        identity = str(geoid)
        if identity not in entry["rent_indices"]:
            raise ValueError(f"Forecast geography unavailable: {identity}")
        rent_index = entry["rent_indices"][identity]
        share = entry["housing_shares"][tenure]
        return {
            "factor": 1 + share * (rent_index - 1),
            "kind": kind,
            "area_id": identity,
            "name": json.loads(self._areas[identity])["name"],
            "rent_index": rent_index,
            "area_type": json.loads(self._areas[identity])["area_type"],
            **entry["geography_by_area"][identity],
            "diagnostics": entry.get("median_diagnostics", {}).get(
                identity, {}
            ),
        }

    def areas_for_year(self, year, *, scenario=None, as_of=None):
        """Return the selected year's area menu with each component's status."""
        entry = self.entry(year, scenario=scenario, as_of=as_of)
        return {
            area_id: {**json.loads(self._areas[area_id]), **metadata}
            for area_id, metadata in entry["geography_by_area"].items()
        }

    def resolve_county(
        self,
        year,
        county_fips,
        *,
        county_vintage="2020",
        scenario=None,
        as_of=None,
    ):
        """Assign a county to its SPM area; counties are not estimation units."""
        identity = self._validate_selection(year, scenario, as_of)
        meta = json.loads(self._assignments["metadata"])
        if county_vintage != meta["county_vintage"]:
            raise ValueError(f"Unsupported county vintage: {county_vintage}")
        if not isinstance(county_fips, str) or not re.fullmatch(
            r"\d{5}", county_fips
        ):
            raise ValueError("County FIPS must be a five-digit string")
        map_id = self._assignments["year_maps"][str(year)]
        area_id = self._assignments["maps"][map_id].get(county_fips)
        if (
            area_id is None
            or area_id
            not in self._calculation_entries[identity][year]["areas"]
        ):
            raise ValueError(
                f"County assignment unavailable for {county_fips}/{year}"
            )
        return {
            "area_id": area_id,
            "kind": "metro",
            "county_fips": county_fips,
            "county_vintage": county_vintage,
            "boundary_vintage": meta["boundary_vintage"],
            "assignment_method": meta["assignment_method"],
            "assignment_sha256": meta["sha256"],
            "status": "research_assignment",
        }

    def geography_factor(
        self,
        year,
        tenure,
        *,
        scenario=None,
        kind="national",
        geoid=None,
        as_of=None,
    ):
        entry = self._calculation_entry(year, scenario, as_of, geoid)
        return self._geography(entry, tenure, kind, geoid)

    def calculate_unit(self, unit, *, scenario=None, as_of=None):
        """Calculate with the selected year's thresholds, shares and rents."""
        if not isinstance(unit, SPMUnit):
            raise TypeError("calculate_unit requires an SPMUnit")
        identity = self.default_scenario if scenario is None else scenario
        entry = self._calculation_entry(
            unit.year, identity, as_of, unit.geography_id
        )
        geography = (
            {
                "factor": unit.geographic_adjustment,
                "kind": "explicit",
                "status": "caller_supplied",
                "vintage": unit.geography_vintage,
            }
            if unit.geographic_adjustment is not None
            else self._geography(
                entry, unit.tenure, unit.geography_kind, unit.geography_id
            )
        )
        base = entry["thresholds"][unit.tenure]
        share = entry["housing_shares"][unit.tenure]
        scale = equivalence_factor(unit.num_adults, unit.num_children)
        adjusted_share = geography["factor"] + share - 1
        if adjusted_share < 0:
            raise ValueError(
                "Geographic adjustment implies a negative housing portion"
            )
        unadjusted = base * scale
        threshold = unadjusted * geography["factor"]
        housing_portion = unadjusted * adjusted_share
        for amount in (unadjusted, threshold, housing_portion):
            _number(amount, "calculated amount")
        return {
            "unit_id": unit.unit_id,
            "year": unit.year,
            "tenure": unit.tenure,
            "forecast_id": self.forecast_id,
            "forecast_sha256": self.content_sha256,
            "base_release_sha256": self._identity[4],
            "scenario": identity,
            "methodology_id": METHOD,
            "national_status": entry["national_status"],
            "geography_status": geography["status"],
            "bundled_geography_status": entry["geography_status"],
            "housing_share_status": entry["housing_share_status"],
            "reference_threshold": base,
            "equivalence_factor": scale,
            "geographic_factor": geography["factor"],
            "unadjusted_threshold": unadjusted,
            "threshold": threshold,
            "housing_share": share,
            "housing_portion": housing_portion,
            "resources": unit.resources,
            "is_in_poverty": (
                None if unit.resources is None else unit.resources < threshold
            ),
            "provenance": {
                "information_date": self._identity[2],
                "geography": geography,
                "ce_window": entry["ce_window"],
                "acs_window": entry["acs_window"],
                "uncertainty": "not estimated",
            },
        }


def load_forecast(path=None, *, expected_sha256=None, as_of=None):
    """Read a local or bundled research forecast; never acquire data."""
    raw = (
        resources.files("spm_calculator")
        .joinpath(f"data/current/{DEFAULT_FORECAST}")
        .read_text(encoding="utf-8")
        if path is None
        else Path(path).read_text(encoding="utf-8")
    )
    document = json.loads(raw, object_pairs_hook=_no_duplicate_keys)
    return SPMForecast.from_dict(
        document, expected_sha256=expected_sha256, as_of=as_of
    )
