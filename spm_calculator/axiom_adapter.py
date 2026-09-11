"""Canonical Microcosm Frame → actual Axiom core transport.

Core executes person classification, related unit counts, dated parameter
lookups and threshold/housing/poverty arithmetic. The canonical calculator
exports the bounded equivalence table because core has no fractional power.
This is not the dense Microcosm AxiomEngine or a tax/benefit/resource model.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
from decimal import Decimal
from numbers import Integral
from pathlib import Path
from typing import Iterable, Optional

from spm_calculator.errors import SPMInputError
from spm_calculator.microcosm_adapter import (
    _attach_results,
    prepare_frame_inputs,
)
from spm_calculator.release import canonical_bytes, equivalence_factor
from spm_calculator.rolling_forecast import METHOD, SPMForecast

MODULE_ID = "us:policies/policyengine/spm-threshold-application"
THRESHOLD_ID = f"{MODULE_ID}#adjusted_threshold"
HOUSING_ID = f"{MODULE_ID}#housing_portion"
POVERTY_ID = f"{MODULE_ID}#is_in_poverty"
TENURES = ("owner_with_mortgage", "owner_without_mortgage", "renter")
SOURCE_HEADER = "# SPM forecast source identity: "
DEFAULT_MAX_ADULTS = 10
DEFAULT_MAX_CHILDREN = 10
NATIVE_FIELDS = {
    "num_adults": "num_adults",
    "num_children": "num_children",
    "reference_threshold": "reference_threshold",
    "housing_share": "housing_share",
    "rent_index": "rent_index",
    "equivalence_factor": "equivalence_factor",
    "geographic_factor": "geographic_factor",
    "unadjusted_threshold": "unadjusted_threshold",
    "threshold": "adjusted_threshold",
    "housing_portion": "housing_portion",
}


class AxiomRuntimeError(RuntimeError):
    """An unavailable runtime or its unmodified structured failure."""

    def __init__(self, message, *, response=None, returncode=None):
        super().__init__(message)
        self.response = response
        self.returncode = returncode


def _json(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False
    )


def _yaml_lines(value, indent=0):
    """Serialize RuleSpec, preserving the native loader's integer table keys."""
    prefix = " " * indent
    if isinstance(value, dict) and value:
        for key, child in value.items():
            token = str(key) if isinstance(key, int) else _json(key)
            if isinstance(child, (dict, list)) and child:
                yield f"{prefix}{token}:"
                yield from _yaml_lines(child, indent + 2)
            else:
                yield f"{prefix}{token}: {_json(child)}"
    elif isinstance(value, list) and value:
        for child in value:
            yield f"{prefix}-"
            yield from _yaml_lines(child, indent + 2)
    else:
        yield prefix + _json(value)


def _domain(max_adults, max_children):
    for value, name, minimum in (
        (max_adults, "max_adults", 1),
        (max_children, "max_children", 0),
    ):
        if type(value) is not int or value < minimum:
            raise SPMInputError(
                "SPM_COMPOSITION_UNSUPPORTED",
                f"{name} must be an integer >= {minimum}",
            )
    return {
        "min_adults": 1,
        "max_adults": max_adults,
        "min_children": 0,
        "max_children": max_children,
    }


def _entry(forecast, year, scenario, as_of):
    # Use the same stable adapter errors as Frame preparation.
    if (
        isinstance(year, bool)
        or not isinstance(year, Integral)
        or year not in forecast.years
    ):
        raise SPMInputError(
            "SPM_YEAR_UNAVAILABLE", f"Forecast has no entry for {year!r}"
        )
    try:
        return forecast.entry(int(year), scenario=scenario, as_of=as_of)
    except ValueError as error:
        if str(error).startswith("Unknown forecast scenario"):
            raise SPMInputError(
                "SPM_SCENARIO_UNAVAILABLE", str(error)
            ) from error
        if str(error).startswith("Forecast has no entry"):
            raise SPMInputError("SPM_YEAR_UNAVAILABLE", str(error)) from error
        raise


def _area_indices(forecast, year, scenario, as_of):
    # Zero is reserved for explicit national; assignments are local to each year.
    return {
        area_id: index
        for index, area_id in enumerate(
            sorted(
                forecast.areas_for_year(year, scenario=scenario, as_of=as_of)
            ),
            1,
        )
    }


def export_build_spec(
    forecast: SPMForecast,
    *,
    years: Optional[Iterable[int]] = None,
    scenario=None,
    max_adults=DEFAULT_MAX_ADULTS,
    max_children=DEFAULT_MAX_CHILDREN,
    as_of=None,
) -> dict:
    """Export source-bound dated rules, with an explicit finite scale domain.

    No default lookup values are exported. An out-of-domain composition maps
    to the absent key -1 inside core, including child-count carry collisions.
    Each bundle selects one scenario and inclusive calendar-year versions.
    """
    if not isinstance(forecast, SPMForecast):
        raise TypeError("Expected a verified SPMForecast")
    domain = _domain(max_adults, max_children)
    requested = tuple(forecast.years if years is None else years)
    if not requested:
        raise SPMInputError(
            "SPM_YEAR_UNAVAILABLE", "At least one forecast year is required"
        )
    scenario = forecast.default_scenario if scenario is None else scenario
    entries = {}
    for year in requested:
        entry = _entry(forecast, year, scenario, as_of)
        entries[int(year)] = entry
    selected = tuple(sorted(entries))
    area_indices = {
        year: _area_indices(forecast, year, scenario, as_of)
        for year in selected
    }
    scale_table = {
        adults * (max_children + 1) + children: equivalence_factor(
            adults, children
        )
        for adults in range(1, max_adults + 1)
        for children in range(max_children + 1)
    }
    document = forecast.to_dict()
    identity = {
        "forecast_id": forecast.forecast_id,
        "forecast_sha256": forecast.content_sha256,
        "schema_version": document["schema_version"],
        "scenario": scenario,
        "years": selected,
        "composition_domain": domain,
        "equivalence_provider": "spm_calculator.release.equivalence_factor",
        "equivalence_table_sha256": hashlib.sha256(
            canonical_bytes(scale_table)
        ).hexdigest(),
        "information_date": document["information_date"],
        "methodology_id": METHOD,
        "component_sha256": document["component_sha256"],
        "sources": document["sources"],
        "area_index_encoding": "0=national; 1..N sorted areas_for_year(selected scenario/year)",
        "scope": "Frame to core; bounded canonical scale export; caller annual resources",
    }

    def versions(key, values):
        return [
            {
                "effective_from": f"{year}-01-01",
                "effective_to": f"{year}-12-31",
                key: values(year),
            }
            for year in selected
        ]

    rules = [
        {
            "name": "member_of_spm_unit",
            "kind": "data_relation",
            "data_relation": {"arity": 2, "arguments": ["Person", "SpmUnit"]},
        }
    ]
    for name, index, dtype, values in (
        (
            "national_threshold_table",
            "housing_tenure",
            "Money",
            lambda year: {
                i: entries[year]["thresholds"][t]
                for i, t in enumerate(TENURES)
            },
        ),
        (
            "housing_share_table",
            "housing_tenure",
            "Decimal",
            lambda year: {
                i: entries[year]["housing_shares"][t]
                for i, t in enumerate(TENURES)
            },
        ),
        (
            "rent_index_table",
            "area_index",
            "Decimal",
            lambda year: {
                0: 1.0,
                **{
                    i: entries[year]["rent_indices"][area]
                    for area, i in area_indices[year].items()
                },
            },
        ),
        (
            "equivalence_table",
            "composition_key",
            "Decimal",
            lambda year: scale_table,
        ),
    ):
        rule = {
            "name": name,
            "kind": "parameter",
            "dtype": dtype,
            "indexed_by": index,
            "versions": versions("values", values),
        }
        if dtype == "Money":
            rule["unit"] = "USD"
        rules.append(rule)
    for name, entity, dtype, formula in (
        (
            "is_measurement_adult",
            "Person",
            "Judgment",
            "age >= 18 or (age >= 15 and independent_minor_role)",
        ),
        (
            "num_adults",
            "SpmUnit",
            "Integer",
            "count_where(member_of_spm_unit, is_measurement_adult)",
        ),
        (
            "num_children",
            "SpmUnit",
            "Integer",
            "len(member_of_spm_unit) - num_adults",
        ),
        (
            "composition_key",
            "SpmUnit",
            "Integer",
            f"if num_adults >= 1 and num_adults <= {max_adults} and num_children >= 0 and num_children <= {max_children}: num_adults * {max_children + 1} + num_children else: -1",
        ),
        (
            "reference_threshold",
            "SpmUnit",
            "Money",
            "national_threshold_table[housing_tenure]",
        ),
        (
            "housing_share",
            "SpmUnit",
            "Decimal",
            "housing_share_table[housing_tenure]",
        ),
        ("rent_index", "SpmUnit", "Decimal", "rent_index_table[area_index]"),
        (
            "equivalence_factor",
            "SpmUnit",
            "Decimal",
            "equivalence_table[composition_key]",
        ),
        (
            "geographic_factor",
            "SpmUnit",
            "Decimal",
            "1 + housing_share * (rent_index - 1)",
        ),
        (
            "unadjusted_threshold",
            "SpmUnit",
            "Money",
            "reference_threshold * equivalence_factor",
        ),
        (
            "adjusted_threshold",
            "SpmUnit",
            "Money",
            "unadjusted_threshold * geographic_factor",
        ),
        (
            "housing_portion",
            "SpmUnit",
            "Money",
            "unadjusted_threshold * (geographic_factor + housing_share - 1)",
        ),
        (
            "is_in_poverty",
            "SpmUnit",
            "Judgment",
            "resources < adjusted_threshold",
        ),
    ):
        rule = {
            "name": name,
            "kind": "derived",
            "entity": entity,
            "dtype": dtype,
            "period": "Year",
            "versions": versions("formula", lambda year, text=formula: text),
        }
        if dtype == "Money":
            rule["unit"] = "USD"
        rules.append(rule)
    source = SOURCE_HEADER + _json(identity) + "\n"
    source += (
        "\n".join(_yaml_lines({"format": "rulespec/v1", "rules": rules}))
        + "\n"
    )
    return {
        "format": "axiom/build-spec/v0",
        "root": MODULE_ID,
        "modules": {MODULE_ID: source},
    }


def _make_request(forecast, prepared, *, max_adults, max_children, as_of=None):
    _domain(max_adults, max_children)
    year, scenario = (
        prepared.provenance["year"],
        prepared.provenance["scenario"],
    )
    area_indices = _area_indices(forecast, year, scenario, as_of)
    interval = {"start": f"{year}-01-01", "end": f"{year}-12-31"}
    inputs, relations, queries = [], [], []

    def add(entity, entity_id, name, kind, value):
        inputs.append(
            {
                "name": f"{MODULE_ID}#input.{name}",
                "entity": entity,
                "entity_id": entity_id,
                "interval": interval,
                "value": {"kind": kind, "value": value},
            }
        )

    for person in prepared.persons:
        add("Person", person["person_id"], "age", "integer", person["age"])
        add(
            "Person",
            person["person_id"],
            "independent_minor_role",
            "bool",
            person["independent_minor_role"],
        )
        relations.append(
            {
                "name": f"{MODULE_ID}#relation.member_of_spm_unit",
                "tuple": [person["person_id"], person["unit_id"]],
                "interval": interval,
            }
        )
    for unit in prepared.units:
        if not (
            1 <= unit.num_adults <= max_adults
            and 0 <= unit.num_children <= max_children
        ):
            raise SPMInputError(
                "SPM_COMPOSITION_UNSUPPORTED",
                f"Unit {unit.unit_id!r} exceeds declared Axiom composition domain: adults 1..{max_adults}, children 0..{max_children}",
            )
        add(
            "SpmUnit",
            unit.unit_id,
            "housing_tenure",
            "integer",
            TENURES.index(unit.tenure),
        )
        add(
            "SpmUnit",
            unit.unit_id,
            "area_index",
            "integer",
            0
            if unit.geography_kind == "national"
            else area_indices[unit.geography_id],
        )
        outputs = [f"{MODULE_ID}#{name}" for name in NATIVE_FIELDS.values()]
        if unit.resources is not None:
            add(
                "SpmUnit",
                unit.unit_id,
                "resources",
                "decimal",
                format(Decimal(str(unit.resources)), "f"),
            )
            outputs.append(POVERTY_ID)
        queries.append(
            {
                "entity_id": unit.unit_id,
                "period": {
                    "period_kind": "custom",
                    "name": "spm-calendar-year",
                    **interval,
                },
                "outputs": outputs,
            }
        )
    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": relations},
        "queries": queries,
    }


def make_request(
    forecast: SPMForecast,
    frame,
    *,
    max_adults=DEFAULT_MAX_ADULTS,
    max_children=DEFAULT_MAX_CHILDREN,
    **kwargs,
):
    """Transport native membership and primitives, never final factors/counts.

    Resources, when present, are caller-measured annual SPM resources. The
    returned preparation record describes source roles, county assignment and
    typed weight resolution; weights never enter core policy calculations.
    """
    prepared = prepare_frame_inputs(frame, forecast, **kwargs)
    return _make_request(
        forecast,
        prepared,
        max_adults=max_adults,
        max_children=max_children,
        as_of=kwargs.get("as_of"),
    ), prepared


def _native_results(forecast, prepared, receipt, *, as_of=None):
    """Attach descriptive forecast metadata to values produced by core."""
    rows = receipt["result"]["results"]
    if len(rows) != len(prepared.units):
        raise AxiomRuntimeError(
            "Native results differ from requested unit count", response=receipt
        )
    scenario = prepared.provenance["scenario"]
    document = forecast.to_dict()
    entry = forecast.entry(
        prepared.provenance["year"], scenario=scenario, as_of=as_of
    )
    results = []
    for unit, assignment, row in zip(
        prepared.units, prepared.provenance["county_assignments"], rows
    ):
        if (
            row["entity_id"] != unit.unit_id
            or row["period"]["start"] != f"{unit.year}-01-01"
        ):
            raise AxiomRuntimeError(
                "Native result identity differs from requested unit/year",
                response=receipt,
            )
        values, native_decimal_values = {}, {}
        for field, rule in NATIVE_FIELDS.items():
            output = row["outputs"][f"{MODULE_ID}#{rule}"]
            if output["kind"] != "scalar":
                raise AxiomRuntimeError(
                    f"Native {field} has no scalar value", response=receipt
                )
            raw_value = output["value"]["value"]
            native_decimal_values[field] = str(raw_value)
            value = float(raw_value)
            if not math.isfinite(value):
                raise AxiomRuntimeError(
                    f"Native {field} is not finite", response=receipt
                )
            values[field] = value
        for field, expected in (
            ("num_adults", unit.num_adults),
            ("num_children", unit.num_children),
        ):
            if values[field] != expected:
                raise AxiomRuntimeError(
                    "Native classification disagrees with validated Frame membership",
                    response=receipt,
                )
            values[field] = int(values[field])
        poverty = None
        if unit.resources is not None:
            outcome = row["outputs"][POVERTY_ID]["outcome"]
            if outcome not in {"holds", "not_holds"}:
                raise AxiomRuntimeError(
                    "Native poverty judgment is undetermined", response=receipt
                )
            poverty = outcome == "holds"
        geography = forecast.geography_factor(
            unit.year,
            unit.tenure,
            kind=unit.geography_kind,
            geoid=unit.geography_id,
            scenario=scenario,
            as_of=as_of,
        )
        geography["factor"] = values["geographic_factor"]
        provenance = {
            "information_date": document["information_date"],
            "geography": geography,
            "ce_window": entry["ce_window"],
            "acs_window": entry["acs_window"],
            "uncertainty": "not estimated",
            "numeric_semantics": {
                "arithmetic": "Axiom core decimal",
                "public_amounts": "float conversions of native_decimal_values",
                "poverty_comparison": "resources < exact native threshold; no rounding",
                "canonical_float_boundary_parity": False,
            },
        }
        if assignment is not None:
            provenance["county_assignment"] = assignment
        results.append(
            {
                "unit_id": unit.unit_id,
                "year": unit.year,
                "tenure": unit.tenure,
                "forecast_id": forecast.forecast_id,
                "forecast_sha256": forecast.content_sha256,
                "base_release_sha256": document["base_release_sha256"],
                "scenario": scenario,
                "methodology_id": METHOD,
                "national_status": entry["national_status"],
                "geography_status": geography["status"],
                "bundled_geography_status": entry["geography_status"],
                "housing_share_status": entry["housing_share_status"],
                **values,
                "native_decimal_values": native_decimal_values,
                "resources": unit.resources,
                "is_in_poverty": poverty,
                "provenance": provenance,
            }
        )
    return results


class AxiomSPMAdapter:
    """Run an explicit real core binary; retain full native responses.

    Bundles are unsigned development artifacts bound to their source and
    executable bytes. They establish integrity, not authentication or legal
    validity. Dense Microcosm AxiomEngine parity is not claimed.
    """

    def __init__(
        self,
        forecast: SPMForecast,
        *,
        binary=None,
        timeout=60,
        max_adults=DEFAULT_MAX_ADULTS,
        max_children=DEFAULT_MAX_CHILDREN,
    ):
        if not isinstance(forecast, SPMForecast):
            raise TypeError("Expected a verified SPMForecast")
        _domain(max_adults, max_children)
        candidate = (
            binary
            or os.environ.get("AXIOM_CORE_BIN")
            or shutil.which("axiom-core")
        )
        if not candidate:
            raise AxiomRuntimeError(
                "Axiom core is required; set AXIOM_CORE_BIN or pass binary="
            )
        path = Path(candidate).expanduser().resolve()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise AxiomRuntimeError(
                f"Axiom core binary is not executable: {path}"
            )
        self.forecast, self.binary, self.timeout = forecast, path, timeout
        self.max_adults, self.max_children = max_adults, max_children

    def _run(self, *args, request=None):
        try:
            process = subprocess.run(
                [str(self.binary), *map(str, args)],
                input=None if request is None else _json(request),
                text=True,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise AxiomRuntimeError(str(error)) from error
        raw = process.stdout if process.returncode == 0 else process.stderr
        try:
            response = json.loads(raw)
        except json.JSONDecodeError as error:
            raise AxiomRuntimeError(
                "Axiom core returned invalid JSON",
                returncode=process.returncode,
            ) from error
        if process.returncode:
            raise AxiomRuntimeError(
                f"Axiom core failed: {response}",
                response=response,
                returncode=process.returncode,
            )
        return response

    def capabilities(self):
        """Return the full native capability response unchanged."""
        return self._run("capabilities")

    def build_bundle(self, path, *, years=None, scenario=None, as_of=None):
        """Build without overwriting; retain returned bundle_sha256 externally."""
        spec = export_build_spec(
            self.forecast,
            years=years,
            scenario=scenario,
            as_of=as_of,
            max_adults=self.max_adults,
            max_children=self.max_children,
        )
        with tempfile.TemporaryDirectory(prefix="spm-axiom-source-") as temp:
            source = Path(temp) / "build-spec.json"
            source.write_text(_json(spec), encoding="utf-8")
            return self._run(
                "build", "--spec", source, "--out", Path(path).resolve()
            )

    def _execute(self, path, expected_sha256, prepared, *, as_of=None):
        bundle_path = Path(path).resolve()
        self._run(
            "verify", "--bundle", bundle_path, "--expect", expected_sha256
        )
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        try:
            header = bundle["modules"][MODULE_ID].splitlines()[0]
            if not header.startswith(SOURCE_HEADER):
                raise AxiomRuntimeError(
                    "Bundle has no SPM forecast source identity"
                )
            identity = json.loads(header[len(SOURCE_HEADER) :])
            years = identity["years"]
            expected = export_build_spec(
                self.forecast,
                years=years,
                scenario=prepared.provenance["scenario"],
                max_adults=self.max_adults,
                max_children=self.max_children,
                as_of=as_of,
            )
        except (
            KeyError,
            IndexError,
            TypeError,
            json.JSONDecodeError,
        ) as error:
            raise AxiomRuntimeError(
                "Bundle does not contain SPM forecast source"
            ) from error
        if (
            bundle["modules"] != expected["modules"]
            or bundle["manifest"]["root"] != MODULE_ID
        ):
            raise AxiomRuntimeError(
                "Bundle source does not match the selected SPM forecast, scenario or composition domain"
            )
        if prepared.provenance["year"] not in years:
            raise SPMInputError(
                "SPM_YEAR_UNAVAILABLE",
                "Requested year is absent from the compiled SPM bundle",
            )
        request = _make_request(
            self.forecast,
            prepared,
            max_adults=self.max_adults,
            max_children=self.max_children,
            as_of=as_of,
        )
        receipt = self._run(
            "run",
            "--bundle",
            bundle_path,
            "--expect",
            expected_sha256,
            request=request,
        )
        return {
            "receipt": receipt,
            "request": request,
            "spm_inputs": prepared.provenance,
            "results": _native_results(
                self.forecast, prepared, receipt, as_of=as_of
            ),
        }

    def execute_bundle(self, path, expected_sha256, frame, **kwargs):
        """Verify retained identity/source association, then execute real core."""
        prepared = prepare_frame_inputs(frame, self.forecast, **kwargs)
        return self._execute(
            path, expected_sha256, prepared, as_of=kwargs.get("as_of")
        )

    def _calculate(self, prepared, *, as_of=None):
        # Validate bounds before spending time compiling the bundle.
        _make_request(
            self.forecast,
            prepared,
            max_adults=self.max_adults,
            max_children=self.max_children,
            as_of=as_of,
        )
        with tempfile.TemporaryDirectory(prefix="spm-axiom-run-") as temp:
            path = Path(temp) / "spm.bundle.json"
            identity = self.build_bundle(
                path,
                years=[prepared.provenance["year"]],
                scenario=prepared.provenance["scenario"],
                as_of=as_of,
            )
            result = self._execute(
                path, identity["bundle_sha256"], prepared, as_of=as_of
            )
            result["build"] = identity
            result["binary_sha256"] = hashlib.sha256(
                self.binary.read_bytes()
            ).hexdigest()
            return result

    def calculate(self, frame, **kwargs):
        """Build/run a Frame and return native evidence and descriptive results."""
        prepared = prepare_frame_inputs(frame, self.forecast, **kwargs)
        return self._calculate(prepared, as_of=kwargs.get("as_of"))

    def apply_to_frame(self, frame, **kwargs):
        """Return a new Frame with actual core amounts and all native weights."""
        prepared = prepare_frame_inputs(frame, self.forecast, **kwargs)
        execution = self._calculate(prepared, as_of=kwargs.get("as_of"))
        return _attach_results(
            frame,
            prepared,
            execution["results"],
            execution={
                "provider": "Axiom core",
                "scope": "Frame to core bridge; not dense AxiomEngine",
                "composition_domain": _domain(
                    self.max_adults, self.max_children
                ),
                **execution,
            },
        )
