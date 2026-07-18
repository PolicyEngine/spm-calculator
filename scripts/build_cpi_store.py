"""Regenerate the packaged CPI annual-average store.

``spm_calculator/data/bls/cpi_annual.json`` is the offline fallback
for the FCSUti composite index: annual averages for every CPI series
the composite uses. This script is the only writer. It replaces the
hand-entered ``PRECOMPUTED_FCSUTI_FACTORS`` table (two-significant-
digit guesses) that previously served as the offline path.

Sources, per series: the BLS public data API (annual averages, period
M13) when quota allows — unregistered access caps at 25 requests/day —
falling back to FRED's keyless CSV endpoint, computing annual means
from NSA monthlies. Where both sources yield overlapping years the
script cross-validates them (tolerance 0.1 percent) and records which
source each series came from.

2025 note: BLS's official 2025 annual averages are computed over
eleven months (the October 2025 release was not published during the
federal shutdown); the FRED-derived means use the same eleven months
and match BLS's published M13 values.

Usage:
    uv run --with curl-cffi python scripts/build_cpi_store.py
"""

from __future__ import annotations

import datetime
import io
import json
import time
from pathlib import Path

from spm_calculator.fcsuti_cpi import CPI_SERIES, fetch_bls_cpi_series

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "spm_calculator" / "data" / "bls" / "cpi_annual.json"

START, END = 2005, 2025

# FRED mirrors of the NSA CPI series. Some BLS ids exist on FRED
# verbatim; the aggregates use FRED's own ids (mappings verified
# against BLS API values at <=4e-4 relative difference).
FRED_IDS = {
    "CUUR0000SA0": "CPIAUCNS",
    "CUUR0000SAA": "CPIAPPNS",
    "CUUR0000SAF": "CPIFABNS",
    "CUUR0000SAH1": "CUUR0000SAH1",
    "CUUR0000SAH2": "CUUR0000SAH2",
    "CUUR0000SEED": "CUUR0000SEED",
    "CUUR0000SEEE": "CUUR0000SEEE",
    "CUUR0000SAF11": "CUSR0000SAF11",  # checked below; skipped if absent
    "CUUR0000SEFV": "CUUR0000SEFV",
}


def fetch_bls(series_id: str, attempts: int = 2):
    for attempt in range(attempts):
        try:
            return fetch_bls_cpi_series(series_id, START, END)
        except Exception as error:  # noqa: BLE001
            if attempt == attempts - 1:
                print(f"  BLS API unavailable for {series_id}: {error}")
                return None
            time.sleep(10)
    return None


def fetch_fred(series_id: str):
    import pandas as pd
    from curl_cffi import requests as cr

    fred_id = FRED_IDS.get(series_id)
    if fred_id is None:
        return None
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}"
    r = cr.get(url, impersonate="chrome", timeout=60)
    if r.status_code != 200 or not r.text.startswith("observation_date"):
        return None
    df = pd.read_csv(io.StringIO(r.text), parse_dates=["observation_date"])
    df.columns = ["date", "value"]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    grouped = df.dropna().groupby(df["date"].dt.year)["value"]
    annual = grouped.mean()[grouped.count() >= 11]
    annual = annual[(annual.index >= START) & (annual.index <= END)]
    return None if annual.empty else annual


def main() -> None:
    series_out: dict[str, dict[str, float]] = {}
    sources: dict[str, str] = {}
    for component, series_id in sorted(CPI_SERIES.items()):
        bls = fetch_bls(series_id)
        fred = fetch_fred(series_id)
        if bls is not None and fred is not None:
            overlap = [y for y in bls.index if y in fred.index]
            worst = max(abs(bls[y] / fred[y] - 1) for y in overlap)
            assert worst < 1e-3, (series_id, worst)
            chosen, source = (
                bls,
                f"BLS API (FRED-cross-validated, {worst:.1e})",
            )
        elif bls is not None:
            chosen, source = bls, "BLS API"
        elif fred is not None:
            chosen, source = fred, f"FRED {FRED_IDS[series_id]} (annual mean)"
        else:
            print(f"{component:12s} {series_id}: unavailable, skipped")
            continue
        series_out[series_id] = {
            str(year): round(float(value), 3) for year, value in chosen.items()
        }
        sources[series_id] = source
        print(
            f"{component:12s} {series_id}: {min(chosen.index)}-"
            f"{max(chosen.index)} via {source}"
        )

    required = {
        CPI_SERIES[c]
        for c in (
            "food",
            "apparel",
            "shelter",
            "utilities",
            "telephone",
            "all_items",
        )
    }
    missing = required - set(series_out)
    assert not missing, f"composite components missing: {missing}"

    doc = {
        "generated_by": "scripts/build_cpi_store.py",
        "retrieved": datetime.date.today().isoformat(),
        "years": [START, END],
        "sources": sources,
        "note": (
            "Annual averages (BLS period M13 where API-sourced; "
            "means of NSA monthlies where FRED-sourced). 2025 values "
            "are computed over eleven months — the October 2025 CPI "
            "release was not published during the federal shutdown — "
            "matching BLS's official 2025 annual averages."
        ),
        "series": series_out,
    }
    OUT.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
