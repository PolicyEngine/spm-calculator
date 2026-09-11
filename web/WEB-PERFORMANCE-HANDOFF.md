# Canonical web performance handoff

This document preserves the original performance and source snapshot below. Its original pending-browser list and artifact hashes are historical. The current browser suite in `e2e/calculator.spec.mjs` covers search, headers, forecast years, failed/stalled request recovery, unavailable areas, historical series breaks, rental diagnostics and the currently linked audit download on both mounts. Acceptance requires successful hosted runs bound to the exact reviewed revision. Final public acceptance with published-package metadata remains a separate release requirement; a test definition or development run does not establish it.

The canonical calculator now fetches a compact UI export once, with loading, error, retry, cancellation and timeout handling. No forecast data is embedded in SSR HTML, RSC, or the application JavaScript bundles. This work is committed and ready for root's CUA browser checks and publication/deployment workflow. No push or deployment was performed; live UX has not been verified.

| Artifact | Before, bytes | After, bytes | Before gzip, bytes | After gzip, bytes |
| --- | ---: | ---: | ---: | ---: |
| Browser JSON | 30,028,969 | 1,225,568 | 2,081,567 | 109,965 |
| Production HTML | 19,155,589 | 39,025 | 1,971,729 | 8,937 |
| Production RSC (`index.txt`) | Not captured | 8,608 | Not captured | 2,814 |

JSON is 95.92% smaller raw and 94.72% smaller gzip. HTML is 99.80% smaller raw and 99.55% smaller gzip. Measurements use actual file bytes and Python gzip level 9 with `mtime=0`; hosted transfer sizes depend on server compression. The production JavaScript files total 1,146,801 uncompressed bytes, without the scientific payload. All 11 local assets referenced by generated HTML exist in `web/out/`.

The exporter retains exact thresholds, housing shares, rent indices, component statuses, source windows, area names/types, source IDs, provenance hashes, displayed CE/ACS validation metrics, growth fits and applicable warning diagnostics. It excludes unrendered scientific folds, cohort/donor records, county assignments and sensitivity records. Two exact menu pools and eight exact geography pools eliminate repeated data across years/scenarios. Pooling compares complete values; it never assumes different scenarios have identical geography and never rounds numbers. The loader expands shared records once and preserves the existing calculator data contract.

The initial server page shows an accessible loading state. A single compact fetch enables the complete calculator and all year comparisons together; there is no partially loaded year/scenario state. The data request and explicit audit-download link respect `NEXT_PUBLIC_BASE_PATH`. Failed, invalid and stalled requests provide a retry button. The full scientific artifact is requested only when a user activates its download link.

All 14 years (2022–2035), both scenarios, all 349 actual annual MSA/residual/nonmetro menu entries, all three tenures, and all 12 published 2022–2025 national threshold/housing-share source cells are preserved. An area absent in a later year remains unavailable until the user selects a valid area. Thin support and topcoding warnings retain their original numbers and flags. Massachusetts Nonmetro and Sumter/South Carolina Metro 2022→2023 series-break disclosures use the new canonical metadata and remain visible when later years are selected because the comparison table includes those historical years.

Methodology now states that relative rent indices stabilize from 2029 once the five-year window contains only the 2024 donor distribution and its projected copies under uniform national rent growth. The 2029 window still contains the observed 2024 cohort. The whole-threshold geography factor can continue changing with `housing_share`. The UI does not claim indefinite changes in relative indices. Package `1.0.0` remains `local_preview`; no published-package or PolicyEngine-runtime claim was added.

The scientific worker's refreshed artifact was used only after repeated stable reads, with a second byte comparison before export. Export `--check` passes against the current source. No scientific source artifact was edited or deleted by this lane. The full byte-identical source remains available as:

`web/public/data/canonical/rolling-forecast-76ab8435f087f167ad01b8495ebd016415ba8086f32bfbd3dab961dcc8976c0a.json`

- Canonical content SHA-256: `b9dbf5ae49697e3bf3abee2fa22b7429703412cb1e58478938a682a0dfddc821`
- Download/source-file SHA-256: `76ab8435f087f167ad01b8495ebd016415ba8086f32bfbd3dab961dcc8976c0a`
- Full download size: 26,606,301 bytes. The filename pins exact file bytes; the internal content hash pins the scientific document. Older pins are retained by the exporter.

Validation completed:

- `python3 -m pytest tests/test_web_config.py -q`: **59 passed**, including source mutation during derivation, audit integrity, exact input/provenance preservation, compact-size bound, historical metadata and standalone Python numerical replay.
- `python3 -m scripts.export_web_release --check`: **passed**, including byte equality of the pinned audit download.
- `cd web && bun run test`: **115 passed across 6 files**. Includes 205,212 numerical replays (14 years × 2 scenarios × 349 areas × 3 tenures × 7 household compositions), all actual annual menus, source cells, warning parity, full comparison tables and loader failure/base-path behavior.
- Independent read-only review checked all 9,772 area/year/scenario selections, 7,724 median-warning selections, 56 historical-warning selections, growth fits and all 59 source links/labels/hashes against canonical data: **no actionable regression found**.
- `cd web && bun run build --webpack`: **passed**, producing a static production export. Webpack was selected because the prior worker encountered a sandbox-prohibited Turbopack worker port bind.
- Black/Ruff for exporter/tests, Prettier for changed web code, scoped whitespace checks, and generated HTML/RSC/JS payload inspection: **passed**.

Only `web/**`, `scripts/export_web_release.py`, and `tests/test_web_config.py` were edited or committed in this follow-up. Scoped implementation includes the prior worker's uncommitted canonical web changes. Other active lanes' changes were left untouched. Progress is committed in `web/PROGRESS.md`; implementation commits are `52b41b1`, `801dbd0`, and `ada7b5b` (this handoff/progress update is a subsequent documentation commit).

Root's remaining work:

1. Use CUA for desktop/mobile browser QA: initial loading responsiveness, hydration, retry after a failed request, search/menu keyboard and click selection, all-year comparisons, unavailable-area transitions, Massachusetts/Sumter labels, thin-support/topcoding warnings, table scrolling and audit download. Verify the final hosted base path and asset responses. These have unit/static coverage, not browser verification. No Chrome CDP was used.
2. If the scientific worker changes the canonical artifact again, run `python3 -m scripts.export_web_release`, then `python3 -m scripts.export_web_release --check`, the Python/Vitest suites and the webpack build before deployment. The regenerated compact export and audit pin must travel together.
3. Version 1.0.0 was published to PyPI on September 11, 2026, so this step is now due: regenerate with `SPM_PUBLISHED_PACKAGE_VERSION=1.0.0`, rebuild using the intended `NEXT_PUBLIC_BASE_PATH`, and perform the root-owned deployment/live checks. Until that runs, the deployed export keeps its `local_preview` status and the page labels the build a development preview whose publication is not confirmed.
