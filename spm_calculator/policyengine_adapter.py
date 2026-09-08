"""Explicit SPM release integration for PolicyEngine's country formulas.

Importing this module does not import PolicyEngine. The optional model imports
occur only when building a reform. The release and options are immutable;
evaluation receipts and once-per-year warning bookkeeping are private copies.
This is a development integration, not a certified population-data bundle.
"""

from __future__ import annotations

import copy
import math
import warnings
from dataclasses import dataclass, field
from importlib import metadata
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .release import SPMRelease


FORMULA_OWNED_INPUTS = frozenset(
    {
        "spm_unit_reference_spm_threshold",
        "spm_unit_unadjusted_spm_threshold",
        "spm_unit_spm_threshold",
        "spm_unit_spm_threshold_housing_portion",
        "spm_unit_geographic_adjustment",
        "spm_unit_count_adults",
        "spm_unit_count_children",
        "spm_unit_capped_housing_subsidy",
        "spm_unit_net_income",
        "spm_unit_benefits",
        "spm_unit_is_in_spm_poverty",
        "spm_unit_is_in_deep_spm_poverty",
        "poverty_line",
        "poverty_gap",
        "is_adult",
        "is_child",
    }
)


def runtime_versions():
    """Actual installed distributions, rather than a certified bundle label."""
    result = {}
    for package in (
        "policyengine",
        "policyengine-us",
        "policyengine-core",
        "spm-calculator",
    ):
        try:
            result[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            result[package] = None
    return result


def validate_policyengine_inputs(entity_records):
    """Reject inputs which would bypass SPM formulas; never rewrite membership.

    Accept an entity -> sequence-of-records mapping, or entity -> DataFrame
    mapping. Observed Census outputs may be retained under separate report-only
    names. This check does not certify population data or its resource methods.
    """
    conflicts = []
    for entity, records in entity_records.items():
        if hasattr(records, "columns"):
            keys = set(records.columns)
        else:
            keys = {key for record in records for key in record}
        conflicts.extend(
            f"{entity}.{name}" for name in sorted(keys & FORMULA_OWNED_INPUTS)
        )
    if conflicts:
        raise ValueError(
            "SPM release formulas cannot run with computed outputs supplied as inputs: "
            + ", ".join(conflicts)
            + ". Retain observed Census values under separate report-only names."
        )


@dataclass(frozen=True)
class PolicyEngineSPMProvider:
    """A simulation-specific immutable release and explicit consumer policies.

    ``pe_cpi_u`` is PE-owned extrapolation, not release data. A supplied forecast
    wins only when ``allow_estimated`` is explicit. Unknown geography errors by
    default. ``geographic_adjustment`` is a whole-threshold factor, not rent.
    """

    release: SPMRelease
    year_policy: str = "pe_cpi_u"
    allow_estimated: bool = False
    geography_kind: str = "national"
    geography_id: Optional[str] = None
    geographic_adjustment: Optional[float] = None
    geography_vintage: Optional[str] = None
    missing_geography: str = "error"
    as_of: Optional[str] = None
    _warned_years: set = field(
        default_factory=set, init=False, repr=False, compare=False
    )
    _year_receipts: dict = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _geography_receipts: dict = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self):
        from .release import SPMRelease

        if not isinstance(self.release, SPMRelease):
            raise TypeError("release must be a verified SPMRelease")
        snapshot = SPMRelease.from_dict(
            self.release.to_dict(),
            expected_sha256=self.release.content_sha256,
            as_of=self.as_of,
        )
        object.__setattr__(self, "release", snapshot)
        if self.year_policy not in {"error", "pe_cpi_u"}:
            raise ValueError("year_policy must be error or pe_cpi_u")
        if not isinstance(self.allow_estimated, bool):
            raise ValueError("allow_estimated must be boolean")
        if self.missing_geography not in {"error", "national"}:
            raise ValueError("missing_geography must be error or national")
        if self.geography_kind not in {
            "national",
            "metro",
            "congressional_district",
            "explicit",
        }:
            raise ValueError("Unsupported geography_kind")
        if self.geography_kind == "explicit":
            value = self.geographic_adjustment
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(
                    "Explicit geographic adjustment must be finite and positive"
                )
            if (
                not isinstance(self.geography_vintage, str)
                or not self.geography_vintage.strip()
                or self.geography_id is not None
            ):
                raise ValueError(
                    "Explicit adjustment needs its vintage and no area id"
                )
        elif self.geographic_adjustment is not None:
            raise ValueError(
                "geographic_adjustment requires geography_kind='explicit'"
            )
        elif (
            self.geography_kind == "national" and self.geography_id is not None
        ):
            raise ValueError("National geography does not take an area id")
        elif self.geography_kind == "metro" and self.geography_id is None:
            raise ValueError("Metro geography requires an area id")

    def snapshot(self):
        """Fresh provider state for one simulation; no process-wide switching."""
        return type(self)(
            **{
                name: getattr(self, name)
                for name in (
                    "release",
                    "year_policy",
                    "allow_estimated",
                    "geography_kind",
                    "geography_id",
                    "geographic_adjustment",
                    "geography_vintage",
                    "missing_geography",
                    "as_of",
                )
            }
        )

    def year_metadata(self, year, *, cpi_u=None):
        """Return an isolated entry plus exact evaluated CPI provenance."""
        if isinstance(year, bool) or not isinstance(year, int):
            raise ValueError("year must be an integer")
        existing = (
            self.release.entry(year, allow_estimated=True, as_of=self.as_of)
            if year in self.release.years
            else None
        )
        if existing is not None and (
            existing["status"] == "published" or self.allow_estimated
        ):
            entry = existing
            entry["geography_threshold_year"] = year
        else:
            base_year = self.release.latest_published_year
            if self.year_policy == "error":
                raise ValueError(
                    f"No permitted release entry for {year}; estimated entries require allow_estimated=True"
                )
            if year <= base_year:
                raise ValueError(
                    f"Cannot extrapolate a missing or unpermitted past/interior year {year}"
                )
            if cpi_u is None:
                raise ValueError(
                    "PE CPI extrapolation requires the actual model CPI-U parameter"
                )
            base = self.release.entry(base_year, as_of=self.as_of)
            endpoints = {}
            for name, endpoint_year in (("base", base_year), ("target", year)):
                instant = f"{endpoint_year}-02-01"
                value = float(cpi_u(instant))
                if not math.isfinite(value) or value <= 0:
                    raise ValueError(
                        "Model CPI-U endpoints must be finite and positive"
                    )
                endpoints[name] = {
                    "year": endpoint_year,
                    "instant": instant,
                    "value": value,
                    "classification": "unknown_model_parameter_classification",
                }
            ratio = endpoints["target"]["value"] / endpoints["base"]["value"]
            share_provenance = copy.deepcopy(base["housing_share_provenance"])
            share_provenance.update(
                status="carried",
                carried_from_threshold_year=base_year,
                target_year=year,
                consumer_extrapolation=True,
            )
            entry = {
                "status": "consumer_extrapolation",
                "methodology_id": "pe_cpi_u",
                "method": "pe_cpi_u",
                "base_year": base_year,
                "target_year": year,
                "base_release_sha256": self.release.content_sha256,
                "thresholds": {
                    tenure: value * ratio
                    for tenure, value in base["thresholds"].items()
                },
                "housing_shares": copy.deepcopy(base["housing_shares"]),
                "housing_share_provenance": share_provenance,
                "source_ids": list(base["source_ids"]),
                "geography_threshold_year": base_year,
                "uncertainty": {
                    "kind": "unavailable",
                    "note": "No extrapolation interval estimated",
                },
                "cpi": {
                    "parameter_path": "gov.bls.cpi.cpi_u",
                    "series": "PE model CPI-U parameter",
                    "ratio": ratio,
                    **endpoints,
                    "classification_note": "Model parameter metadata does not establish observed versus projected endpoint values",
                    "parameter_metadata": copy.deepcopy(
                        getattr(cpi_u, "metadata", {})
                    ),
                    "runtime_versions": runtime_versions(),
                },
                "unused_release_estimate": (
                    None
                    if existing is None
                    else {
                        "status": existing["status"],
                        "methodology_id": existing["methodology_id"],
                        "release_id": self.release.release_id,
                        "year": year,
                        "reason": "allow_estimated=False",
                    }
                ),
            }
            if year not in self._warned_years:
                warnings.warn(
                    f"SPM {year} uses PE CPI-U consumer extrapolation from published {base_year}; it is not a published release threshold",
                    UserWarning,
                    stacklevel=2,
                )
                self._warned_years.add(year)
        entry.update(
            release_id=self.release.release_id,
            release_sha256=self.release.content_sha256,
            year=year,
        )
        self._year_receipts[year] = copy.deepcopy(entry)
        return copy.deepcopy(entry)

    def geography_metadata(self, year, tenure, *, geoid=None, cpi_u=None):
        """Resolve only release-pinned geography or an explicit caller factor."""
        entry = self.year_metadata(year, cpi_u=cpi_u)
        if self.geography_kind == "explicit":
            result = {
                "factor": float(self.geographic_adjustment),
                "kind": "explicit",
                "status": "caller_supplied",
                "vintage": self.geography_vintage,
            }
        else:
            identity = (
                self.geography_id if self.geography_id is not None else geoid
            )
            if self.geography_kind == "national":
                identity = None
            result = self.release.geography_factor(
                entry["geography_threshold_year"],
                tenure,
                kind=self.geography_kind,
                geoid=identity,
                missing=self.missing_geography,
                allow_estimated=self.allow_estimated,
            )
        if result["factor"] + entry["housing_shares"][tenure] - 1 < 0:
            raise ValueError(
                "Geographic adjustment implies a negative housing portion"
            )
        result.update(
            target_year=year,
            tenure=tenure,
            housing_share_provenance=copy.deepcopy(
                entry["housing_share_provenance"]
            ),
        )
        key = (year, tenure, result.get("kind"), result.get("area_id"))
        self._geography_receipts[key] = copy.deepcopy(result)
        return copy.deepcopy(result)

    def provenance(self):
        """Only JSON-compatible receipts; never expose provider objects."""
        return {
            "integration_status": "development_household_integration",
            "release_id": self.release.release_id,
            "release_sha256": self.release.content_sha256,
            "information_date": self.release.to_dict()["information_date"],
            "year_policy": self.year_policy,
            "allow_estimated": self.allow_estimated,
            "missing_geography": self.missing_geography,
            "runtime_versions": runtime_versions(),
            "years": {
                str(year): copy.deepcopy(value)
                for year, value in sorted(self._year_receipts.items())
            },
            "geographies": [
                copy.deepcopy(value)
                for value in self._geography_receipts.values()
            ],
            "composition_method": "Existing PolicyEngine SPM membership and is_adult/is_child formulas; Census independent-teen parity not established",
            "population_data_certified": False,
        }


def build_policyengine_reform(provider):
    """Build per-simulation formula classes over an immutable release snapshot.

    The returned class exposes its bound ``spm_release_provider`` for receipts.
    Caller-supplied formula outputs must first pass validate_policyengine_inputs.
    """
    import numpy as np
    from policyengine_core.periods import YEAR
    from policyengine_core.reforms import Reform
    from policyengine_core.variables import Variable
    from policyengine_us.entities import SPMUnit
    from policyengine_us.variables.household.income.spm_unit.spm_unit_tenure_type import (
        SPMUnitTenureType,
    )

    from .equivalence_scale import spm_equivalence_scale

    if not isinstance(provider, PolicyEngineSPMProvider):
        raise TypeError("provider must be a PolicyEngineSPMProvider")
    bound = provider.snapshot()

    def tenure_keys(spm_unit, period):
        tenure = spm_unit("spm_unit_tenure_type", period)
        result = np.full(len(tenure), "", dtype=object)
        for enum in SPMUnitTenureType:
            result = np.where(tenure == enum, enum.name.lower(), result)
        if np.any(result == ""):
            raise ValueError("Unrecognized PolicyEngine SPM tenure")
        return result

    def entry(period, parameters):
        return bound.year_metadata(
            period.start.year, cpi_u=parameters.gov.bls.cpi.cpi_u
        )

    class spm_unit_reference_spm_threshold(Variable):
        value_type = float
        entity = SPMUnit
        definition_period = YEAR
        label = "SPM reference threshold from an explicit release"
        unit = "currency-USD"

        def formula(spm_unit, period, parameters):
            values = entry(period, parameters)["thresholds"]
            return np.array(
                [values[key] for key in tenure_keys(spm_unit, period)]
            )

    class spm_unit_unadjusted_spm_threshold(Variable):
        value_type = float
        entity = SPMUnit
        definition_period = YEAR
        label = "SPM threshold before geographic adjustment"
        unit = "currency-USD"

        def formula(spm_unit, period, parameters):
            adults = spm_unit("spm_unit_count_adults", period)
            children = spm_unit("spm_unit_count_children", period)
            if np.any(
                ~np.isfinite(adults)
                | ~np.isfinite(children)
                | (adults < 1)
                | (children < 0)
                | (adults != np.floor(adults))
                | (children != np.floor(children))
            ):
                raise ValueError(
                    "SPM release calculation requires at least one classified "
                    "SPM adult and nonnegative whole child counts; minor-only "
                    "units need an explicit classification decision"
                )
            return spm_unit(
                "spm_unit_reference_spm_threshold", period
            ) * spm_equivalence_scale(adults, children)

    class spm_unit_geographic_adjustment(Variable):
        value_type = float
        entity = SPMUnit
        definition_period = YEAR
        label = "Explicit release geographic adjustment"
        default_value = 1.0

        def formula(spm_unit, period, parameters):
            tenures = tenure_keys(spm_unit, period)
            geoids = (
                spm_unit.household("congressional_district_geoid", period)
                if bound.geography_kind == "congressional_district"
                and bound.geography_id is None
                else [None] * len(tenures)
            )
            values = {}
            result = []
            for tenure, geoid in zip(tenures, geoids):
                identity = None if geoid is None else str(int(geoid))
                key = (tenure, identity)
                if key not in values:
                    values[key] = bound.geography_metadata(
                        period.start.year,
                        tenure,
                        geoid=identity,
                        cpi_u=parameters.gov.bls.cpi.cpi_u,
                    )["factor"]
                result.append(values[key])
            return np.asarray(result)

    class spm_unit_spm_threshold(Variable):
        value_type = float
        entity = SPMUnit
        definition_period = YEAR
        label = "SPM poverty threshold from an explicit release"
        unit = "currency-USD"

        def formula(spm_unit, period, parameters):
            return spm_unit(
                "spm_unit_unadjusted_spm_threshold", period
            ) * spm_unit("spm_unit_geographic_adjustment", period)

    class spm_unit_spm_threshold_housing_portion(Variable):
        value_type = float
        entity = SPMUnit
        definition_period = YEAR
        label = "Housing portion from the selected SPM release"
        unit = "currency-USD"

        def formula(spm_unit, period, parameters):
            shares = entry(period, parameters)["housing_shares"]
            housing_share = np.array(
                [shares[key] for key in tenure_keys(spm_unit, period)]
            )
            geoadj = spm_unit("spm_unit_geographic_adjustment", period)
            return spm_unit("spm_unit_unadjusted_spm_threshold", period) * (
                geoadj + housing_share - 1
            )

    variables = (
        spm_unit_reference_spm_threshold,
        spm_unit_unadjusted_spm_threshold,
        spm_unit_geographic_adjustment,
        spm_unit_spm_threshold,
        spm_unit_spm_threshold_housing_portion,
    )

    class release_reform(Reform):
        def apply(self):
            for variable in variables:
                self.update_variable(variable)

    release_reform.__name__ = f"SPMRelease_{bound.release.content_sha256}"
    release_reform.spm_release_provider = bound
    return release_reform
