"""用于单元测试和开发演示的可复现K线数据生成器。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from lh_quant.data.schema import validate_bars


def generate_sample_bars(
    symbol: str = "DEMO",
    periods: int = 120,
    seed: int = 42,
    start: str = "2024-01-01",
) -> pd.DataFrame:
    """生成可复现的日线 OHLCV 样例数据。

    这个函数只用于低层单元测试和开发演示，不代表真实市场行情。参与端到端流程时应先写入
    隔离数据库，再从数据库读取回测，避免绕过数据事实源。
    """

    if periods <= 0:
        raise ValueError("生成周期数必须大于 0")

    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.0008, scale=0.018, size=periods)
    close = 100.0 * np.cumprod(1.0 + returns)
    open_ = np.r_[100.0, close[:-1]]
    spread = np.abs(rng.normal(loc=0.01, scale=0.004, size=periods))
    high = np.maximum(open_, close) * (1.0 + spread)
    low = np.minimum(open_, close) * (1.0 - spread)
    volume = rng.integers(80_000, 180_000, size=periods)

    bars = pd.DataFrame(
        {
            "symbol": symbol,
            "datetime": pd.bdate_range(start=start, periods=periods),
            "open": np.round(open_, 2),
            "high": np.round(high, 2),
            "low": np.round(low, 2),
            "close": np.round(close, 2),
            "volume": volume,
        }
    )
    return validate_bars(bars)
