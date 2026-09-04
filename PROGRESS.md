# Progress

## State

Implementation and verification are complete on `max/bls-2026-threshold-correction`. The branch is ready for review; it has not been pushed or merged.

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
- Froze the original CE-replication levels as tracked evaluation provenance so the corrected CE classifier cannot rewrite the historical 2025 forecasting commitment.
- Documented all requested CE replication approximations and completed the final requirements audit.
- Reproduced the threshold series, four-rule backtest, nowcast, and web configuration from their generators without uncommitted differences.
- Passed the final verification bar: 235 Python tests passed and 18 skipped; Ruff format/check passed; 6 web tests passed; the stale-marker guard passed; and the nowcast script reproduced $41,036.34 / $34,135.99 / $40,755.98 from tracked inputs.

## Next

- Review the commits and open/update PR #32 when ready. No implementation work remains in this lane.
