"""National canonical bases preserve BLS's published spreadsheet precision."""

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from spm_calculator.published_thresholds import get_published_thresholds
from spm_calculator.rolling_forecast import load_forecast

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = json.loads(
    (
        ROOT / "spm_calculator/data/current/bls_published_cell_receipt.json"
    ).read_text()
)
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _cell(document, address):
    return document.find(f'.//s:c[@r="{address}"]', NS)


@pytest.fixture(scope="module")
def workbook_documents():
    result = {}
    for name, source in RECEIPT["workbooks"].items():
        path = ROOT / source["path"]
        assert (
            hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]
        )
        with ZipFile(path) as archive:
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            sheet = workbook.find("s:sheets/s:sheet", NS)
            assert sheet.get("name") == source["sheet"]
            result[name] = ET.fromstring(
                archive.read(source["worksheet_part"])
            )
    return result


@pytest.mark.parametrize(
    "record",
    RECEIPT["records"],
    ids=lambda row: f"{row['year']}-{row['tenure']}-{row['cell']}",
)
def test_canonical_value_is_published_literal_cell(record, workbook_documents):
    """Reject reconstructed or integer-truncated national anchor values."""
    document = workbook_documents[record["workbook_id"]]
    cell = _cell(document, record["cell"])
    assert cell is not None
    assert cell.get("t") in (None, "n")
    assert cell.find("s:f", NS) is None
    literal = cell.find("s:v", NS).text
    assert literal == record["xml_numeric_literal"]
    value = float(literal)
    assert value == record["published_full_precision"]
    assert value == get_published_thresholds(record["year"])[record["tenure"]]

    forecast = load_forecast()
    for scenario in ("ce_trend", "zero_real"):
        entry = forecast.entry(record["year"], scenario=scenario)
        assert entry["national_status"] == "published"
        assert entry["thresholds"][record["tenure"]] == value

    # The rolling current workbook independently preserves the corrected cells.
    if "corroborating_workbook_id" in record:
        current = workbook_documents[record["corroborating_workbook_id"]]
        assert _cell(current, record["cell"]).find("s:v", NS).text == literal

    rounded = int(
        Decimal(literal).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    assert rounded == record["page_whole_dollars"]
    if record["year"] in (2024, 2025):
        comparison = RECEIPT["pages"]["current_2025_chart_2"]
        year_values = comparison["whole_dollar_values"][str(record["year"])]
        assert year_values[record["tenure"]] == rounded


def test_receipt_covers_every_published_canonical_year_and_tenure():
    tenures = {"owner_with_mortgage", "owner_without_mortgage", "renter"}
    assert len(RECEIPT["records"]) == 12
    assert {(row["year"], row["tenure"]) for row in RECEIPT["records"]} == {
        (year, tenure) for year in range(2022, 2026) for tenure in tenures
    }


def test_source_checksums_and_vintage_are_independently_reconciled():
    source = json.loads((ROOT / RECEIPT["canonical_source_path"]).read_text())
    corrected = source["series"][RECEIPT["canonical_series"]]
    assert (
        corrected["provenance"]["sha256"]
        == (RECEIPT["workbooks"]["corrected_2005_2024"]["sha256"])
    )
    current = corrected["segments"]["bls-published-2025"]["provenance"]
    assert (
        current["sha256"]
        == (RECEIPT["workbooks"]["current_through_2025"]["sha256"])
    )
    vintage = RECEIPT["annual_page_vintage"]
    old = get_published_thresholds(2024, series=vintage["superseded_series"])
    assert old == vintage["superseded_2024_values"]
    corrected_rounded = {
        row["tenure"]: row["page_whole_dollars"]
        for row in RECEIPT["records"]
        if row["year"] == 2024
    }
    assert all(
        old[tenure] != value for tenure, value in corrected_rounded.items()
    )
