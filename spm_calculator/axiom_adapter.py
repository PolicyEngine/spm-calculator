"""Optional, partial SPM bridge to the actual Axiom core Rust runtime.

SPM owns release selection, unit classification, equivalence and geography
inputs. Axiom executes the released threshold arithmetic and resource
comparison. This module contains no replacement policy evaluator.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from spm_calculator.release import SPMRelease, SPMUnit, equivalence_factor

MODULE_ID = "us:policies/policyengine/spm-threshold-application"
THRESHOLD_ID = f"{MODULE_ID}#adjusted_threshold"
POVERTY_ID = f"{MODULE_ID}#is_in_poverty"
TENURES = ("owner_with_mortgage", "owner_without_mortgage", "renter")
SOURCE_HEADER = "# SPM release source identity: "


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
    """Serialize our limited source tree, preserving integer table keys.

    The native YAML loader rejects JSON's quoted numeric table keys. All
    strings are JSON-quoted (valid YAML scalars); no YAML parser or evaluator
    is introduced into this optional transport.
    """
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


def export_build_spec(
    release: SPMRelease,
    *,
    years: Optional[Iterable[int]] = None,
    allow_estimated: bool = False,
    as_of=None,
) -> dict:
    """Portable RuleSpec source closure; requires no installed Axiom binary.

    By default export published entries only. Explicit estimated years require
    ``allow_estimated=True``. Each valid interval is one inclusive calendar
    year; there is no implicit extrapolation or knowledge-date selection.
    """
    if years is None:
        selected = tuple(
            year
            for year in release.years
            if allow_estimated
            or release.entry(year, allow_estimated=True)["status"]
            == "published"
        )
    else:
        selected = tuple(sorted(set(years)))
    if not selected:
        raise ValueError("At least one released year is required")
    entries = {
        year: release.entry(year, allow_estimated=allow_estimated, as_of=as_of)
        for year in selected
    }
    provenance = {
        "release_id": release.release_id,
        "release_sha256": release.content_sha256,
        "scope": "partial statistical bridge; external equivalence and geography",
        "sources": release.to_dict()["sources"],
        "years": {
            str(year): {
                key: entry[key]
                for key in ("status", "methodology_id", "available_on")
            }
            for year, entry in entries.items()
        },
    }

    def versions(formula):
        return [
            {
                "effective_from": f"{year}-01-01",
                "effective_to": f"{year}-12-31",
                "formula": str(formula(year)),
            }
            for year in selected
        ]

    rules = [
        {
            "name": "national_threshold",
            "kind": "parameter",
            "dtype": "Money",
            "unit": "USD",
            "indexed_by": "housing_tenure",
            "source": _json(provenance),
            "source_url": "https://www.bls.gov/pir/spmhome.htm",
            "versions": [
                {
                    "effective_from": f"{year}-01-01",
                    "effective_to": f"{year}-12-31",
                    "values": {
                        index: entries[year]["thresholds"][tenure]
                        for index, tenure in enumerate(TENURES)
                    },
                }
                for year in selected
            ],
        }
    ]
    for name, dtype, formula in (
        ("reference_threshold", "Money", "national_threshold[housing_tenure]"),
        (
            "adjusted_threshold",
            "Money",
            "reference_threshold * equivalence_factor * geographic_factor",
        ),
        ("is_in_poverty", "Judgment", "resources < adjusted_threshold"),
    ):
        rule = {
            "name": name,
            "kind": "derived",
            "entity": "SpmUnit",
            "dtype": dtype,
            "period": "Year",
            "source": _json(provenance),
            "source_url": "https://www.bls.gov/pir/spmhome.htm",
            "versions": versions(lambda year, text=formula: text),
        }
        if dtype == "Money":
            rule["unit"] = "USD"
        rules.append(rule)
    # Retaining source strings binds provenance even though metadata is inert.
    identity = {"release_sha256": release.content_sha256, "years": selected}
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


def make_request(
    release: SPMRelease,
    units: Iterable[SPMUnit],
    *,
    allow_estimated: bool = False,
    as_of=None,
) -> tuple[dict, list[dict]]:
    """Supply declared external facts; all threshold arithmetic stays native.

    Resources are already measured annual SPM resources, not Axiom-calculated
    taxes or benefits. Geography is a whole-threshold multiplier, not a rent
    index. One query always covers exactly January 1 through December 31.
    """
    inputs, queries, provenance, seen = [], [], [], set()
    for unit in units:
        identity = (unit.unit_id, unit.year)
        if identity in seen:
            raise ValueError("Duplicate SPM unit/year in one Axiom request")
        seen.add(identity)
        entry = release.entry(
            unit.year, allow_estimated=allow_estimated, as_of=as_of
        )
        factor = equivalence_factor(unit.num_adults, unit.num_children)
        if unit.geographic_adjustment is not None:
            geo = {
                "factor": unit.geographic_adjustment,
                "kind": "explicit_whole_threshold_factor",
                "source": "caller",
            }
        else:
            geo = release.geography_factor(
                unit.year,
                unit.tenure,
                kind=unit.geography_kind,
                geoid=unit.geography_id,
                missing="error",
                allow_estimated=allow_estimated,
            )
        if geo["factor"] + entry["housing_shares"][unit.tenure] < 1:
            raise ValueError(
                "Geographic factor implies negative housing portion"
            )
        interval = {
            "start": f"{unit.year}-01-01",
            "end": f"{unit.year}-12-31",
        }
        facts = {
            "housing_tenure": {
                "kind": "integer",
                "value": TENURES.index(unit.tenure),
            },
            "equivalence_factor": {"kind": "decimal", "value": str(factor)},
            "geographic_factor": {
                "kind": "decimal",
                "value": str(geo["factor"]),
            },
        }
        outputs = [THRESHOLD_ID]
        if unit.resources is not None:
            facts["resources"] = {
                "kind": "decimal",
                "value": str(unit.resources),
            }
            outputs.append(POVERTY_ID)
        for name, value in facts.items():
            inputs.append(
                {
                    "name": f"{MODULE_ID}#input.{name}",
                    "entity": "SpmUnit",
                    "entity_id": unit.unit_id,
                    "interval": interval,
                    "value": value,
                }
            )
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
        provenance.append(
            {
                "unit_id": unit.unit_id,
                "year": unit.year,
                "release_id": release.release_id,
                "release_sha256": release.content_sha256,
                "status": entry["status"],
                "methodology_id": entry["methodology_id"],
                "available_on": entry["available_on"],
                "external_equivalence_factor": factor,
                "tenure": unit.tenure,
                "equivalence_provider": "spm_calculator.release.equivalence_factor",
                "external_geography": geo,
                "resources_provider": "caller; annual SPM resources",
                "counts": {
                    "adults": unit.num_adults,
                    "children": unit.num_children,
                    "classification": "caller-supplied SPM membership/classification",
                },
            }
        )
    if not queries:
        raise ValueError("At least one SPM unit is required")
    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }, provenance


class AxiomSPMAdapter:
    """Thin subprocess transport for a caller-selected real core executable.

    The runtime never downloads or selects newer sources. Export build specs
    for portability; development bundles require the exact original binary.
    """

    def __init__(self, release: SPMRelease, *, binary=None, timeout=60):
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
        self.release = release
        self.binary = path
        self.timeout = timeout

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

    def build_bundle(
        self, path, *, years=None, allow_estimated=False, as_of=None
    ):
        """Build without overwriting; retain returned bundle_sha256 externally."""
        spec = export_build_spec(
            self.release,
            years=years,
            allow_estimated=allow_estimated,
            as_of=as_of,
        )
        with tempfile.TemporaryDirectory(prefix="spm-axiom-source-") as temp:
            source = Path(temp) / "build-spec.json"
            source.write_text(_json(spec), encoding="utf-8")
            return self._run(
                "build", "--spec", source, "--out", Path(path).resolve()
            )

    def execute_bundle(
        self,
        path,
        expected_sha256,
        units,
        *,
        allow_estimated=False,
        as_of=None,
    ):
        """Verify supplied identity and release association, then execute.

        Returns the entire native receipt plus separate SPM input provenance.
        An expected digest is mandatory and is never read from the bundle.
        """
        bundle_path = Path(path).resolve()
        self._run(
            "verify", "--bundle", bundle_path, "--expect", expected_sha256
        )
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        try:
            header = bundle["modules"][MODULE_ID].splitlines()[0]
            if not header.startswith(SOURCE_HEADER):
                raise AxiomRuntimeError(
                    "Bundle has no SPM release source identity"
                )
            years = json.loads(header[len(SOURCE_HEADER) :])["years"]
            expected = export_build_spec(
                self.release,
                years=years,
                allow_estimated=allow_estimated,
                as_of=as_of,
            )
        except (
            KeyError,
            IndexError,
            TypeError,
            json.JSONDecodeError,
        ) as error:
            raise AxiomRuntimeError(
                "Bundle does not contain SPM release source"
            ) from error
        if (
            bundle["modules"] != expected["modules"]
            or bundle["manifest"]["root"] != MODULE_ID
        ):
            raise AxiomRuntimeError(
                "Bundle source does not match the selected SPM release"
            )
        request, provenance = make_request(
            self.release, units, allow_estimated=allow_estimated, as_of=as_of
        )
        requested_years = {
            int(q["period"]["start"][:4]) for q in request["queries"]
        }
        if not requested_years <= set(years):
            raise ValueError(
                "Requested year is absent from the compiled SPM bundle"
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
            "spm_inputs": provenance,
            "request": request,
        }

    def calculate(self, units, *, allow_estimated=False, as_of=None):
        """Build and run locally; no bundle is advertised as portable."""
        units = tuple(units)
        with tempfile.TemporaryDirectory(prefix="spm-axiom-run-") as temp:
            path = Path(temp) / "spm.bundle.json"
            identity = self.build_bundle(
                path,
                years={unit.year for unit in units},
                allow_estimated=allow_estimated,
                as_of=as_of,
            )
            result = self.execute_bundle(
                path,
                identity["bundle_sha256"],
                units,
                allow_estimated=allow_estimated,
                as_of=as_of,
            )
            result["build"] = identity
            result["binary_sha256"] = hashlib.sha256(
                self.binary.read_bytes()
            ).hexdigest()
            return result
