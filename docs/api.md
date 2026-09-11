# API reference

Version 1.0.0 exposes one current forecast calculation path.
Examples use public interfaces of the published package.

| Task | Interface |
| --- | --- |
| Load the current artifact and calculate a unit | [`SPMForecast`, `load_forecast`, `SPMUnit`](api/forecast.md) |
| Resolve county assignment or inspect a year's areas | [Forecast geography methods](api/geography.md) |
| Scale already classified adult/child counts | [`spm_equivalence_scale`](api/equivalence_scale.md) |
| Preserve or reconstruct resource-unit membership | [`spm_unit_id` and partition comparison](api/units.md) |
| Read published national source values | [`get_published_thresholds`](api/forecast.md#published-source-access) |
| Apply thresholds inside PolicyEngine | [Canonical provider and country configuration](policyengine-release-integration.md) |
| Apply and summarize actual Frames | [Microcosm integration](microcosm-integration.md) |
| Execute native classification and arithmetic | [Actual Axiom core integration](axiom-integration.md) |

The [quickstart](quickstart.md) also covers the installed CLI.
The [artifact contract](spm-releases.md) distinguishes schema-2 forecasts from
archived schema-1 release records. Retired calculator/geographic helper pages
are replaced by the forecast and geography references above; there is no
current runtime compatibility shim.
