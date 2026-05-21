"""不绑定具体回测框架的策略函数。"""

from lh_quant.strategies.momentum import momentum_breakout_signals
from lh_quant.strategies.moving_average import moving_average_cross_signals
from lh_quant.strategies.registry import (
    build_strategy_overlays,
    generate_strategy_signals,
    get_strategy_specs,
    normalize_strategy_params,
)
from lh_quant.strategies.rsi import rsi_reversion_signals

__all__ = [
    "build_strategy_overlays",
    "generate_strategy_signals",
    "get_strategy_specs",
    "momentum_breakout_signals",
    "moving_average_cross_signals",
    "normalize_strategy_params",
    "rsi_reversion_signals",
]
