# Canonical web performance

## State

Performance follow-up in progress. This lane owns only `web/**`, `scripts/export_web_release.py`, and `tests/test_web_config.py`. Scoped commits are authorized by the standing orders; no push, deployment, or edits to other lanes. Prior canonical handoff: `web/web-canonical-report.md`.

## Done

- Read prior handoff and current controls, warnings, methodology, exporter, and tests.
- Measured baseline release JSON: 30,028,969 bytes (2,081,567 gzip); generated HTML: 19,155,589 bytes (1,971,729 gzip). gzip uses Python default compression level 9 and mtime 0.
- Identified full scenario diagnostics and scientific fold records in browser data plus static JSON import crossing the server/client boundary.
- Assigned independent client loading and visible warning/methodology work.

## Next

- Export compact UI inputs and displayed diagnostics without modifying the scientific artifact; retain a pinned byte-identical explicit audit download.
- Fetch compact data once with base-path support and loading/error/retry states. Preserve all 14 years, both scenarios, real area menus, source cells, numerical outputs, and warnings.
- Check canonical source stability before export, then run export equality, numerical replay, Vitest, and webpack production build.
- Record final sizes, checks, remaining root/browser/publication work in `web/WEB-PERFORMANCE-HANDOFF.md`.
