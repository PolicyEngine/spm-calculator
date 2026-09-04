"""Golden and input-selection tests for threshold projection scripts."""

import json

import pytest

from scripts import backtest_threshold_projection, compute_nowcast_2025


def test_nowcast_uses_tracked_cpi_store_by_default():
    store, path = compute_nowcast_2025.load_cpi_store()

    assert path == compute_nowcast_2025.TRACKED_CPI_STORE
    assert "CUUR0000SEEE" not in store


def test_backtest_uses_tracked_cpi_store_by_default():
    store, path = backtest_threshold_projection.load_cpi_store()

    assert path == backtest_threshold_projection.TRACKED_CPI_STORE
    assert "CUUR0000SEEE" not in store
    assert "CUUR0000SAF11" in store  # only the tracked store carries this


def test_benchmark_cpi_store_requires_explicit_opt_in(monkeypatch, tmp_path):
    benchmark_path = tmp_path / "bls_cpi_series.json"
    benchmark_path.write_text(json.dumps({"CUUR0000SA0": {"2024": 1}}))
    monkeypatch.setattr(
        compute_nowcast_2025, "BENCHMARK_CPI_STORE", benchmark_path
    )
    monkeypatch.setattr(
        backtest_threshold_projection,
        "BENCHMARK_CPI_STORE",
        benchmark_path,
    )

    _, nowcast_path = compute_nowcast_2025.load_cpi_store(
        use_benchmark_store=True
    )
    backtest_store, backtest_path = (
        backtest_threshold_projection.load_cpi_store(use_benchmark_store=True)
    )

    assert nowcast_path == benchmark_path
    assert backtest_path == benchmark_path
    assert "CUUR0000SAF11" not in backtest_store


def _backtest_artifact():
    return json.loads(
        backtest_threshold_projection.TRACKED_RESULTS.read_text()
    )


def test_backtest_golden_mean_absolute_errors():
    """Pin all four 2020-2024 backtest MAEs in percentage points."""
    summary = _backtest_artifact()["summary"]
    expected = {
        "cpi_u": 2.2286,
        "fcsuti_cpi": 1.5688,
        "replication_ratio": 0.4110,
        "blend": 0.7567,
    }

    assert set(summary) == set(expected)
    for rule, expected_percent in expected.items():
        assert summary[rule]["mean_absolute_error_percent"] == pytest.approx(
            expected_percent, abs=1e-4
        )


def test_tracked_backtest_matches_executable_rules():
    """Recalculate the artifact without the git-ignored benchmark input."""
    artifact = _backtest_artifact()
    replicated = {
        int(year): values
        for year, values in artifact["provenance"]["replication"][
            "selected_thresholds"
        ].items()
    }
    cpi, _ = backtest_threshold_projection.load_cpi_store()

    rows, summary = backtest_threshold_projection.calculate_backtest(
        replicated, cpi
    )

    assert rows == artifact["annual_results"]
    assert summary == artifact["summary"]
    assert {row["rule"] for row in rows} == {
        "cpi_u",
        "fcsuti_cpi",
        "replication_ratio",
        "blend",
    }


def test_backtest_artifact_carries_input_provenance():
    provenance = _backtest_artifact()["provenance"]

    assert provenance["thresholds"]["series"] == ("bls-corrected-2026-07-17")
    assert provenance["cpi"]["path"] == (
        "spm_calculator/data/bls/cpi_annual.json"
    )
    assert provenance["replication"]["selection"] == {
        "mortgage_principal": "include",
        "annualization": "quarter4",
        "anchor_percent": 82,
    }
