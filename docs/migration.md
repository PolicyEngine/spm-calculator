# Migrating to the canonical SPM calculator

This document accompanies the 1.0.0 release candidate. Publication and downstream
bundle promotion remain pending until their release gates pass.

## Public API replacement

Version 1.0.0 replaces the legacy calculation path with `SPMUnit`, `load_forecast`,
and the canonical PolicyEngine, Frame, and Axiom adapters. The old `calculator`,
`forecast`, `geoadj`, `nowcast`, and `projection` modules are removed. Their former
imports are not supported. Use the [quickstart](quickstart.md) and integration
guides to migrate; the old formulas are not retained as a parallel runtime.

## Existing PolicyEngine installations

Older `policyengine-us` releases import legacy modules and allow an unbounded
`spm-calculator>=0.2.0` dependency. Their metadata therefore permits 1.0.0 even
though their imports are incompatible. Publishing a major version does not make
pip infer an upper bound. This affects fresh installations and dependency
upgrades outside the protected PolicyEngine service images as well.

Keep the exact calculator constraint when reproducing an older bundle. For
example, in an isolated environment:

```sh
python -m pip install "policyengine[models]==5.2.0" "spm-calculator==0.3.1"
python -m pip check
```

The same calculator constraint is required for any older country or wrapper
release that uses those legacy imports. Retaining only a country-version pin
does not protect its unconstrained transitive calculator dependency. The
published 0.3.1 artifact remains available for historical environments; it is
not installed alongside 1.0.0 in the canonical runtime.

Canonical integration requires the coordinated country model and wrapper
release, the certified source-enriched population, and the calculator hash
declared by that bundle. Do not independently substitute 1.0.0 into an older
wrapper manifest. The release announcement will identify the verified published
country and wrapper versions once available; candidate versions are not proof
of publication.

## Release sequencing

Before publishing 1.0.0, verify that active old service image builders enforce
0.3.1 and deploy those changes. Publish and verify the source-enriched dataset
before releasing a country model whose default population requires its native
SPM role input. Qualify the final country and wrapper artifacts, their default
dataset and their exact calculator pins before promoting service routes.

The 1.0.0 release notes must carry the legacy-installation constraint above and
link the coordinated release versions. This is a declared breaking dependency
change for older unbounded installations, not a guarantee that every historical
PyPI requirement can resolve to the new runtime. Existing published metadata
and scientific artifacts remain immutable.
