"""供 API 和策略模板复用的本地因子注册表。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from lh_quant.factors.basic import (
    exponential_moving_average_factor,
    moving_average_factor,
    return_factor,
    rsi_factor,
    volatility_factor,
    volume_average_factor,
)

FactorDirection = Literal["positive", "negative", "neutral"]
FactorCalculator = Callable[[pd.DataFrame], pd.Series]


@dataclass(frozen=True)
class FactorDefinition:
    """描述一个可展示、可计算的因子定义。"""

    id: str
    name: str
    category: str
    frequency: str
    direction: FactorDirection
    description: str
    source: str
    license: str
    formula: str
    calculator: FactorCalculator

    def to_json(self) -> dict[str, Any]:
        """转换为前端可直接消费的因子规格。"""

        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "frequency": self.frequency,
            "direction": self.direction,
            "description": self.description,
            "source": self.source,
            "license": self.license,
            "formula": self.formula,
            "status": "available",
        }


def get_factor_specs() -> list[dict[str, Any]]:
    """返回所有本地因子的展示规格。"""

    return [definition.to_json() for definition in _FACTORS.values()]


def calculate_factor(factor_id: str, bars: pd.DataFrame) -> pd.Series:
    """按因子 ID 计算与行情索引对齐的因子值。"""

    try:
        definition = _FACTORS[factor_id]
    except KeyError as error:
        raise ValueError(f"Unknown factor: {factor_id}") from error
    values = definition.calculator(bars)
    values.name = definition.id
    return values


_FACTORS: dict[str, FactorDefinition] = {
    "return_5d": FactorDefinition(
        id="return_5d",
        name="5 day return",
        category="return",
        frequency="1d",
        direction="positive",
        description="Trailing 5 trading day close-to-close return.",
        source="local",
        license="internal",
        formula="close / close.shift(5) - 1",
        calculator=lambda bars: return_factor(bars, 5),
    ),
    "return_20d": FactorDefinition(
        id="return_20d",
        name="20 day return",
        category="return",
        frequency="1d",
        direction="positive",
        description="Trailing 20 trading day close-to-close return.",
        source="local",
        license="internal",
        formula="close / close.shift(20) - 1",
        calculator=lambda bars: return_factor(bars, 20),
    ),
    "volatility_20d": FactorDefinition(
        id="volatility_20d",
        name="20 day volatility",
        category="risk",
        frequency="1d",
        direction="negative",
        description="Rolling 20 trading day standard deviation of daily returns.",
        source="local",
        license="internal",
        formula="std(pct_change(close), 20)",
        calculator=lambda bars: volatility_factor(bars, 20),
    ),
    "ma_20d": FactorDefinition(
        id="ma_20d",
        name="20 day moving average",
        category="trend",
        frequency="1d",
        direction="neutral",
        description="20 trading day simple moving average of close.",
        source="local",
        license="internal",
        formula="mean(close, 20)",
        calculator=lambda bars: moving_average_factor(bars, 20),
    ),
    "ema_20d": FactorDefinition(
        id="ema_20d",
        name="20 day EMA",
        category="trend",
        frequency="1d",
        direction="neutral",
        description="20 trading day exponential moving average of close.",
        source="local",
        license="internal",
        formula="ewm(close, span=20)",
        calculator=lambda bars: exponential_moving_average_factor(bars, 20),
    ),
    "rsi_14d": FactorDefinition(
        id="rsi_14d",
        name="14 day RSI",
        category="reversion",
        frequency="1d",
        direction="neutral",
        description="Relative strength index over 14 trading days.",
        source="local",
        license="internal",
        formula="100 - 100 / (1 + avg_gain(14) / avg_loss(14))",
        calculator=lambda bars: rsi_factor(bars, 14),
    ),
    "volume_ma_20d": FactorDefinition(
        id="volume_ma_20d",
        name="20 day volume average",
        category="liquidity",
        frequency="1d",
        direction="positive",
        description="20 trading day average volume.",
        source="local",
        license="internal",
        formula="mean(volume, 20)",
        calculator=lambda bars: volume_average_factor(bars, 20),
    ),
}
