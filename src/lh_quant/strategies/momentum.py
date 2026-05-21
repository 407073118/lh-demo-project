"""价格动量突破策略。"""

from __future__ import annotations

import pandas as pd


def momentum_breakout_signals(
    bars: pd.DataFrame,
    lookback_window: int,
    exit_window: int,
    price_column: str = "close",
) -> pd.Series:
    """根据 N 日收盘突破和退出通道生成买卖信号。

    买入条件使用昨日以前的 `lookback_window` 日最高收盘价，卖出条件使用昨日以前的
    `exit_window` 日最低收盘价。阈值都通过 `shift(1)` 排除当天数据，避免未来函数。
    """

    if lookback_window <= 0 or exit_window <= 0:
        raise ValueError("突破和退出窗口必须大于 0")
    if price_column not in bars.columns:
        raise ValueError(f"缺少价格字段: {price_column}")

    close = bars[price_column].astype(float)
    breakout_line = momentum_breakout_entry_line(bars, lookback_window, price_column)
    exit_line = momentum_breakout_exit_line(bars, exit_window, price_column)

    buy = close > breakout_line
    sell = close < exit_line
    signals = pd.Series(0, index=bars.index, name="signal")
    signals.loc[buy.fillna(False)] = 1
    signals.loc[sell.fillna(False)] = -1
    return signals


def momentum_breakout_entry_line(
    bars: pd.DataFrame,
    lookback_window: int,
    price_column: str = "close",
) -> pd.Series:
    """计算突破买入上轨，使用昨日以前的滚动最高收盘价。"""

    if lookback_window <= 0:
        raise ValueError("突破窗口必须大于 0")
    if price_column not in bars.columns:
        raise ValueError(f"缺少价格字段: {price_column}")
    return bars[price_column].astype(float).shift(1).rolling(lookback_window).max()


def momentum_breakout_exit_line(
    bars: pd.DataFrame,
    exit_window: int,
    price_column: str = "close",
) -> pd.Series:
    """计算突破策略的退出下轨，使用昨日以前的滚动最低收盘价。"""

    if exit_window <= 0:
        raise ValueError("退出窗口必须大于 0")
    if price_column not in bars.columns:
        raise ValueError(f"缺少价格字段: {price_column}")
    return bars[price_column].astype(float).shift(1).rolling(exit_window).min()
