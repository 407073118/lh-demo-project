"""基于 OHLCV 行情计算的基础本地因子。"""

from __future__ import annotations

import pandas as pd


def return_factor(bars: pd.DataFrame, window: int) -> pd.Series:
    """计算指定窗口的收盘价收益率。"""

    close = pd.to_numeric(bars["close"], errors="coerce")
    return close.pct_change(window)


def volatility_factor(bars: pd.DataFrame, window: int) -> pd.Series:
    """计算指定窗口的收益率波动率。"""

    close = pd.to_numeric(bars["close"], errors="coerce")
    return close.pct_change().rolling(window).std()


def moving_average_factor(bars: pd.DataFrame, window: int) -> pd.Series:
    """计算指定窗口的简单移动平均价。"""

    close = pd.to_numeric(bars["close"], errors="coerce")
    return close.rolling(window).mean()


def exponential_moving_average_factor(bars: pd.DataFrame, window: int) -> pd.Series:
    """计算指定窗口的指数移动平均价。"""

    close = pd.to_numeric(bars["close"], errors="coerce")
    return close.ewm(span=window, adjust=False).mean()


def rsi_factor(bars: pd.DataFrame, window: int) -> pd.Series:
    """计算指定窗口的 RSI 相对强弱指标。"""

    close = pd.to_numeric(bars["close"], errors="coerce")
    delta = close.diff()
    gains = delta.clip(lower=0).rolling(window).mean()
    losses = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gains / losses.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def volume_average_factor(bars: pd.DataFrame, window: int) -> pd.Series:
    """计算指定窗口的成交量均值。"""

    volume = pd.to_numeric(bars["volume"], errors="coerce")
    return volume.rolling(window).mean()
