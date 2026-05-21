"""RSI 均值回归策略。"""

from __future__ import annotations

import pandas as pd


def rsi_reversion_signals(
    bars: pd.DataFrame,
    rsi_window: int,
    oversold: float,
    overbought: float,
    price_column: str = "close",
) -> pd.Series:
    """根据 RSI 超跌修复和过热信号生成买卖点。

    RSI 从下向上穿过超卖阈值时买入，向上穿过过热阈值时卖出。这个规则避免在
    RSI 持续低位时反复买入，也更适合当前只接收离散买卖信号的回测引擎。
    """

    if rsi_window <= 1:
        raise ValueError("RSI 周期必须大于 1")
    if not 0 < oversold < overbought < 100:
        raise ValueError("RSI 阈值必须满足 0 < 超卖阈值 < 过热阈值 < 100")
    if price_column not in bars.columns:
        raise ValueError(f"缺少价格字段: {price_column}")

    rsi = calculate_rsi(bars[price_column].astype(float), rsi_window)
    buy = (rsi > oversold) & (rsi.shift(1) <= oversold)
    sell = (rsi > overbought) & (rsi.shift(1) <= overbought)

    signals = pd.Series(0, index=bars.index, name="signal")
    signals.loc[buy.fillna(False)] = 1
    signals.loc[sell.fillna(False)] = -1
    return signals


def calculate_rsi(close: pd.Series, window: int) -> pd.Series:
    """计算 RSI 指标，并处理单边上涨、单边下跌和平盘场景。"""

    if window <= 1:
        raise ValueError("RSI 周期必须大于 1")

    delta = close.astype(float).diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - 100 / (1 + rs)
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100)
    rsi = rsi.mask((avg_gain == 0) & (avg_loss > 0), 0)
    rsi = rsi.mask((avg_gain == 0) & (avg_loss == 0), 50)
    return rsi.fillna(50)
