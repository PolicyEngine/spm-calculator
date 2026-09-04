"""Check packaged SPM thresholds against every live BLS source.

The check has three independent lanes:

* the frozen 2005--2024 correction workbook, which must continue to match
  the packaged correction-vintage thresholds, standard errors, and tenure
  shares;
* BLS's rolling ``spm_thresholds.xlsx`` workbook, which contains the
  full-precision 2025 release and is where a revision or a new annual
  release is expected to appear first; and
* the rounded values in the annual page's linked Chart 1 data table.

Any value drift, missing packaged year, or unparseable required source
exits with code 1 so scheduled CI can open an issue. Network failures and
HTTP blocks exit with code 78 ("skip"), keeping source unavailability
distinct from an observed data difference.

Usage:
    uv run --with curl-cffi --with openpyxl python scripts/check_bls_drift.py
"""

from __future__ import annotations

import re
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_threshold_series import TENURES, parse_workbook  # noqa: E402

from spm_calculator.forecast import (  # noqa: E402
    HISTORICAL_THRESHOLDS,
    get_standard_errors,
    get_tenure_shares,
    get_thresholds,
)

FROZEN_WORKBOOK_URL = (
    "https://www.bls.gov/pir/spm/spm_threshold_200524_corrected.xlsx"
)
CURRENT_WORKBOOK_URL = "https://www.bls.gov/pir/spm/spm_thresholds.xlsx"
PUBLICATION_PAGE_2025_URL = (
    "https://www.bls.gov/pir/spm/spm_thresholds_2025.htm"
)
CHART_1_2025_URL = "https://www.bls.gov/pir/spm/spm_chart_1_2025_data.htm"

FROZEN_YEARS = set(range(2005, 2025))
MEASURE_TOLERANCES = {
    # The current workbook carries precision below a cent. Tight tolerances
    # ensure a later full-precision revision is not hidden by display rounding.
    "threshold": 1e-12,
    "standard_error": 1e-12,
    "tenure_share": 1e-12,
}
SKIP_EXIT = 78


def _requests_module():
    try:
        from curl_cffi import requests as cr
    except ImportError:
        print("curl_cffi unavailable; skipping drift check.")
        return None
    return cr


def fetch_workbook(url: str) -> bytes | None:
    """Fetch one required workbook, returning ``None`` if unavailable."""
    cr = _requests_module()
    if cr is None:
        return None
    try:
        response = cr.get(url, impersonate="chrome", timeout=120)
    except Exception as error:  # noqa: BLE001
        print(f"fetch failed for {url}: {error}")
        return None
    if response.status_code == 200 and response.content[:2] == b"PK":
        print(f"fetched {url} ({len(response.content):,} bytes)")
        return response.content
    print(f"{url}: status {response.status_code}, not a workbook")
    return None


def fetch_page(url: str) -> str | None:
    """Fetch an HTML page, returning ``None`` if unavailable."""
    cr = _requests_module()
    if cr is None:
        return None
    try:
        response = cr.get(url, impersonate="chrome", timeout=120)
    except Exception as error:  # noqa: BLE001
        print(f"fetch failed for {url}: {error}")
        return None
    if response.status_code == 200:
        print(f"fetched {url} ({len(response.content):,} bytes)")
        return response.text
    print(f"{url}: status {response.status_code}, not an HTML page")
    return None


class _TableParser(HTMLParser):
    """Collect text cells from HTML tables without another dependency."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict] = []
        self._table: dict | None = None
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag == "table" and self._table is None:
            self._table = {"attrs": dict(attrs), "rows": []}
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._cell_parts = []
        elif tag == "br" and self._cell_parts is not None:
            self._cell_parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._cell_parts is not None:
            assert self._row is not None
            self._row.append(" ".join("".join(self._cell_parts).split()))
            self._cell_parts = None
        elif tag == "tr" and self._row is not None:
            assert self._table is not None
            if self._row:
                self._table["rows"].append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None


def _tenure_from_text(text: str) -> str | None:
    normalized = " ".join(text.lower().replace("-", " ").split())
    if "renter" in normalized:
        return "renter"
    if "owner" not in normalized or "mortgage" not in normalized:
        return None
    if "without" in normalized or "no mortgage" in normalized:
        return "owner_without_mortgage"
    if "with" in normalized:
        return "owner_with_mortgage"
    return None


def _number(text: str) -> float | None:
    match = re.search(r"\$?\s*(-?\d[\d,]*(?:\.\d+)?)", text)
    return float(match.group(1).replace(",", "")) if match else None


def _year_column(rows: list[list[str]], year: int) -> int | None:
    for row in rows:
        for index, cell in enumerate(row):
            lowered = cell.lower()
            if str(year) in lowered and (
                "threshold" in lowered or lowered.strip() == str(year)
            ):
                return index
    return None


def _parse_row_oriented_table(
    rows: list[list[str]], year: int
) -> dict[str, float]:
    result: dict[str, float] = {}
    year_column = _year_column(rows, year)
    for row in rows:
        tenure = next(
            (
                _tenure_from_text(cell)
                for cell in row
                if _tenure_from_text(cell)
            ),
            None,
        )
        if tenure is None:
            continue
        value = None
        if year_column is not None and year_column < len(row):
            candidate = _number(row[year_column])
            if candidate is not None and candidate >= 10_000:
                value = candidate
        if value is None:
            candidates = [
                number
                for cell in row
                if (number := _number(cell)) is not None and number >= 10_000
            ]
            if candidates:
                # In comparison tables, BLS orders the newest year last.
                value = candidates[-1]
        if value is not None:
            result[tenure] = value
    return result


def _parse_transposed_table(
    rows: list[list[str]], year: int
) -> dict[str, float]:
    for header in rows:
        tenure_columns = {
            tenure: index
            for index, cell in enumerate(header)
            if (tenure := _tenure_from_text(cell)) is not None
        }
        if set(tenure_columns) != set(TENURES.values()):
            continue
        for row in rows:
            label = " ".join(row).lower()
            if str(year) not in label or "threshold" not in label:
                continue
            values = {}
            for tenure, index in tenure_columns.items():
                if index >= len(row) or (value := _number(row[index])) is None:
                    break
                values[tenure] = value
            if set(values) == set(TENURES.values()):
                return values
    return {}


def parse_chart_1_table(html: str, year: int = 2025) -> dict[str, float]:
    """Parse whole-dollar tenure thresholds from the annual Chart 1 table.

    BLS's accessible chart markup has varied between row-oriented and
    transposed tables, so both forms are accepted. Tables explicitly labeled
    ``Chart 1`` are preferred; a tenure-complete table is a safe fallback.
    """
    parser = _TableParser()
    parser.feed(html)
    parsed: list[tuple[bool, dict[str, float]]] = []
    for table in parser.tables:
        rows = table["rows"]
        values = _parse_row_oriented_table(rows, year)
        if set(values) != set(TENURES.values()):
            values = _parse_transposed_table(rows, year)
        if set(values) != set(TENURES.values()):
            continue
        descriptor = " ".join(
            str(value)
            for value in [
                *table["attrs"].values(),
                *(cell for row in rows for cell in row),
            ]
            if value is not None
        ).lower()
        parsed.append(
            ("chart 1" in descriptor or "chart1" in descriptor, values)
        )
    if not parsed:
        raise ValueError("could not find a complete Chart 1 threshold table")
    parsed.sort(key=lambda item: item[0], reverse=True)
    return parsed[0][1]


def flatten_workbook(published: dict, revised: dict) -> dict[int, dict]:
    """Rebuild the canonical splice with all three published measures."""
    flat: dict[int, dict] = {}
    for bucket in (published, revised):
        for year_str, tenures in bucket.items():
            year = int(year_str)
            if bucket is published and year >= 2019:
                continue  # the workbook's superseded "2019 Published" column
            flat[year] = tenures
    return flat


def _packaged_series() -> dict[int, dict]:
    packaged = {}
    for year, thresholds in HISTORICAL_THRESHOLDS.items():
        standard_errors = get_standard_errors(year)
        tenure_shares = get_tenure_shares(year)
        packaged[year] = {
            tenure: {
                "threshold": threshold,
                "standard_error": standard_errors[tenure],
                "tenure_share": tenure_shares[tenure],
            }
            for tenure, threshold in thresholds.items()
        }
    return packaged


def compare_workbook(
    source: str,
    live: dict[int, dict],
    packaged: dict[int, dict],
) -> list[str]:
    """Compare every year, tenure, and measure in one workbook lane."""
    divergences: list[str] = []
    for year in sorted(set(live) | set(packaged)):
        if year not in packaged:
            divergences.append(
                f"{source} {year}: BLS publishes this year; package lacks it "
                f"(new release? run scripts/build_threshold_series.py)"
            )
            continue
        if year not in live:
            divergences.append(
                f"{source} {year}: packaged but absent from the live workbook"
            )
            continue
        for tenure in sorted(set(live[year]) | set(packaged[year])):
            if tenure not in packaged[year] or tenure not in live[year]:
                divergences.append(
                    f"{source} {year} {tenure}: tenure missing from one source"
                )
                continue
            for measure, tolerance in MEASURE_TOLERANCES.items():
                live_value = live[year][tenure].get(measure)
                packaged_value = packaged[year][tenure].get(measure)
                if (
                    live_value is None
                    or packaged_value is None
                    or abs(live_value - packaged_value) > tolerance
                ):
                    divergences.append(
                        f"{source} {year} {tenure} {measure}: packaged "
                        f"{packaged_value} != live {live_value}"
                    )
    return divergences


def compare_page_2025(html: str) -> list[str]:
    """Compare BLS's rounded Chart 1 values with packaged 2025 values."""
    try:
        live = parse_chart_1_table(html)
    except ValueError as error:
        return [f"2025 page Chart 1: {error}"]
    packaged = get_thresholds(2025, allow_forecast=False)
    divergences = []
    for tenure in sorted(set(live) | set(packaged)):
        live_value = live.get(tenure)
        packaged_value = packaged.get(tenure)
        packaged_rounded = (
            round(packaged_value) if packaged_value is not None else None
        )
        if live_value != packaged_rounded:
            divergences.append(
                f"2025 page Chart 1 {tenure}: packaged rounded "
                f"{packaged_rounded} != live {live_value}"
            )
    return divergences


def check_page_vintage(
    latest_year: int, page_html: str | None = None
) -> list[str]:
    """Warn when an annual BLS page serves superseded threshold values.

    The pre-correction series ends in 2024. Years it does not contain are
    skipped rather than fabricated by forecasting.
    """
    try:
        superseded = get_thresholds(
            latest_year,
            allow_forecast=False,
            series="census-published-pre-correction",
        )
    except ValueError:
        return []

    url = f"https://www.bls.gov/pir/spm/spm_thresholds_{latest_year}.htm"
    if page_html is None:
        page_html = fetch_page(url)
    if page_html is None:
        return []
    stale = [
        f"{tenure} ${value:,.0f}"
        for tenure, value in superseded.items()
        if f"{value:,.0f}" in page_html
    ]
    if not stale:
        return []
    return [
        f"WARNING: {url} displays pre-correction {latest_year} values "
        f"({'; '.join(stale)}) — superseded by the corrected workbook"
    ]


def _parse_workbook_bytes(content: bytes) -> dict[int, dict]:
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as temporary:
        temporary.write(content)
        temporary.flush()
        published, revised = parse_workbook(Path(temporary.name))
    return flatten_workbook(published, revised)


def main() -> int:
    frozen_content = fetch_workbook(FROZEN_WORKBOOK_URL)
    current_content = fetch_workbook(CURRENT_WORKBOOK_URL)
    chart_1_2025 = fetch_page(CHART_1_2025_URL)
    if (
        frozen_content is None
        or current_content is None
        or chart_1_2025 is None
    ):
        print("BLS unreachable or blocked; treating as neutral skip.")
        return SKIP_EXIT

    frozen_live = _parse_workbook_bytes(frozen_content)
    current_live = _parse_workbook_bytes(current_content)
    packaged = _packaged_series()

    divergences = compare_workbook(
        "frozen corrected workbook",
        frozen_live,
        {year: packaged[year] for year in FROZEN_YEARS},
    )
    divergences.extend(
        compare_workbook("current workbook", current_live, packaged)
    )
    divergences.extend(compare_page_2025(chart_1_2025))

    if divergences:
        print("DRIFT DETECTED between packaged series and bls.gov:")
        for line in divergences:
            print(f"  - {line}")
        return 1

    # Preserve the existing warning for BLS's stale 2024 annual page.
    for warning in check_page_vintage(max(frozen_live)):
        print(warning)

    print(
        "No drift: frozen corrected workbook, current workbook, and "
        "2025 Chart 1 match the packaged thresholds, standard errors, "
        "and tenure shares."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
