"""Canonical forecast integration for PolicyEngine's SPM measurement formulas.

PolicyEngine owns resources and benefit rules. This adapter supplies only SPM
measurement inputs and final canonical amounts, with one storage cast. Importing
it does not import PolicyEngine or change process-wide model state.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from importlib import metadata
from typing import TYPE_CHECKING

from .errors import SPMInputError

if TYPE_CHECKING:
    from .rolling_forecast import SPMForecast


FORMULA_OWNED_INPUTS = frozenset(
    {
        "spm_unit_reference_spm_threshold",
        "spm_unit_unadjusted_spm_threshold",
        "spm_unit_spm_threshold",
        "spm_unit_spm_threshold_housing_portion",
        "spm_unit_geographic_adjustment",
        "spm_measurement_adults",
        "spm_measurement_children",
        "spm_unit_capped_housing_subsidy",
        "spm_unit_net_income",
        "spm_unit_benefits",
        "spm_unit_is_in_spm_poverty",
        "spm_unit_is_in_deep_spm_poverty",
        "poverty_line",
        "poverty_gap",
    }
)


def runtime_versions():
    """Return installed distributions without asserting data certification."""
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
    """Reject inputs that bypass SPM formulas without rewriting membership.

    Generic benefit-eligibility adult/child counts are outside this contract.
    Observed Census outputs can be retained under separate report-only names.
    """
    conflicts = []
    for entity, records in entity_records.items():
        keys = (
            set(records.columns)
            if hasattr(records, "columns")
            else {key for record in records for key in record}
        )
        conflicts.extend(
            f"{entity}.{name}" for name in sorted(keys & FORMULA_OWNED_INPUTS)
        )
    if conflicts:
        raise ValueError(
            "SPM formulas cannot run with computed outputs supplied as inputs: "
            + ", ".join(conflicts)
            + ". Retain observed Census values under separate report-only names."
        )


@dataclass(frozen=True)
class PolicyEngineSPMProvider:
    """One verified forecast/scenario with explicit location selection.

    The default resolves each unit's observed county through the artifact's
    year-specific area assignment. A household caller may explicitly select
    ``national`` or one ``metro`` area. Unknown years, counties and areas fail;
    there is no consumer extrapolation or location fallback policy.
    """

    forecast: SPMForecast
    scenario: str | None = None
    geography_kind: str = "county"
    geography_id: str | None = None
    county_vintage: str = "2020"
    as_of: str | None = None
    _amount_cache: dict = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _year_receipts: dict = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _geography_receipts: dict = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self):
        from .rolling_forecast import SPMForecast

        if not isinstance(self.forecast, SPMForecast):
            raise TypeError("forecast must be a verified SPMForecast")
        # SPMForecast is immutable and returns detached accessor results.
        scenario = (
            self.forecast.default_scenario
            if self.scenario is None
            else self.scenario
        )
        self.forecast.entry(
            self.forecast.years[0], scenario=scenario, as_of=self.as_of
        )
        object.__setattr__(self, "scenario", scenario)
        if self.geography_kind not in {"county", "national", "metro"}:
            raise ValueError(
                "geography_kind must be county, national or metro"
            )
        if self.geography_kind == "metro":
            if not isinstance(self.geography_id, str) or not self.geography_id:
                raise ValueError("Metro selection requires an area id")
        elif self.geography_id is not None:
            raise ValueError("Only a fixed metro selection takes geography_id")
        if not isinstance(self.county_vintage, str) or not self.county_vintage:
            raise ValueError("county_vintage must be explicit")

    def snapshot(self, *, copy_receipts=False):
        """Create private state; clones with retained holders keep their receipts."""
        snapshot = type(self)(
            **{
                name: getattr(self, name)
                for name in (
                    "forecast",
                    "scenario",
                    "geography_kind",
                    "geography_id",
                    "county_vintage",
                    "as_of",
                )
            }
        )
        if copy_receipts:
            snapshot._year_receipts.update(copy.deepcopy(self._year_receipts))
            snapshot._geography_receipts.update(
                copy.deepcopy(self._geography_receipts)
            )
        return snapshot

    def _validate_year(self, year):
        """Reject unsupported years only when a measurement is requested."""
        if (
            isinstance(year, bool)
            or not isinstance(year, int)
            or year not in self.forecast.years
        ):
            raise SPMInputError(
                "SPM_YEAR_UNAVAILABLE", f"Forecast has no entry for {year!r}"
            )

    def year_metadata(self, year):
        self._validate_year(year)
        if year not in self._year_receipts:
            self._year_receipts[year] = self.forecast.entry(
                year, scenario=self.scenario, as_of=self.as_of
            )
        return copy.deepcopy(self._year_receipts[year])

    def calculate_unit(
        self, *, year, adults, children, tenure, county_fips=None
    ):
        """Execute the canonical calculator; preserve resolved input provenance."""
        from .release import SPMUnit

        self._validate_year(year)
        assignment = None
        kind, identity = self.geography_kind, self.geography_id
        if kind == "county":
            if county_fips is None or county_fips == "":
                raise SPMInputError(
                    "SPM_GEOGRAPHY_REQUIRED",
                    "Choose an SPM area, provide county FIPS, or explicitly select national geography; state alone does not identify an SPM area",
                )
            try:
                assignment = self.forecast.resolve_county(
                    year,
                    county_fips,
                    county_vintage=self.county_vintage,
                    scenario=self.scenario,
                    as_of=self.as_of,
                )
            except ValueError as error:
                raise SPMInputError(
                    "SPM_GEOGRAPHY_UNAVAILABLE", str(error)
                ) from error
            kind, identity = assignment["kind"], assignment["area_id"]
        elif county_fips is not None:
            raise ValueError(
                "County input conflicts with explicit geography selection"
            )
        if kind == "metro" and identity not in self.forecast.areas_for_year(
            year, scenario=self.scenario, as_of=self.as_of
        ):
            raise SPMInputError(
                "SPM_GEOGRAPHY_UNAVAILABLE",
                f"SPM area {identity!r} is unavailable for {year}",
            )
        result = self.forecast.calculate_unit(
            SPMUnit(
                unit_id="policyengine",
                year=year,
                num_adults=adults,
                num_children=children,
                tenure=tenure,
                geography_kind=kind,
                geography_id=identity,
            ),
            scenario=self.scenario,
            as_of=self.as_of,
        )
        if year not in self._year_receipts:
            self._year_receipts[year] = self.forecast.entry(
                year, scenario=self.scenario, as_of=self.as_of
            )
        if assignment is not None:
            result["provenance"]["county_assignment"] = assignment
        self._geography_receipts[(year, tenure, county_fips, identity)] = {
            "year": year,
            "tenure": tenure,
            "geography": copy.deepcopy(result["provenance"]["geography"]),
            "county_assignment": copy.deepcopy(assignment),
        }
        return result

    def _amounts(self, year, adults, children, tenure, county):
        key = (year, adults, children, tenure, county)
        if key not in self._amount_cache:
            result = self.calculate_unit(
                year=year,
                adults=adults,
                children=children,
                tenure=tenure,
                county_fips=county,
            )
            self._amount_cache[key] = tuple(
                result[name]
                for name in (
                    "reference_threshold",
                    "unadjusted_threshold",
                    "geographic_factor",
                    "threshold",
                    "housing_portion",
                )
            )
        return self._amount_cache[key]

    def provenance(self):
        """Report calculation inputs; data certification belongs to the bundle."""
        return {
            "forecast_id": self.forecast.forecast_id,
            "forecast_sha256": self.forecast.content_sha256,
            "scenario": self.scenario,
            "geography_kind": self.geography_kind,
            "runtime_versions": runtime_versions(),
            "years": {
                str(year): copy.deepcopy(value)
                for year, value in sorted(self._year_receipts.items())
            },
            "geographies": copy.deepcopy(
                list(self._geography_receipts.values())
            ),
            "composition_method": "age >= 18 or age >= 15 with explicit SPM independence role; native SPM membership",
            "storage_method": "canonical final amount cast once to model dtype",
        }


def policyengine_amount(unit, period, field):
    """Return one raw canonical float64 amount for native country formulas."""
    import numpy as np

    fields = (
        "reference_threshold",
        "unadjusted_threshold",
        "geographic_factor",
        "threshold",
        "housing_portion",
    )
    if field not in fields:
        raise ValueError(f"Unknown SPM amount field: {field}")
    index = fields.index(field)
    bound = unit.simulation.tax_benefit_system.spm_forecast_provider
    adults = unit("spm_measurement_adults", period)
    children = unit("spm_measurement_children", period)
    if np.any(adults < 1):
        raise SPMInputError(
            "SPM_COMPOSITION_REQUIRED",
            "SPM unit has no classified adult: supply source-backed independence or household head/spouse structure",
        )
    tenures = unit("spm_unit_tenure_type", period).decode_to_str()
    counties = (
        unit.household("county_fips", period)
        if bound.geography_kind == "county"
        else [None] * len(adults)
    )
    rows = [
        bound._amounts(
            int(period.start.year),
            int(a),
            int(k),
            str(t).lower(),
            None
            if c is None
            else (c.decode() if isinstance(c, bytes) else str(c)),
        )
        for a, k, t, c in zip(adults, children, tenures, counties)
    ]
    return np.asarray([row[index] for row in rows], dtype=np.float64)


def build_policyengine_variables():
    """Create shared formula classes that resolve their simulation's provider.

    Formula closures never capture a provider or another simulation's cache.
    Country models register these variables before reading situation inputs.
    """
    from policyengine_core.periods import ETERNITY, YEAR
    from policyengine_core.variables import Variable
    from policyengine_us.entities import Person, SPMUnit

    class is_household_spouse(Variable):
        value_type = bool
        entity = Person
        definition_period = ETERNITY
        label = "Explicit household spouse role"

    class is_spm_independent_minor_role(Variable):
        value_type = bool
        entity = Person
        definition_period = ETERNITY
        label = "SPM independence role from source or household structure"

        def formula(person, period, parameters):
            return person("is_household_head", period) | person(
                "is_household_spouse", period
            )

    class spm_measurement_adults(Variable):
        value_type = int
        entity = SPMUnit
        definition_period = YEAR
        label = "Adults under SPM measurement classification"

        def formula(unit, period, parameters):
            age = unit.members("age", period)
            role = unit.members("is_spm_independent_minor_role", period)
            return unit.sum((age >= 18) | ((age >= 15) & role))

    class spm_measurement_children(Variable):
        value_type = int
        entity = SPMUnit
        definition_period = YEAR
        label = "Children under SPM measurement classification"

        def formula(unit, period, parameters):
            return unit.nb_persons() - unit("spm_measurement_adults", period)

    def amount_variable(name, index, label, currency=True):
        def formula(unit, period, parameters):
            # Return each canonical final amount directly, never multiply
            # independently rounded model intermediates.
            return policyengine_amount(
                unit,
                period,
                (
                    "reference_threshold",
                    "unadjusted_threshold",
                    "geographic_factor",
                    "threshold",
                    "housing_portion",
                )[index],
            )

        attributes = {
            "value_type": float,
            "entity": SPMUnit,
            "definition_period": YEAR,
            "label": label,
            "formula": formula,
            "__module__": __name__,
        }
        if currency:
            attributes["unit"] = "currency-USD"
        return type(name, (Variable,), attributes)

    return (
        is_household_spouse,
        is_spm_independent_minor_role,
        spm_measurement_adults,
        spm_measurement_children,
        amount_variable(
            "spm_unit_reference_spm_threshold",
            0,
            "Canonical SPM reference threshold",
        ),
        amount_variable(
            "spm_unit_unadjusted_spm_threshold",
            1,
            "Canonical SPM threshold before geography",
        ),
        amount_variable(
            "spm_unit_geographic_adjustment",
            2,
            "Canonical SPM geographic adjustment",
            False,
        ),
        amount_variable(
            "spm_unit_spm_threshold", 3, "Canonical SPM poverty threshold"
        ),
        amount_variable(
            "spm_unit_spm_threshold_housing_portion",
            4,
            "Canonical SPM housing portion",
        ),
    )


def build_policyengine_reform(provider):
    """Install the shared variables and a private provider on a model system."""
    from policyengine_core.reforms import Reform

    if not isinstance(provider, PolicyEngineSPMProvider):
        raise TypeError("provider must be a PolicyEngineSPMProvider")
    bound = provider.snapshot()
    variables = build_policyengine_variables()

    class forecast_reform(Reform):
        def apply(self):
            self.spm_forecast_provider = bound.snapshot()
            for variable in variables:
                self.update_variable(variable)

    forecast_reform.__name__ = f"SPMForecast_{bound.forecast.content_sha256}"
    forecast_reform.spm_forecast_provider = bound
    return forecast_reform
