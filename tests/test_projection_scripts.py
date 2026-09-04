"""Golden and input-selection tests for threshold projection scripts."""

from scripts import backtest_threshold_projection, compute_nowcast_2025


def test_nowcast_uses_tracked_cpi_store_by_default():
    store, path = compute_nowcast_2025.load_cpi_store()

    assert path == compute_nowcast_2025.TRACKED_CPI_STORE
    assert "CUUR0000SEEE" not in store


def test_backtest_uses_tracked_cpi_store_by_default():
    _, store = backtest_threshold_projection.load_inputs()

    assert "CUUR0000SEEE" not in store
    assert "CUUR0000SAF11" in store  # only the tracked store carries this


def test_benchmark_cpi_store_requires_explicit_opt_in():
    _, nowcast_path = compute_nowcast_2025.load_cpi_store(
        use_benchmark_store=True
    )
    _, backtest_store = backtest_threshold_projection.load_inputs(
        use_benchmark_store=True
    )

    assert nowcast_path == compute_nowcast_2025.BENCHMARK_CPI_STORE
    assert "CUUR0000SAF11" not in backtest_store
