"""Tests for the multi-source BLS threshold drift check."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts import check_bls_drift as drift

PAGE_TABLE = """
<h2>Research Supplemental Poverty Measure (in dollars), 2025</h2>
<table>
  <tr><th>Measure</th><th>Threshold Amount</th></tr>
  <tr><td>Official</td><td>32,649</td></tr>
  <tr><td>SPM Owners with mortgages</td><td>41,323</td></tr>
  <tr><td>SPM Owners without mortgages</td><td>34,326</td></tr>
  <tr><td>SPM Renters</td><td>41,701</td></tr>
</table>
"""


def _one_year() -> dict[int, dict]:
    return {
        2025: {
            "owner_with_mortgage": {
                "threshold": 41322.707394,
                "standard_error": 327.35414802,
                "tenure_share": 0.51035789503,
            },
            "owner_without_mortgage": {
                "threshold": 34325.99772,
                "standard_error": 560.28664871,
                "tenure_share": 0.10217639667,
            },
            "renter": {
                "threshold": 41700.555713,
                "standard_error": 393.03526083,
                "tenure_share": 0.3874657083,
            },
        }
    }


class TestChartOne:
    def test_parses_row_oriented_accessible_table(self):
        assert drift.parse_chart_1_table(PAGE_TABLE) == {
            "owner_with_mortgage": 41323,
            "owner_without_mortgage": 34326,
            "renter": 41701,
        }

    def test_parses_transposed_accessible_table(self):
        html = """
        <table id="chart1-data">
          <tr>
            <th>Measure</th><th>Owners with mortgages</th>
            <th>Owners without mortgages</th><th>Renters</th>
          </tr>
          <tr><th>2025 SPM threshold</th><td>41,323</td>
            <td>34,326</td><td>41,701</td></tr>
        </table>
        """
        assert drift.parse_chart_1_table(html) == {
            "owner_with_mortgage": 41323,
            "owner_without_mortgage": 34326,
            "renter": 41701,
        }

    def test_page_values_match_full_precision_values_after_rounding(self):
        assert drift.compare_page_2025(PAGE_TABLE) == []

    def test_page_revision_is_drift(self):
        changed = PAGE_TABLE.replace(">41,701<", ">41,702<")
        messages = drift.compare_page_2025(changed)
        assert len(messages) == 1
        assert "renter" in messages[0]
        assert "41701 != live 41702" in messages[0]

    def test_missing_table_is_drift_not_a_silent_pass(self):
        assert "could not find" in drift.compare_page_2025("<p>changed</p>")[0]


class TestWorkbookMeasures:
    @pytest.mark.parametrize(
        "measure,change",
        [
            ("threshold", 0.000001),
            ("standard_error", 0.000001),
            ("tenure_share", 0.0000000001),
        ],
    )
    def test_full_precision_drift_in_every_measure_is_detected(
        self, measure, change
    ):
        packaged = _one_year()
        live = deepcopy(packaged)
        live[2025]["renter"][measure] += change
        messages = drift.compare_workbook("current workbook", live, packaged)
        assert len(messages) == 1
        assert measure in messages[0]

    def test_exact_thresholds_standard_errors_and_shares_match(self):
        values = _one_year()
        assert drift.compare_workbook("current workbook", values, values) == []

    def test_new_current_workbook_year_is_detected(self):
        packaged = _one_year()
        live = deepcopy(packaged)
        live[2026] = deepcopy(live[2025])
        messages = drift.compare_workbook("current workbook", live, packaged)
        assert any(
            "2026" in message and "package lacks" in message
            for message in messages
        )


class TestPageVintage:
    def test_does_not_forecast_an_unavailable_pre_correction_year(
        self, monkeypatch
    ):
        calls = []

        def unavailable(year, **kwargs):
            calls.append((year, kwargs))
            raise ValueError("not published in this series")

        monkeypatch.setattr(drift, "get_published_thresholds", unavailable)
        assert drift.check_page_vintage(2025, page_html=PAGE_TABLE) == []
        assert calls == [
            (
                2025,
                {
                    "series": "census-published-pre-correction",
                },
            )
        ]

    def test_preserves_stale_page_warning(self):
        html = "<p>39,068; 32,586; 39,430</p>"
        warnings = drift.check_page_vintage(2024, page_html=html)
        assert len(warnings) == 1
        assert "pre-correction 2024 values" in warnings[0]


def test_main_checks_frozen_current_and_page(monkeypatch, capsys):
    data = Path("spm_calculator/data/bls")
    workbooks = {
        drift.FROZEN_WORKBOOK_URL: (
            data / "spm_threshold_200524_corrected.xlsx"
        ).read_bytes(),
        drift.CURRENT_WORKBOOK_URL: (
            data / "spm_thresholds.xlsx"
        ).read_bytes(),
    }
    fetched = []

    def fetch_workbook(url):
        fetched.append(url)
        return workbooks[url]

    monkeypatch.setattr(drift, "fetch_workbook", fetch_workbook)
    fetched_pages = []

    def fetch_page(url):
        fetched_pages.append(url)
        return PAGE_TABLE

    monkeypatch.setattr(drift, "fetch_page", fetch_page)
    monkeypatch.setattr(drift, "check_page_vintage", lambda year: [])

    assert drift.main() == 0
    assert fetched == [drift.FROZEN_WORKBOOK_URL, drift.CURRENT_WORKBOOK_URL]
    assert fetched_pages == [drift.CHART_1_2025_URL]
    output = capsys.readouterr().out
    assert "frozen corrected workbook, current workbook" in output
    assert "2025 Chart 1" in output
