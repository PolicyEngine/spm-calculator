# Progress

## State

Core implementation is complete on `max/bls-2026-threshold-correction`; documentation of known approximations, integration review, and the full verification bar remain.

## Done

- Confirmed the requested worktree, branch, clean starting state, and starting commit `d2746cf`.
- Fixed the drift-watch pipeline status capture so checker exit code 1 can open an issue, with a regression test (review A).
- Bundled and pinned BLS's current workbook, generated the full-precision 2025 segment, advanced the published base, and retained the superseded nowcast with a warning (review B and assignment items 1–3).
- Corrected the tracked CPI composite and made both projection scripts use it by default (review C).
- Added the executable 50/50 rule and a provenance-bearing four-rule backtest artifact with golden MAEs (review D).
- Removed all specified stale pre-repair values and added a repository-wide regression guard (review E).
- Corrected the CE six-code tenure schema and made incomplete CE/CPI inputs fail closed (reviews F–G).
- Pinned trusted workbook hashes and expanded drift checks across both workbooks, all measures, and the 2025 Chart 1 table (reviews H–I).
- Made published-threshold fallback an explicit opt-in (review J).
- Regenerated the web configuration so 2025 is published, preserved future-nowcast UI machinery, and added the archived 2025 evaluation.
- Updated the correction narrative and README, and added the towncrier fragment.

## Next

- Finish review K's approximation docstrings and matching documentation section.
- Run the requirements audit and full Python, Ruff, nowcast, stale-marker, and web verification.
- Record final hashes/statistics here and write the requested final report.
