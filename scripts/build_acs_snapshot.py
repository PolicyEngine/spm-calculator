"""Pin Census ACS rent tables for offline browser lookups.

Requires CENSUS_API_KEY only when explicitly downloading. Credentials and
authenticated URLs are never written into the snapshot or diagnostics.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "spm_calculator/data/acs_rents_2023.json"
VARIABLE = "B25031_004E"
URL = "https://api.census.gov/data/2023/acs/acs5"


def main():
    key = os.environ.get("CENSUS_API_KEY")
    if not key:
        raise SystemExit(
            "CENSUS_API_KEY is required to download a new snapshot"
        )
    responses = {}
    for kind, query in (
        ("national", "us:*"),
        ("state", "state:*"),
        ("county", "county:*"),
    ):
        try:
            response = requests.get(
                URL,
                params={"get": f"NAME,{VARIABLE}", "for": query, "key": key},
                timeout=60,
            )
            if response.status_code != 200:
                raise ValueError("non-200 response")
            rows = response.json()
            if not isinstance(rows, list) or not rows:
                raise ValueError("invalid table")
        except Exception:
            raise SystemExit(
                f"Census {kind} request failed; no snapshot written"
            ) from None
        responses[kind] = rows
    data = {
        "year": 2023,
        "retrieved_on": datetime.now(timezone.utc).date().isoformat(),
        "source_url": URL,
        "variable": VARIABLE,
        "raw_tables": responses,
    }
    data["raw_tables_sha256"] = hashlib.sha256(
        json.dumps(responses, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    OUT.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Pinned Census national/state/county tables to {OUT.name}")


if __name__ == "__main__":
    main()
