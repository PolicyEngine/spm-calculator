# SPM releases and integration boundaries

The SPM package owns the measurement method and publishes reproducible data. Its reader and household calculation work without PolicyEngine, Microcosm, Axiom, a data download or credentials. The development version is 0.5.0; it is not yet a registry release.

| Component | Owns | Consumes |
| --- | --- | --- |
| SPM package | CE sample policy, expenditure construction, threshold estimation, named projections, releases | Pinned BLS/Census inputs; CE survey design weights |
| Microcosm | Entity links, typed weights, population construction and calibration | SPM release and explicit SPM unit classification |
| PolicyEngine | Taxes, benefits, resources and household/population simulation | Selected SPM release through formula providers |
| Axiom | Native rule execution and execution receipts | Versioned national thresholds; explicitly external equivalence and geographic factors in this first bridge |

PE can migrate its execution to Axiom while the release contract stays the same. The initial Axiom adapter is a partial bridge: the real Rust engine applies the released threshold to supplied factors and compares supplied annual resources. It does not yet calculate the fractional-power equivalence scale, construct resource units or calculate the household's taxes and benefits. The permanent user API is the separate `policyengine.py` repository; its development SPM hook is described in [PE integration](policyengine-release-integration.md).

## Release contract

`spm_calculator/data/releases/spm-2026-09-08.json` binds:

- Schema version, release id, creation and information dates, USD/year and the two-adult/two-child reference family.
- National values by target year and tenure, publication/estimate status, method id, source identities and uncertainty information.
- Housing shares with their own source, reference year and published/carried/assumed status. These shares affect both geography and the cap on housing assistance counted as resources.
- Pinned geographic rent indices and source snapshots. The current release bundles official 2024 Census SPM area data and optional 2023 ACS state/county/district research inputs. The custom ACS adjustments are not official SPM thresholds. Areas with nonpositive published rents are explicitly excluded.
- Source checksums and availability dates. Unknown publication dates remain null. The September 8 availability date is conservative snapshot evidence, not a reconstructed real-time information set.

The JSON Schema is [schema-v1.json](../spm_calculator/data/releases/schema-v1.json). The Python reader additionally checks content digests, dates, cross-references and numeric invariants. A digest is an integrity check; source authenticity requires a separately trusted digest or signed distribution.

The content hash is SHA-256 of UTF-8 JSON with sorted keys, compact separators, non-ASCII characters preserved and nonfinite numbers prohibited, excluding only `content_sha256`. Accessors return copies; the provider retains immutable bytes. A supplied `as_of` cannot predate the release information date. No lookup silently downloads a newer release or substitutes an absent year.

The first release uses the corrected BLS national series through 2025. It carries fixed three-decimal 2024 housing shares into other years as an approximation. Geographic thresholds recompute `1 - housing_share + housing_share * rent_index`; they do not claim exact reproduction of Census metro amounts based on the earlier national series and rounding. Published national standard errors do not quantify this geographic/share approximation.

## Browser geography scope

The app exports only the official areas in the [Census 2024 SPM workbook](https://www2.census.gov/programs-surveys/demo/tables/p60/287/SPM-pov-threshold-2024.xlsx): 260 named MSAs, 34 state residual Metro areas and 47 state Nonmetro areas. These 341 entries are all available through the release's `metro` geography kind. State residual entries represent the Census-defined residual area, not an entire state.

The browser does not export the release's custom ACS state, county or district rent lookup tables. National thresholds remain calculation inputs and reference values, rather than an app location choice. Python research helpers and the sealed release retain their existing inputs for compatibility and reproducibility; restricting the browser export leaves the release bytes and content hash unchanged.

The browser's [rolling forecasts](rolling-forecasts.md) form a separate research layer above the sealed release. They advance the CE and ACS windows, estimate missing observations under explicit price and real-spending assumptions, and recompute housing shares and rent indices. Published national 2025 values remain exact, while 2025 geographic inputs are modeled. Both a CE real-spending trend and zero real growth are available through 2030. The forecast has its own content and assumption hashes, retrospective comparisons and support diagnostics. `load_forecast` reproduces the displayed result with all selected-year inputs; `load_release` continues to identify the sealed published inputs. Forecast uncertainty is not estimated.

Local-area population analysis should assign each SPM unit to its official Census area, preserving the mix of areas within a county or district. Microcosm owns those geographic assignments and boundary vintages. A single custom county or district rent adjustment is a different research estimate, not an official geographic SPM threshold.

## Reproduce and use

```sh
uv run scripts/build_release.py --check
uv run scripts/export_web_release.py --check
uv run spm-calculator info
uv run spm-calculator --expect-sha256 YOUR_RETAINED_HASH verify
uv run spm-calculator calculate --year 2025 --adults 2 --children 2 --tenure renter
uv run spm-calculator export --format csv > thresholds.csv
```

The reader and scalar calculation also run in a Python interpreter with site packages disabled. Legacy data-download APIs retain their installed dependencies. New ACS source acquisition for optional Python research is separate from replay: `scripts/build_acs_snapshot.py` requires a caller-supplied Census key, writes no credentials, and stores the raw tables. The website imports only the generated national and official Census area inputs; it does not acquire or export custom ACS rent lookups.

Adult and child counts are already classified SPM counts. Age alone does not establish dependency for every minor-headed unit. CE estimation therefore has a separate, named unresolved-composition policy with weight diagnostics. See [current CE replication](current-ce-replication.md). Microcosm population weights must not replace CE design weights or calibrate away a poverty-rate validation error.

Projections use explicit inputs through `projection.ProjectionInput` and `project_thresholds`. Consumption ratios are anchored to an official base; price-only and blend alternatives retain their method identities. Current corrected-data results are retrospective. They neither replace the frozen 2025 commitment nor establish long-horizon accuracy or an uncertainty interval.

## Compatibility and rollout

Version 0.5.0 deliberately changes numerical values exposed by the existing `HISTORICAL_THRESHOLDS` constant to the corrected canonical series and moves the latest published year to 2025. The `package-legacy-0.3` series remains available for old results. The five imports consumed by PE retain their signatures and return shapes. The year-less `get_housing_share(tenure)` remains exactly 0.434, 0.323 and 0.443; only the explicit provider reads year-specific share fields.

The old PE requirement `spm-calculator>=0.2.0` would admit this correction automatically on upgrade. The paired PE draft must pin the reviewed calculator Git commit while the package is unpublished, with an eventual registry pin of `spm-calculator==0.5.0`. Coordinate that PE pin before any package publication. This work prepares draft changes; it does not merge, publish or deploy them.

The new PE adapter defaults to labeled model-CPI extrapolation beyond the published base. The standalone reader defaults to error. Estimated release entries require explicit opt-in; a declined estimate is identified if the provider extrapolates instead. Provenance includes model parameter identity, endpoint values/classifications, and carried housing-share metadata. Unknown classification is not described as observed inflation. Existing legacy PE extrapolation and geography fallback outside this adapter remain legacy behavior.

Actual local native-engine and wrapper checks are development integration evidence. They do not certify a production PE data bundle or a complete US migration to Axiom. The current published PE wrapper lacks the new SPM release hook, and the public calculator still needs a separately authorized production deployment.
