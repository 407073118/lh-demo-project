import pandas as pd
import pytest

from lh_quant.backtest.metrics import calculate_backtest_metrics


def test_calculate_backtest_metrics_includes_risk_trade_exposure_and_turnover() -> None:
    equity_curve = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=5, freq="B"),
            "cash": [100_000, 0, 0, 105_000, 105_000],
            "position": [0, 1_000, 1_000, 0, 0],
            "price": [100, 100, 103, 105, 105],
            "equity": [100_000, 100_000, 103_000, 105_000, 105_000],
        }
    )
    trades = pd.DataFrame(
        {
            "datetime": [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-04")],
            "side": ["buy", "sell"],
            "price": [100.0, 105.0],
            "quantity": [1_000.0, 1_000.0],
            "commission": [100.0, 105.0],
        }
    )

    metrics = calculate_backtest_metrics(
        equity_curve=equity_curve,
        trades=trades,
        starting_cash=100_000,
    )

    assert metrics["starting_cash"] == 100_000
    assert metrics["final_equity"] == 105_000
    assert metrics["total_return"] == 0.05
    assert metrics["max_drawdown"] == 0
    assert metrics["trade_count"] == 2
    assert metrics["closed_trade_count"] == 1
    assert metrics["win_rate"] == 1.0
    assert metrics["profit_factor"] is None
    assert metrics["expectancy"] == 4795.0
    assert metrics["total_commission"] == 205.0
    assert metrics["turnover"] > 1.9
    assert metrics["exposure"] == 0.4
    assert metrics["calmar_ratio"] is None


def test_calculate_backtest_metrics_handles_losing_round_trip() -> None:
    equity_curve = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=4, freq="B"),
            "cash": [100_000, 0, 95_000, 95_000],
            "position": [0, 1_000, 0, 0],
            "price": [100, 100, 95, 95],
            "equity": [100_000, 100_000, 95_000, 95_000],
        }
    )
    trades = pd.DataFrame(
        {
            "datetime": [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")],
            "side": ["buy", "sell"],
            "price": [100.0, 95.0],
            "quantity": [1_000.0, 1_000.0],
            "commission": [100.0, 95.0],
        }
    )

    metrics = calculate_backtest_metrics(equity_curve, trades, starting_cash=100_000)

    assert metrics["total_return"] == -0.05
    assert metrics["max_drawdown"] == -0.05
    assert metrics["closed_trade_count"] == 1
    assert metrics["win_rate"] == 0.0
    assert metrics["profit_factor"] == 0.0
    assert metrics["expectancy"] == -5195.0


def test_calculate_backtest_metrics_annualizes_by_return_periods() -> None:
    equity_curve = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=3, freq="B"),
            "cash": [100_000, 100_000, 110_000],
            "position": [0, 0, 0],
            "price": [100, 100, 110],
            "equity": [100_000, 100_000, 110_000],
        }
    )
    trades = pd.DataFrame(columns=["datetime", "side", "price", "quantity", "commission"])

    metrics = calculate_backtest_metrics(equity_curve, trades, starting_cash=100_000)

    expected = (1.10 ** (252 / 2)) - 1.0
    assert metrics["annualized_return"] == pytest.approx(round(expected, 6))
