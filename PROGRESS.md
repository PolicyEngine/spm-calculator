# Progress

## State

Implementing the BLS 2025 published-threshold update and the additional review fixes on `max/bls-2026-threshold-correction`.

## Done

- Confirmed the requested worktree, branch, clean starting state, and starting commit `d2746cf`.
- Fixed the drift-watch pipeline status capture so checker exit code 1 can open an issue, with a regression test (review A).

## Next

- Inspect and ingest the current BLS workbook while preserving the 2005–2024 generated series byte-for-byte.
- Apply remaining review items B–K as separate, tested commits.
- Regenerate package and web artifacts, run all required verification, and write the final report.
