The standalone app now uses one canonical schema-2 forecast path for 2022–2035. Search and selection use each year's SPM estimation areas, retain unavailable selections across year changes, and distinguish published national thresholds/housing shares from modeled geography and forecasts. Methodology and provenance live in the results footnote under one shared ui-kit header.

Changed files:

- `scripts/export_web_release.py`: canonical export, complete scenarios/statuses/diagnostics, year-specific areas, explicit package publication configuration.
- `tests/test_web_config.py`: canonical export, area membership/status, numerical replay, BLS shares and publication-gate regressions.
- `tests/test_rolling_forecast_artifact.py`: only removed the obsolete frozen `web/public/data/spm_config.json` parameter; preserved both scientific source-archive assertions. Other changes in this coordinated file belong to other lanes.
- `web/app/layout.jsx`, `web/app/page.jsx`: accurate geography description and shared page shell.
- `web/src/components/CalculatorWorkbench.jsx`, `web/src/components/ForecastDiagnostics.jsx`, `web/lib/forecastValidation.js`: canonical calculations, controls, component status, applicable backtest limitations and provenance.
- `web/public/data/release_config.json`: regenerated from canonical artifact.
- `web/tests/CalculatorWorkbench.test.jsx`, `web/tests/rollingForecast.test.jsx`, `web/tests/offlineRelease.test.jsx`, `web/tests/forecastValidation.test.jsx`, `web/tests/fixtures/rollingCalculatorData.js`: canonical UI and offline integration regressions.
- `web/PROGRESS.md`, `web/web-canonical-report.md`: lane progress and final report.

Removed superseded browser files: `web/public/data/spm_config.json`, `web/public/data/metro_geoadj.json`, and `web/tests/fixtures/calculatorData.js`. Source archives outside web were preserved.

Verification:

- Canonical export and `python3 -m scripts.export_web_release --check`: pass.
- `python3 -m pytest tests/test_web_config.py -q`: 51 passed.
- Remaining frozen scientific source-archive checks: 2 passed.
- `cd web && bun run test`: 81 passed across 4 files.
- `cd web && bun run build --webpack`: production static build passed. Default `bun run build` was blocked by Turbopack's CSS worker attempting a sandbox-prohibited local port bind.
- Black/Ruff for exporter/tests, Prettier for edited web code, and whitespace checks: pass.
- Generated HTML audit: one shared navigation toggle, one results footnote, and all 14 year options. This is not real-browser verification.

Canonical content hash: `2fbe0ec23344719c705d378e25242813a51f6bf05ba2af9a14f5a4945432565d`. Exported scenario entries exactly match the source artifact; no forecasts were re-estimated. Geography coverage is 342 published areas plus 7 modeled groups in 2022, and 341 plus 8 thereafter. BLS national thresholds and housing shares remain published through 2025. Future CBO CPI ratios are explicitly a uniform component/rent-growth modeling assumption. CE and ACS backtest limits are explicit for unsupported horizons and unanchored groups.

Parent integration / remaining verification:

- Verify real desktop/mobile rendering, hydration, search keyboard/click selection, changed-year unavailable selections, table scrolling, and deployed asset paths. The complete export is approximately 30 MB JSON / 2.08 MB gzip; generated HTML is approximately 19 MB uncompressed, so verify loading responsiveness.
- Package version `1.0.0` is honestly labeled local build/development preview. After that exact version is actually published, regenerate with `SPM_PUBLISHED_PACKAGE_VERSION=1.0.0 python3 -m scripts.export_web_release` (or `--published-package-version 1.0.0`). Mismatching versions fail; only matching publication removes preview links and enables the versioned PyPI link.
- Regenerate/check the export if the scientific agent changes the canonical artifact hash or package version. Parent owns publication and deployment.
- Copying to the requested `/Users/maxghenis/spm-rebuild-20260908/rollout/web-canonical-report.md` failed with `Operation not permitted`: that directory is outside this session's writable roots. This report is saved under `web/` for parent transfer.

No commits, pushes, deployment, git mutations, or scientific artifact/adapter edits were made in this lane. The task-specific no-commit restriction took precedence over the standing commit/progress-commit request.
