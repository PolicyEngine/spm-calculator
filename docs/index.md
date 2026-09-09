# SPM calculator

Use the local 1.0.0 candidate to calculate Supplemental Poverty Measure
thresholds from published 2025 national values and tenure housing shares,
or conditional CE/ACS rolling forecasts through 2035. Standalone calculations
read bundled, verified inputs offline. This documentation does not announce
package, website, PolicyEngine wrapper or API publication.

Start with the [quickstart](quickstart.md) for Python and CLI examples. The
[API reference](api.md) describes `SPMForecast`, `SPMUnit`, year-specific area
assignment and source metadata. The default artifact covers 2022–2035;
unknown years and locations fail instead of triggering a runtime projection.

A county identifies an assignment to an SPM estimation area for the selected
year. National is an explicit choice. Local amounts can use modeled rent
indices even when national thresholds are published; inspect each component's
status and the area's diagnostics.

Read [validation](validation.md) alongside [rolling forecasts](rolling-forecasts.md)
for the source checks, conditional assumptions and unresolved uncertainty.
[Historical correction and experiment records](bls-2026-correction.md) remain
separate from current runtime examples.

```{tableofcontents}
```
