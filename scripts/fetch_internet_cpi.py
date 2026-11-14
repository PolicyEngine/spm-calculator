"""Pin the CPI-U series for home internet, CUUR0000SEEE03.

The in-kind replication prices home internet (CE UCC 690114) with
"Internet services and electronic information providers", U.S. city
average, all urban consumers, not seasonally adjusted. This script is the
only writer of ``spm_calculator/data/bls/cpi_internet_receipt.json``: it
posts the BLS public data API requests and keeps the responses verbatim,
so the annual averages (period M13) the replication reads can be checked
against what BLS returned. ``cpi_annual.json`` stays as it is, because the
canonical forecast seals its bytes.

Unregistered API access returns at most ten years per request, so the
script asks for 2005-2014, 2015-2024 and 2025. BLS's 2025 annual averages
cover eleven months: the October 2025 CPI was not collected.

Run: uv run --no-sync python scripts/fetch_internet_cpi.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "spm_calculator/data/bls/cpi_internet_receipt.json"
URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
SERIES_ID = "CUUR0000SEEE03"
SPANS = ((2005, 2014), (2015, 2024), (2025, 2025))


def main():
    exchanges = []
    for start, end in SPANS:
        payload = {
            "seriesid": [SERIES_ID],
            "startyear": str(start),
            "endyear": str(end),
            "annualaverage": True,
        }
        response = requests.post(URL, json=payload, timeout=30)
        response.raise_for_status()
        body = response.json()
        if body.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(f"BLS API error: {body.get('message')}")
        exchanges.append({"request": payload, "response": body})
    document = {
        "generated_by": "scripts/fetch_internet_cpi.py",
        "retrieved": datetime.now(timezone.utc).date().isoformat(),
        "url": URL,
        "series_id": SERIES_ID,
        "title": (
            "Internet services and electronic information providers in "
            "U.S. city average, all urban consumers, not seasonally adjusted"
        ),
        "exchanges": exchanges,
    }
    OUT.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
