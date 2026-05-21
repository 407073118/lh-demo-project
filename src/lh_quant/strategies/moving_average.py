"""移动平均线交叉策略。"""

from __future__ import annotations

import pandas as pd


def moving_average_cross_signals(
    bars: pd.DataFrame,
    fast_window: int,
    slow_window: int,
    price_column: str = "close",
) -> pd.Series:
    """根据快慢均线交叉生成交易信号。

    当快均线从下向上穿过慢均线时返回 1，表示买入信号；当快均线从上向下跌破慢均线时返回 -1，
    表示卖出信号；其他时间返回 0，表示不操作。函数只使用当前及历史数据，不向未来看。
    """

    if fast_window <= 0 or slow_window <= 0:
        raise ValueError("均线窗口必须大于 0")
    if fast_window >= slow_window:
        raise ValueError("短均线窗口必须小于长均线窗口")
    if price_column not in bars.columns:
        raise ValueError(f"缺少价格字段: {price_column}")

    close = bars[price_column].astype(float)
    fast = close.rolling(fast_window).mean()
    slow = close.rolling(slow_window).mean()

    cross_up = (fast > slow) & (fast.shift(1) <= slow.shift(1))
    cross_down = (fast < slow) & (fast.shift(1) >= slow.shift(1))

    signals = pd.Series(0, index=bars.index, name="signal")
    signals.loc[cross_up.fillna(False)] = 1
    signals.loc[cross_down.fillna(False)] = -1
    return signals
