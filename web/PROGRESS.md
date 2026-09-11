# Canonical web performance

## State

Authorized web performance work complete and committed. Root-owned CUA/live checks, publication and deployment remain. This lane owns only `web/**`, `scripts/export_web_release.py`, and `tests/test_web_config.py`. Scoped commits are authorized by the standing orders; no push, deployment, or edits to other lanes. Prior canonical handoff: `web/web-canonical-report.md`.

## Done

- Read prior handoff and current controls, warnings, methodology, exporter, and tests.
- Measured baseline release JSON: 30,028,969 bytes (2,081,567 gzip); generated HTML: 19,155,589 bytes (1,971,729 gzip). gzip uses Python default compression level 9 and mtime 0.
- Identified full scenario diagnostics and scientific fold records in browser data plus static JSON import crossing the server/client boundary.
- Assigned independent client loading and visible warning/methodology work.

- Derived transport now uses two exact menu pools and eight exact geography pools; excludes unrendered scientific folds, donor diagnostics, county assignments and sensitivity records. Numbers are unchanged.
- Canonical content hash refreshed to `b9dbf5ae49697e3bf3abee2fa22b7429703412cb1e58478938a682a0dfddc821`; source file SHA-256 `76ab8435f087f167ad01b8495ebd016415ba8086f32bfbd3dab961dcc8976c0a`. The byte-identical file is copied to a content-addressed explicit download under `web/public/data/canonical/`.
- Client fetch handles base paths, loading, errors, retries, unmount cancellation, and request timeout. No scientific JSON enters SSR/RSC.
- Selected-area Massachusetts/Sumter historical warnings and accurate 2029 donor-distribution stabilization note are visible; material topcoding/thin-support diagnostics preserved.
- Python export suite: 59 passed; export/audit `--check`: passed. Full Vitest suite: 115 passed, including 205,212 numerical replays and all actual year menus. Webpack production static build: passed. No browser/UX verification performed.
- Added passing export-integrity regressions: source mutation during derivation writes nothing; missing/corrupt pinned audit downloads fail checks and are never overwritten.
- Independent full data-contract review found no actionable regression. Production HTML is 39,025 bytes / 8,937 gzip; RSC is 8,608 / 2,814. All 11 initial local asset references resolve, and no scientific payload is embedded in HTML/RSC/JS.
- Wrote final report to `web/WEB-PERFORMANCE-HANDOFF.md`.
- Compact JSON: 1,225,568 bytes / 109,965 gzip (95.92% / 94.72% smaller than baseline).

## Next

- Root: perform CUA desktop/mobile/live loading, interaction and download QA; this lane did not verify browser UX and used no Chrome CDP.
- Root: after any further scientific hash change, regenerate/check the compact export and audit pin together, rerun checks, and rebuild.
- Root: publish the exact package before setting its published-version flag; package 1.0.0 remains a local preview. Deployment and live checks belong to root.
- Final handoff, exact size measurements, pinned hashes, commands and remaining work: `web/WEB-PERFORMANCE-HANDOFF.md`.
