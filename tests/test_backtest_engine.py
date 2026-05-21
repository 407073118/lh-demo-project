import pandas as pd
import pytest

from lh_quant.backtest.engine import run_signal_backtest


def test_run_signal_backtest_buys_sells_and_reports_metrics() -> None:
    bars = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=4, freq="D"),
            "close": [10.0, 12.0, 15.0, 13.0],
        }
    )
    signals = pd.Series([1, 0, -1, 0], index=bars.index)

    result = run_signal_backtest(bars, signals, cash=1000.0, commission_rate=0.0)

    assert len(result.trades) == 2
    assert result.metrics["total_return"] == 0.5
    assert result.metrics["trade_count"] == 2
    assert result.equity_curve["equity"].iloc[-1] == 1500.0


def test_run_signal_backtest_keeps_cash_when_there_are_no_signals() -> None:
    bars = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=3, freq="D"),
            "close": [10.0, 11.0, 12.0],
        }
    )
    signals = pd.Series([0, 0, 0], index=bars.index)

    result = run_signal_backtest(bars, signals, cash=1000.0)

    assert result.metrics["total_return"] == 0.0
    assert result.metrics["trade_count"] == 0
    assert result.equity_curve["equity"].tolist() == [1000.0, 1000.0, 1000.0]


def test_run_signal_backtest_rejects_multiple_symbols() -> None:
    bars = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "datetime": pd.date_range("2024-01-01", periods=2, freq="D"),
            "close": [10.0, 100.0],
        }
    )
    signals = pd.Series([1, -1], index=bars.index)

    with pytest.raises(ValueError, match="只能包含一个标的"):
        run_signal_backtest(bars, signals)


def test_run_signal_backtest_rejects_non_positive_close_prices() -> None:
    bars = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=2, freq="D"),
            "close": [10.0, 0.0],
        }
    )
    signals = pd.Series([1, -1], index=bars.index)

    with pytest.raises(ValueError, match="收盘价必须大于 0"):
        run_signal_backtest(bars, signals)


def test_run_signal_backtest_rejects_non_finite_close_prices() -> None:
    bars = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=2, freq="D"),
            "close": [10.0, float("inf")],
        }
    )
    signals = pd.Series([1, -1], index=bars.index)

    with pytest.raises(ValueError, match="有限数字"):
        run_signal_backtest(bars, signals)


def test_run_signal_backtest_rejects_commission_rate_that_consumes_cash() -> None:
    bars = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=2, freq="D"),
            "close": [10.0, 11.0],
        }
    )
    signals = pd.Series([1, -1], index=bars.index)

    with pytest.raises(ValueError, match="less than 1"):
        run_signal_backtest(bars, signals, commission_rate=1.0)


def test_run_signal_backtest_rejects_invalid_signal_values() -> None:
    bars = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=3, freq="D"),
            "close": [10.0, 11.0, 12.0],
        }
    )
    signals = pd.Series([2, 0, -2], index=bars.index)

    with pytest.raises(ValueError, match="交易信号"):
        run_signal_backtest(bars, signals)


def test_run_signal_backtest_rejects_misaligned_signal_index() -> None:
    bars = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=2, freq="D"),
            "close": [10.0, 11.0],
        },
        index=[10, 11],
    )
    signals = pd.Series([1, -1], index=[0, 1])

    with pytest.raises(ValueError, match="索引必须一致"):
        run_signal_backtest(bars, signals)


def test_run_signal_backtest_rejects_empty_inputs() -> None:
    bars = pd.DataFrame({"datetime": [], "close": []})
    signals = pd.Series([], dtype=int)

    with pytest.raises(ValueError, match="至少需要一行K线数据"):
        run_signal_backtest(bars, signals)
