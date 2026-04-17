"""
Generate bundled metro data and static web assets for the SPM calculator.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import openpyxl
import requests


def _read_package_version() -> str:
    """Read spm-calculator's version from pyproject.toml.

    Keeps the web bundle's ``packageVersion`` field in lockstep with
    the Python package's release tag without requiring tomllib.
    """
    repo_root = Path(__file__).resolve().parent.parent
    pyproject = (repo_root / "pyproject.toml").read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    if not match:
        raise RuntimeError("Could not find a version field in pyproject.toml")
    return match.group(1)


HISTORICAL_THRESHOLDS = {
    "2015": {
        "renter": 25155,
        "owner_with_mortgage": 24859,
        "owner_without_mortgage": 20639,
    },
    "2016": {
        "renter": 25558,
        "owner_with_mortgage": 25248,
        "owner_without_mortgage": 20943,
    },
    "2017": {
        "renter": 26213,
        "owner_with_mortgage": 25897,
        "owner_without_mortgage": 21527,
    },
    "2018": {
        "renter": 26905,
        "owner_with_mortgage": 26565,
        "owner_without_mortgage": 22095,
    },
    "2019": {
        "renter": 27515,
        "owner_with_mortgage": 27172,
        "owner_without_mortgage": 22600,
    },
    "2020": {
        "renter": 28881,
        "owner_with_mortgage": 28533,
        "owner_without_mortgage": 23948,
    },
    "2021": {
        "renter": 31453,
        "owner_with_mortgage": 31089,
        "owner_without_mortgage": 26022,
    },
    "2022": {
        "renter": 33402,
        "owner_with_mortgage": 32949,
        "owner_without_mortgage": 27679,
    },
    "2023": {
        "renter": 36606,
        "owner_with_mortgage": 36192,
        "owner_without_mortgage": 30347,
    },
    "2024": {
        "renter": 39430,
        "owner_with_mortgage": 39068,
        "owner_without_mortgage": 32586,
    },
}

CPI_PROJECTIONS = {
    2025: 0.025,
    2026: 0.023,
    2027: 0.022,
    2028: 0.020,
    2029: 0.020,
    2030: 0.020,
}

LATEST_PUBLISHED_YEAR = 2024
REFERENCE_RAW_SCALE = 3**0.7
TENURE_HOUSING_SHARES = {
    "owner_with_mortgage": 0.434,
    "owner_without_mortgage": 0.323,
    "renter": 0.443,
}
METRO_SOURCE_URL = (
    "https://www2.census.gov/programs-surveys/demo/tables/p60/287/"
    "SPM-pov-threshold-2024.xlsx"
)


def forecast_thresholds(year: int) -> dict:
    base = HISTORICAL_THRESHOLDS[str(LATEST_PUBLISHED_YEAR)]
    factor = 1.0
    for y in range(LATEST_PUBLISHED_YEAR + 1, year + 1):
        factor *= 1 + CPI_PROJECTIONS.get(y, 0.020)
    return {
        tenure: int(round(value * factor)) for tenure, value in base.items()
    }


def generate_all_thresholds():
    all_thresholds = dict(HISTORICAL_THRESHOLDS)
    for year in range(LATEST_PUBLISHED_YEAR + 1, 2031):
        all_thresholds[str(year)] = forecast_thresholds(year)
    return all_thresholds


def _load_workbook_from_bytes(content: bytes):
    from io import BytesIO

    return openpyxl.load_workbook(BytesIO(content), data_only=True)


def generate_metro_data() -> dict:
    response = requests.get(METRO_SOURCE_URL, timeout=60)
    response.raise_for_status()
    workbook = _load_workbook_from_bytes(response.content)
    sheet = workbook["Thresholds 2024"]

    national_thresholds = HISTORICAL_THRESHOLDS["2024"]
    metro_areas = {}

    for row in sheet.iter_rows(min_row=3, values_only=True):
        code = row[0]
        if code is None or row[2] is None:
            continue

        rent_index = float(row[2])
        reference_thresholds = {
            "owner_with_mortgage": int(row[3]),
            "owner_without_mortgage": int(row[4]),
            "renter": int(row[5]),
        }
        adjustments = {
            tenure: reference_thresholds[tenure] / national_thresholds[tenure]
            for tenure in national_thresholds
        }

        metro_areas[str(int(code)).zfill(4 if int(code) < 10000 else 5)] = {
            "name": row[1],
            "rentIndex": rent_index,
            "adjustments": adjustments,
            "referenceThresholds": reference_thresholds,
        }

    return {
        "year": 2024,
        "source": "Census Bureau SPM Thresholds by Metro Area 2024",
        "sourceUrl": METRO_SOURCE_URL,
        "nationalThresholds": national_thresholds,
        "housingShares": TENURE_HOUSING_SHARES,
        "metroAreas": metro_areas,
    }


def generate_data():
    repo_root = Path(__file__).resolve().parent.parent
    package_data_dir = repo_root / "spm_calculator" / "data"
    web_data_dir = repo_root / "web" / "public" / "data"
    package_data_dir.mkdir(parents=True, exist_ok=True)
    web_data_dir.mkdir(parents=True, exist_ok=True)

    metro_data = generate_metro_data()
    all_thresholds = generate_all_thresholds()

    with open(package_data_dir / "metro_geoadj_2024.json", "w") as f:
        json.dump(metro_data, f, indent=2)

    with open(web_data_dir / "metro_geoadj.json", "w") as f:
        json.dump(metro_data, f, indent=2)

    config = {
        "packageVersion": _read_package_version(),
        "baseThresholds": all_thresholds,
        "methodology": {
            "referenceRawScale": REFERENCE_RAW_SCALE,
            "housingShares": TENURE_HOUSING_SHARES,
            "equivalenceScale": {
                "singleAdultFirstChild": 0.8,
                "additionalChild": 0.5,
                "economiesOfScale": 0.7,
                "twoAdultNoChild": 1.41,
                "referenceFamilyRaw": REFERENCE_RAW_SCALE,
            },
        },
        "forecast": {
            "latestPublishedYear": LATEST_PUBLISHED_YEAR,
            "cpiProjections": {str(k): v for k, v in CPI_PROJECTIONS.items()},
        },
    }

    # `base_thresholds.json` used to be written here alongside
    # `spm_config.json`, but the web app only reads the config file
    # (which already carries `baseThresholds`). Dropping the duplicate
    # file avoids a drift risk if someone updates one without the other.
    with open(web_data_dir / "spm_config.json", "w") as f:
        json.dump(config, f, indent=2)

    print(f"Wrote {package_data_dir / 'metro_geoadj_2024.json'}")
    print(f"Wrote {web_data_dir / 'metro_geoadj.json'}")
    print(f"Wrote {web_data_dir / 'spm_config.json'}")


if __name__ == "__main__":
    generate_data()
