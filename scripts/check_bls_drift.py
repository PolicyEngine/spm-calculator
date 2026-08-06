"""Check the packaged threshold series against BLS's live publication.

Downloads the BLS SPM-thresholds workbook and compares every
overlapping (year, tenure) threshold against the packaged default
series. Exits non-zero on divergence — including years BLS publishes
that the package lacks — so a scheduled CI job can open an issue; a
BLS revision then surfaces within a week instead of whenever a human
notices. This is the check that would have caught both the package's
hand-entry errors and BLS's 2026-07-17 correction on day one.

BLS blocked-download handling: bls.gov rejects default TLS clients, so
this script requires ``curl_cffi``. Network failures and HTTP blocks
exit with code 78 ("skip"), distinct from the divergence exit code 1,
so CI treats unreachability as neutral rather than alarming.

Usage:
    uv run --with curl-cffi --with openpyxl python scripts/check_bls_drift.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_threshold_series import parse_workbook  # noqa: E402

from spm_calculator.forecast import (  # noqa: E402
    HISTORICAL_THRESHOLDS,
    get_thresholds,
)

TOLERANCE = 0.005  # dollars; workbook values are exact to the cent

CANDIDATE_URLS = [
    # Corrected workbook published 2026-07-17. When BLS next reissues
    # thresholds (e.g., adding 2025), add the new filename FIRST and
    # keep the old ones as fallbacks.
    "https://www.bls.gov/pir/spm/spm_threshold_200524_corrected.xlsx",
]

SKIP_EXIT = 78


def fetch_workbook() -> bytes | None:
    try:
        from curl_cffi import requests as cr
    except ImportError:
        print("curl_cffi unavailable; skipping drift check.")
        return None
    for url in CANDIDATE_URLS:
        try:
            r = cr.get(url, impersonate="chrome", timeout=120)
        except Exception as e:  # noqa: BLE001
            print(f"fetch failed for {url}: {e}")
            continue
        if r.status_code == 200 and r.content[:2] == b"PK":
            print(f"fetched {url} ({len(r.content):,} bytes)")
            return r.content
        print(f"{url}: status {r.status_code}, not a workbook")
    return None


def check_page_vintage(latest_year: int) -> list[str]:
    """Warn when the per-year BLS page serves superseded values.

    Observed 2026-08-06: spm_thresholds_2024.htm again displayed the
    pre-correction values with no correction notice, while the
    corrected workbook carried different numbers. The workbook
    comparison above cannot see that, so this checks the page text for
    the pre-correction vintage. Non-fatal: the inconsistency is on
    BLS's side, so it warns rather than fails.
    """
    try:
        from curl_cffi import requests as cr
    except ImportError:
        return []
    url = f"https://www.bls.gov/pir/spm/spm_thresholds_{latest_year}.htm"
    try:
        r = cr.get(url, impersonate="chrome", timeout=120)
    except Exception:  # noqa: BLE001
        return []
    if r.status_code != 200:
        return []
    superseded = get_thresholds(
        latest_year, series="census-published-pre-correction"
    )
    stale = [
        f"{tenure} ${value:,.0f}"
        for tenure, value in superseded.items()
        if f"{value:,.0f}" in r.text
    ]
    if not stale:
        return []
    return [
        f"WARNING: {url} displays pre-correction {latest_year} values "
        f"({'; '.join(stale)}) — superseded by the corrected workbook"
    ]


def flatten(published: dict, revised: dict) -> dict[int, dict[str, float]]:
    """Rebuild the canonical splice: published <=2018, revised 2019+."""
    flat: dict[int, dict[str, float]] = {}
    for bucket in (published, revised):
        for year_str, tenures in bucket.items():
            year = int(year_str)
            if bucket is published and year >= 2019:
                continue  # the workbook's "2019 Published" column
            flat[year] = {
                tenure: measures["threshold"]
                for tenure, measures in tenures.items()
            }
    return flat


def main() -> int:
    content = fetch_workbook()
    if content is None:
        print("BLS unreachable or blocked; treating as neutral skip.")
        return SKIP_EXIT

    with tempfile.NamedTemporaryFile(suffix=".xlsx") as tmp:
        tmp.write(content)
        tmp.flush()
        published, revised = parse_workbook(Path(tmp.name))

    live = flatten(published, revised)

    divergences: list[str] = []
    for year in sorted(set(live) | set(HISTORICAL_THRESHOLDS)):
        if year not in HISTORICAL_THRESHOLDS:
            divergences.append(
                f"{year}: BLS publishes this year; package lacks it "
                f"(new release? run scripts/build_threshold_series.py)"
            )
            continue
        if year not in live:
            divergences.append(
                f"{year}: packaged but absent from the live workbook"
            )
            continue
        for tenure, live_value in live[year].items():
            packaged = HISTORICAL_THRESHOLDS[year].get(tenure)
            if packaged is None or abs(packaged - live_value) > TOLERANCE:
                divergences.append(
                    f"{year} {tenure}: packaged {packaged} != "
                    f"live {live_value}"
                )

    if divergences:
        print("DRIFT DETECTED between packaged series and bls.gov:")
        for line in divergences:
            print(f"  - {line}")
        return 1

    for warning in check_page_vintage(max(live)):
        print(warning)

    print(f"No drift: {len(live)} years match bls.gov within ${TOLERANCE}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
