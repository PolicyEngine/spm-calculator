"""Partial-bridge acceptance against the real Axiom core binary.

Set AXIOM_CORE_BIN explicitly for release acceptance. Missing runtime skips
only native tests; an explicitly configured invalid runtime fails them.
"""

import json
import os
from dataclasses import replace
from decimal import Decimal

import pytest

from spm_calculator.axiom_adapter import (
    MODULE_ID,
    POVERTY_ID,
    SOURCE_HEADER,
    THRESHOLD_ID,
    AxiomRuntimeError,
    AxiomSPMAdapter,
    export_build_spec,
    make_request,
)
from spm_calculator.release import (
    SPMRelease,
    SPMUnit,
    load_release,
    seal_release,
)


@pytest.fixture
def release():
    return load_release()


@pytest.fixture
def adapter(release):
    binary = os.environ.get("AXIOM_CORE_BIN")
    if not binary:
        pytest.skip("Set AXIOM_CORE_BIN to run actual Axiom acceptance")
    return AxiomSPMAdapter(release, binary=binary)


def test_portable_export_pins_release_and_source_versions(release):
    spec = export_build_spec(release, years=[2024, 2025])
    assert spec["root"] == MODULE_ID
    assert spec["format"] == "axiom/build-spec/v0"
    source = spec["modules"][MODULE_ID]
    identity = json.loads(source.splitlines()[0][len(SOURCE_HEADER) :])
    assert '"format": "rulespec/v1"' in source
    assert "statutes" not in MODULE_ID
    assert identity["release_sha256"] == release.content_sha256
    assert identity["years"] == [2024, 2025]
    assert '"effective_to": "2025-12-31"' in source
    assert (
        str(release.entry(2025)["thresholds"]["owner_with_mortgage"]) in source
    )


def test_exact_calendar_input_contract_and_no_implicit_resources(release):
    unit = SPMUnit("synthetic:1", 2, 2, "renter", 2025)
    request, provenance = make_request(release, [unit])
    assert request["queries"][0]["period"] == {
        "period_kind": "custom",
        "name": "spm-calendar-year",
        "start": "2025-01-01",
        "end": "2025-12-31",
    }
    assert request["queries"][0]["outputs"] == [THRESHOLD_ID]
    assert "assessment_date" not in json.dumps(request)
    assert provenance[0]["external_equivalence_factor"] == 1
    with pytest.raises(ValueError, match="Duplicate"):
        make_request(release, [unit, unit])


def test_requested_missing_runtime_has_no_evaluator_fallback(
    release, tmp_path
):
    with pytest.raises(AxiomRuntimeError, match="not executable"):
        AxiomSPMAdapter(release, binary=tmp_path / "absent-runtime")


def test_unsupported_year_cannot_be_exported(release):
    with pytest.raises(ValueError):
        export_build_spec(release, years=[1900])


@pytest.mark.parametrize("year", [2024, 2025])
def test_actual_native_thresholds_match_standalone_across_tenures(
    adapter, release, year
):
    units = [
        SPMUnit(
            unit_id=f"synthetic:{tenure}",
            num_adults=adults,
            num_children=children,
            tenure=tenure,
            year=year,
            geographic_adjustment=geography,
        )
        for tenure, adults, children, geography in (
            ("owner_with_mortgage", 2, 2, 1.1),
            ("owner_without_mortgage", 1, 0, 0.9),
            ("renter", 1, 2, 1.0),
        )
    ]
    result = adapter.calculate(units)
    assert result["receipt"]["assurance"] == "development_unsigned"
    assert (
        result["build"]["engine"]["revision"]
        == "d142c645917817cf590e036fb99f99b2d4780e1a"
    )
    for unit, native in zip(units, result["receipt"]["result"]["results"]):
        value = native["outputs"][THRESHOLD_ID]
        assert value["kind"] == "scalar"
        assert float(value["value"]["value"]) == pytest.approx(
            release.calculate_unit(unit)["threshold"], abs=1e-8, rel=1e-12
        )
        assert native["trace"]


def test_actual_native_strict_poverty_at_exact_released_threshold(
    adapter, release
):
    threshold = release.entry(2025)["thresholds"]["renter"]
    equal = SPMUnit(
        "synthetic:equal", 2, 2, "renter", 2025, resources=threshold
    )
    below = replace(
        equal, unit_id="synthetic:below", resources=threshold - 0.01
    )
    above = replace(
        equal, unit_id="synthetic:above", resources=threshold + 0.01
    )
    output = adapter.calculate([below, equal, above])
    native = output["receipt"]["result"]["results"]
    assert [row["outputs"][POVERTY_ID]["outcome"] for row in native] == [
        "holds",
        "not_holds",
        "not_holds",
    ]
    assert Decimal(
        native[1]["outputs"][THRESHOLD_ID]["value"]["value"]
    ) == Decimal(str(threshold))


def test_actual_runtime_rejects_wrong_expected_digest_and_source_tampering(
    adapter, tmp_path
):
    path = tmp_path / "spm.bundle.json"
    identity = adapter.build_bundle(path, years=[2025])
    original = path.read_bytes()
    unit = SPMUnit("synthetic:1", 2, 2, "renter", 2025)
    with pytest.raises(AxiomRuntimeError):
        adapter.execute_bundle(path, "0" * 64, [unit])
    assert path.read_bytes() == original
    corrupted = json.loads(original)
    corrupted["modules"][MODULE_ID] += " "
    path.write_text(json.dumps(corrupted))
    with pytest.raises(AxiomRuntimeError):
        adapter.execute_bundle(path, identity["bundle_sha256"], [unit])


def test_actual_runtime_rejects_uncompiled_year_and_preserves_bundle(
    adapter, tmp_path
):
    path = tmp_path / "spm.bundle.json"
    identity = adapter.build_bundle(path, years=[2025])
    original = path.read_bytes()
    with pytest.raises(ValueError, match="absent from the compiled"):
        adapter.execute_bundle(
            path,
            identity["bundle_sha256"],
            [SPMUnit("synthetic:1", 2, 2, "renter", 2024)],
        )
    with pytest.raises(AxiomRuntimeError):
        adapter.build_bundle(path, years=[2025])
    assert path.read_bytes() == original


def test_native_export_rejects_unknown_tenure_instead_of_renter_fallback(
    adapter, release, tmp_path
):
    path = tmp_path / "spm.bundle.json"
    identity = adapter.build_bundle(path, years=[2025])
    request, _ = make_request(
        release, [SPMUnit("synthetic:1", 2, 2, "renter", 2025)]
    )
    request["dataset"]["inputs"][0]["value"]["value"] = 99
    with pytest.raises(AxiomRuntimeError):
        adapter._run(
            "run",
            "--bundle",
            path,
            "--expect",
            identity["bundle_sha256"],
            request=request,
        )


def test_release_association_cannot_be_relabelled(adapter, release, tmp_path):
    path = tmp_path / "spm.bundle.json"
    identity = adapter.build_bundle(path, years=[2025])
    synthetic = release.to_dict()
    synthetic["release_id"] = "synthetic-different-release"
    other = AxiomSPMAdapter(
        SPMRelease.from_dict(seal_release(synthetic)), binary=adapter.binary
    )
    with pytest.raises(AxiomRuntimeError, match="selected SPM release"):
        other.execute_bundle(
            path,
            identity["bundle_sha256"],
            [SPMUnit("synthetic:1", 2, 2, "renter", 2025)],
        )


def test_estimated_release_entry_requires_explicit_opt_in(adapter, release):
    synthetic = release.to_dict()
    synthetic["release_id"] = "synthetic-status-contract-fixture"
    synthetic["years"]["2025"]["status"] = "forecast"
    other_release = SPMRelease.from_dict(seal_release(synthetic))
    other = AxiomSPMAdapter(other_release, binary=adapter.binary)
    unit = SPMUnit("synthetic:estimate", 2, 2, "renter", 2025)
    with pytest.raises(ValueError):
        other.calculate([unit])
    result = other.calculate([unit], allow_estimated=True)
    assert result["spm_inputs"][0]["status"] == "forecast"
    with pytest.raises(ValueError):
        other.calculate([unit], allow_estimated=True, as_of="1900-01-01")
