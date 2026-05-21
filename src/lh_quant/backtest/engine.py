"""最小可用的单标的信号回测引擎。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from lh_quant.backtest.metrics import calculate_backtest_metrics


@dataclass(frozen=True)
class BacktestResult:
    """回测结果对象，包含权益曲线、成交记录和汇总指标。"""

    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    metrics: dict[str, float | int | None]


def run_signal_backtest(
    bars: pd.DataFrame,
    signals: pd.Series,
    cash: float = 100_000.0,
    commission_rate: float = 0.001,
) -> BacktestResult:
    """按收盘价执行信号，运行一个简化的单标的做多回测。

    参数：
    - bars：K线数据，至少需要包含 `close` 列；如果包含 `symbol`，只能有一个标的。
    - signals：与 bars 索引完全一致的信号序列，1 表示买入，-1 表示卖出，0 表示不操作。
    - cash：初始资金。
    - commission_rate：单边交易手续费率，例如 0.001 表示千分之一。

    返回：
    - BacktestResult，里面有每日权益曲线、买卖成交明细和总收益率等指标。
    """

    if bars.empty:
        raise ValueError("回测至少需要一行K线数据")
    if "close" not in bars.columns:
        raise ValueError("K线数据必须包含 close 收盘价字段")
    if len(bars) != len(signals):
        raise ValueError("K线数据和信号序列长度必须一致")
    if not bars.index.equals(signals.index):
        raise ValueError("K线数据和信号序列的索引必须一致")
    if "symbol" in bars.columns and bars["symbol"].nunique(dropna=False) != 1:
        raise ValueError("当前信号回测只能包含一个标的")
    if cash <= 0:
        raise ValueError("初始资金必须大于 0")
    if commission_rate < 0:
        raise ValueError("手续费率不能为负数")

    if commission_rate >= 1:
        raise ValueError("commission_rate must be less than 1")

    bars = bars.copy()
    bars["close"] = pd.to_numeric(bars["close"], errors="coerce")
    if bars["close"].isna().any():
        raise ValueError("收盘价必须是数字")
    if not np.isfinite(bars["close"]).all():
        raise ValueError("收盘价必须是有限数字")
    if (bars["close"] <= 0).any():
        raise ValueError("收盘价必须大于 0")

    normalized_signals = pd.to_numeric(signals, errors="coerce")
    if normalized_signals.isna().any() or not np.isfinite(normalized_signals).all():
        raise ValueError("交易信号必须是 -1、0 或 1")
    if not normalized_signals.isin([-1, 0, 1]).all():
        raise ValueError("交易信号必须是 -1、0 或 1")

    cash_balance = float(cash)
    position = 0.0
    equity_rows: list[dict[str, float | pd.Timestamp | int]] = []
    trade_rows: list[dict[str, float | pd.Timestamp | str]] = []

    timestamps = (
        bars["datetime"] if "datetime" in bars.columns else bars.index.to_series(index=bars.index)
    )

    for index, row in bars.iterrows():
        price = float(row["close"])
        signal = int(normalized_signals.loc[index])
        timestamp = timestamps.loc[index]

        if signal == 1 and position == 0:
            commission = cash_balance * commission_rate
            quantity = (cash_balance - commission) / price
            cash_balance = 0.0
            position = quantity
            trade_rows.append(
                {
                    "datetime": timestamp,
                    "side": "buy",
                    "price": price,
                    "quantity": quantity,
                    "commission": commission,
                }
            )
        elif signal == -1 and position > 0:
            proceeds = position * price
            commission = proceeds * commission_rate
            cash_balance = proceeds - commission
            trade_rows.append(
                {
                    "datetime": timestamp,
                    "side": "sell",
                    "price": price,
                    "quantity": position,
                    "commission": commission,
                }
            )
            position = 0.0

        equity = cash_balance + position * price
        equity_rows.append(
            {
                "datetime": timestamp,
                "cash": cash_balance,
                "position": position,
                "price": price,
                "equity": equity,
            }
        )

    equity_curve = pd.DataFrame(equity_rows)
    trades = pd.DataFrame(
        trade_rows,
        columns=["datetime", "side", "price", "quantity", "commission"],
    )
    metrics = calculate_backtest_metrics(equity_curve, trades, starting_cash=cash)
    return BacktestResult(equity_curve=equity_curve, trades=trades, metrics=metrics)
