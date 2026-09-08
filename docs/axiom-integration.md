# Axiom integration

The optional `spm_calculator.axiom_adapter` runs the actual Axiom core Rust
compiler and runtime. Axiom calculates the released national threshold times
the supplied equivalence and geographic factors, then compares supplied annual
SPM resources with that threshold. It returns the complete native receipt and
explanation trace, alongside SPM input provenance.

This is a partial bridge. SPM still selects the release and information date,
classifies unit membership, and supplies the equivalence factor and the
whole-threshold geographic multiplier. Resources are supplied by the caller.
The pinned engine has no fractional-power expression, so the bridge does not
claim that Axiom calculates the Betson equivalence scale, taxes, benefits or
SPM resource construction. Missing Axiom software raises an explicit error;
there is no substitute evaluator.

## Runtime and source

Acceptance uses [axiom-core at 8ac3a54](https://github.com/TheAxiomFoundation/axiom-core/tree/8ac3a54f60fa3737166ff0c986d9660f34a25435),
which pins the actual rules engine at
`d142c645917817cf590e036fb99f99b2d4780e1a`, engine version `0.2.2`, artifact
format `2`. Build core using its pinned Rust 1.94.1 toolchain:

```sh
cargo build --locked --workspace
target/debug/axiom-core capabilities
```

Pass the resulting binary explicitly or set `AXIOM_CORE_BIN`. Version strings
alone do not establish binary or artifact compatibility.

```python
from spm_calculator.release import SPMUnit, load_release
from spm_calculator.axiom_adapter import AxiomSPMAdapter

release = load_release(expected_sha256=independently_retained_release_digest)
adapter = AxiomSPMAdapter(release, binary="/path/to/axiom-core")
result = adapter.calculate([
    SPMUnit("example:1", 2, 2, "renter", 2025, resources=40_000),
])
receipt = result["receipt"]
```

The project-owned identifier is
`us:policies/policyengine/spm-threshold-application`. It is a statistical
methodology module, not a fabricated statute or an official BLS encoding.
Source strings retain the complete release hash, source identities and
availability metadata. The native loader treats that provenance as descriptive;
the SPM release reader enforces the information-date boundary.

National thresholds are indexed by tenure: `0` means owner with mortgage,
`1` owner without mortgage and `2` renter. An unknown index fails native
parameter lookup. The Python transport accepts the release's named tenures and
encodes this index. Native input/output identifiers are published in each
compiled artifact's `metadata.input_catalog` and output rules.

## Portable export and replay

`export_build_spec(release, years=[2024, 2025])` works without an Axiom
installation. It returns the explicit `axiom/build-spec/v0` source closure.
Estimated entries require `allow_estimated=True`; missing years never silently
extrapolate. Sources are actual RuleSpec YAML; the enclosing build spec is JSON.

`adapter.build_bundle(path, years=[2025])` returns the actual native build
identity and refuses to overwrite an existing bundle. Retain its
`bundle_sha256` independently. Then:

```python
result = adapter.execute_bundle(
    bundle_path, independently_retained_bundle_digest, units
)
```

Core verifies the expected digest, exact sources, rebuilt artifact and executing
binary identity. The adapter also verifies that the source matches its selected
SPM release. A development bundle is bound to the original executable bytes;
another platform or build must rebuild from the portable source closure. Core
calls this assurance `development_unsigned`. Digests establish integrity
against a caller's expectation, not authorship, legal validity or a signed
release. No core WASM facade or browser receipt parity is claimed here.

Every high-level request covers exactly January 1 through December 31,
inclusive. The native wire uses `period_kind: custom` with the name
`spm-calendar-year`; there is no native `year` variant. Core selects dated
versions at period start and does not prorate straddling periods. The adapter
does not create them. It never passes the unsupported `assessment_date` field.

Poverty uses strict `<`, without first rounding the threshold. Native judgment
outcomes are `holds`, `not_holds` and `undetermined`, not scalar booleans. When
resources are omitted, the adapter queries only the threshold. Missing
resources are never interpreted as zero.

## Verification

The following tests execute the actual runtime, including multiple years,
tenures, family compositions, geography factors, equality at the poverty line,
estimated-entry opt-in, wrong digests and tampered sources:

```sh
AXIOM_CORE_BIN=/path/to/axiom-core python -m pytest tests/test_axiom_adapter.py
python scripts/validate_axiom_integration.py \
  --binary /path/to/axiom-core --output-dir /tmp/spm-axiom-evidence
```

The evidence directory must not already exist. It contains a portable build
spec, separately retained expected identity, original synthetic request, full
native receipt, input provenance, and a validation report with exact release,
source-file and executable hashes. The request fixtures are public synthetic
units; user calculation receipts can contain private data and are not public
registry artifacts. Default tests skip native acceptance only when no binary
has been configured. A configured invalid binary fails.
