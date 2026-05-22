"""策略注册中心。

这个模块把“策略展示给前端的元数据”和“后端实际执行策略信号”的入口放在一起。
后续新增策略时，只需要在这里登记参数、校验规则、信号函数和图表叠加线，API 与前端就能复用同一套配置。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, Literal

import pandas as pd

from lh_quant.strategies.momentum import (
    momentum_breakout_entry_line,
    momentum_breakout_exit_line,
    momentum_breakout_signals,
)
from lh_quant.strategies.moving_average import moving_average_cross_signals
from lh_quant.strategies.rsi import rsi_reversion_signals

ParamValueType = Literal["int", "float", "bool", "enum", "factor", "universe"]
StrategyParamValue = int | float | bool | str
StrategyParams = dict[str, StrategyParamValue]
SignalBuilder = Callable[[pd.DataFrame, StrategyParams], pd.Series]
OverlayBuilder = Callable[[pd.DataFrame, StrategyParams], list[dict[str, Any]]]
Validator = Callable[[StrategyParams], None]


@dataclass(frozen=True)
class StrategyParamDefinition:
    """描述一个策略参数，供前端渲染输入框，也供后端做边界校验。"""

    key: str
    label: str
    value_type: ParamValueType
    default: int | float
    min_value: int | float
    max_value: int | float
    step: int | float
    unit: str
    help_text: str

    def to_json(self) -> dict[str, Any]:
        """转换成前端直接消费的驼峰 JSON。"""

        return {
            "key": self.key,
            "label": self.label,
            "valueType": self.value_type,
            "default": self.default,
            "min": self.min_value,
            "max": self.max_value,
            "step": self.step,
            "unit": self.unit,
            "helpText": self.help_text,
        }


@dataclass(frozen=True)
class StrategyConstraintDefinition:
    """描述前端可展示、后端可执行的策略参数关系约束。"""

    type: str
    message: str
    left: str | None = None
    right: str | None = None
    fields: tuple[str, ...] = ()
    min_value: int | float | None = None
    max_value: int | float | None = None

    def to_json(self) -> dict[str, Any]:
        """转换成前端表单验证可直接消费的 JSON。"""

        payload: dict[str, Any] = {"type": self.type, "message": self.message}
        if self.left is not None:
            payload["left"] = self.left
        if self.right is not None:
            payload["right"] = self.right
        if self.fields:
            payload["fields"] = list(self.fields)
        if self.min_value is not None:
            payload["min"] = self.min_value
        if self.max_value is not None:
            payload["max"] = self.max_value
        return payload


@dataclass(frozen=True)
class StrategyDefinition:
    """完整策略定义，包含展示信息、参数规则和执行函数。"""

    id: str
    name: str
    description: str
    category: str
    params: tuple[StrategyParamDefinition, ...]
    signal_builder: SignalBuilder
    overlay_builder: OverlayBuilder
    constraints: tuple[StrategyConstraintDefinition, ...] = ()
    validator: Validator | None = None
    version: str = "1.0.0"
    source: dict[str, Any] | None = None
    license: str = "internal"
    tags: tuple[str, ...] = ()
    supported_frequencies: tuple[str, ...] = ("1d",)
    risk_level: str = "medium"

    def to_json(self) -> dict[str, Any]:
        """转换成策略列表接口使用的 JSON 结构。"""

        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "version": self.version,
            "source": self.source or {"type": "built_in", "name": "LH Quant"},
            "license": self.license,
            "tags": list(self.tags),
            "supportedFrequencies": list(self.supported_frequencies),
            "riskLevel": self.risk_level,
            "params": [param.to_json() for param in self.params],
            "constraints": [constraint.to_json() for constraint in self.constraints],
        }


def get_strategy_specs() -> list[dict[str, Any]]:
    """返回所有可配置策略的前端展示元数据。"""

    return [strategy.to_json() for strategy in _STRATEGIES.values()]


def get_strategy_definition(strategy_id: str) -> StrategyDefinition:
    """根据策略 ID 取得策略定义，不存在时抛出中文错误。"""

    try:
        return _STRATEGIES[strategy_id]
    except KeyError as error:
        raise ValueError(f"未知策略：{strategy_id}") from error


def normalize_strategy_params(
    strategy_id: str,
    raw_params: Mapping[str, Any] | None,
) -> StrategyParams:
    """补齐默认值并校验策略参数范围。

    前端可能只提交被用户改过的参数，所以这里会用注册表里的默认值补全其余参数；
    同时把字符串形式的数字转换成真实数值，保证策略函数拿到的是干净、可复现的参数。
    """

    strategy = get_strategy_definition(strategy_id)
    incoming = raw_params or {}
    normalized: StrategyParams = {}
    for param in strategy.params:
        value = incoming.get(param.key, param.default)
        normalized[param.key] = _coerce_param_value(param, value)

    _validate_constraints(normalized, strategy.constraints)
    if strategy.validator is not None:
        strategy.validator(normalized)
    return normalized


def generate_strategy_signals(
    strategy_id: str,
    bars: pd.DataFrame,
    params: Mapping[str, Any] | None,
) -> pd.Series:
    """统一生成策略信号，返回与行情索引对齐的 1、0、-1 序列。"""

    strategy = get_strategy_definition(strategy_id)
    normalized = normalize_strategy_params(strategy_id, params)
    return strategy.signal_builder(bars, normalized)


def build_strategy_overlays(
    strategy_id: str,
    bars: pd.DataFrame,
    params: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """统一生成 K线主图叠加指标线，例如均线或突破通道。"""

    strategy = get_strategy_definition(strategy_id)
    normalized = normalize_strategy_params(strategy_id, params)
    return strategy.overlay_builder(bars, normalized)


def _coerce_param_value(param: StrategyParamDefinition, value: Any) -> int | float:
    """把外部传入参数转换成注册表声明的数值类型，并执行上下限校验。"""

    try:
        if param.value_type == "int":
            numeric_value: int | float = int(value)
        else:
            numeric_value = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{param.label} 必须是数字") from error

    if numeric_value < param.min_value or numeric_value > param.max_value:
        raise ValueError(f"{param.label} 必须在 {param.min_value} 到 {param.max_value} 之间")
    return numeric_value


def _validate_constraints(
    params: StrategyParams,
    constraints: tuple[StrategyConstraintDefinition, ...],
) -> None:
    """执行注册表声明的跨参数关系约束。"""

    for constraint in constraints:
        if constraint.type == "lt":
            if constraint.left is None or constraint.right is None:
                raise ValueError("lt constraint requires left and right")
            if not params[constraint.left] < params[constraint.right]:
                raise ValueError(constraint.message)
        elif constraint.type == "ordered":
            values = [params[field] for field in constraint.fields]
            if any(left >= right for left, right in pairwise(values)):
                raise ValueError(constraint.message)
            if constraint.min_value is not None and values[0] <= constraint.min_value:
                raise ValueError(constraint.message)
            if constraint.max_value is not None and values[-1] >= constraint.max_value:
                raise ValueError(constraint.message)
        else:
            raise ValueError(f"未知策略参数约束：{constraint.type}")


def _validate_moving_average(params: StrategyParams) -> None:
    """校验双均线策略的快慢窗口关系。"""

    if params["fastWindow"] >= params["slowWindow"]:
        raise ValueError("短均线周期必须小于长均线周期")


def _validate_momentum_breakout(params: StrategyParams) -> None:
    """校验突破策略的进入窗口需要长于退出窗口。"""

    if params["exitWindow"] >= params["lookbackWindow"]:
        raise ValueError("退出窗口必须小于突破窗口")


def _validate_rsi_reversion(params: StrategyParams) -> None:
    """校验 RSI 阈值顺序，避免产生永远无法触发的规则。"""

    if not 0 < params["oversold"] < params["overbought"] < 100:
        raise ValueError("RSI 阈值必须满足 0 < 超卖阈值 < 过热阈值 < 100")


def _moving_average_signal_builder(bars: pd.DataFrame, params: StrategyParams) -> pd.Series:
    """执行双均线策略信号。"""

    return moving_average_cross_signals(
        bars,
        fast_window=int(params["fastWindow"]),
        slow_window=int(params["slowWindow"]),
    )


def _moving_average_overlay_builder(
    bars: pd.DataFrame,
    params: StrategyParams,
) -> list[dict[str, Any]]:
    """生成双均线主图叠加线。"""

    close = bars["close"].astype(float)
    return [
        {
            "name": "短均线",
            "color": "#2563EB",
            "values": close.rolling(int(params["fastWindow"])).mean(),
        },
        {
            "name": "长均线",
            "color": "#F59E0B",
            "values": close.rolling(int(params["slowWindow"])).mean(),
        },
    ]


def _momentum_breakout_signal_builder(bars: pd.DataFrame, params: StrategyParams) -> pd.Series:
    """执行动量突破策略信号。"""

    return momentum_breakout_signals(
        bars,
        lookback_window=int(params["lookbackWindow"]),
        exit_window=int(params["exitWindow"]),
    )


def _momentum_breakout_overlay_builder(
    bars: pd.DataFrame,
    params: StrategyParams,
) -> list[dict[str, Any]]:
    """生成突破策略的上轨和下轨。"""

    return [
        {
            "name": "突破上轨",
            "color": "#2563EB",
            "values": momentum_breakout_entry_line(bars, int(params["lookbackWindow"])),
        },
        {
            "name": "退出下轨",
            "color": "#F59E0B",
            "values": momentum_breakout_exit_line(bars, int(params["exitWindow"])),
        },
    ]


def _rsi_reversion_signal_builder(bars: pd.DataFrame, params: StrategyParams) -> pd.Series:
    """执行 RSI 均值回归策略信号。"""

    return rsi_reversion_signals(
        bars,
        rsi_window=int(params["rsiWindow"]),
        oversold=float(params["oversold"]),
        overbought=float(params["overbought"]),
    )


def _empty_price_overlay_builder(
    _bars: pd.DataFrame,
    _params: StrategyParams,
) -> list[dict[str, Any]]:
    """RSI 是副图指标，当前版本先不叠到价格主图上。"""

    return []


_STRATEGIES: dict[str, StrategyDefinition] = {
    "moving_average": StrategyDefinition(
        id="moving_average",
        name="双均线策略",
        description="用短期均线上穿长期均线作为买入，下穿作为卖出，适合先验证趋势跟踪流程。",
        category="趋势跟踪",
        params=(
            StrategyParamDefinition(
                key="fastWindow",
                label="短均线",
                value_type="int",
                default=5,
                min_value=2,
                max_value=120,
                step=1,
                unit="日",
                help_text="短周期越小，信号越敏感，噪声也越多。",
            ),
            StrategyParamDefinition(
                key="slowWindow",
                label="长均线",
                value_type="int",
                default=20,
                min_value=3,
                max_value=250,
                step=1,
                unit="日",
                help_text="长周期用于确认主趋势，必须大于短均线。",
            ),
        ),
        signal_builder=_moving_average_signal_builder,
        overlay_builder=_moving_average_overlay_builder,
        constraints=(
            StrategyConstraintDefinition(
                type="lt",
                left="fastWindow",
                right="slowWindow",
                message="短均线周期必须小于长均线周期",
            ),
        ),
        validator=_validate_moving_average,
    ),
    "momentum_breakout": StrategyDefinition(
        id="momentum_breakout",
        name="动量突破策略",
        description="价格突破过去 N 日高点时买入，跌破较短退出通道时离场，适合强趋势行情。",
        category="突破",
        params=(
            StrategyParamDefinition(
                key="lookbackWindow",
                label="突破窗口",
                value_type="int",
                default=60,
                min_value=5,
                max_value=250,
                step=1,
                unit="日",
                help_text="用于计算买入上轨的历史窗口，窗口越大越偏中长期趋势。",
            ),
            StrategyParamDefinition(
                key="exitWindow",
                label="退出窗口",
                value_type="int",
                default=20,
                min_value=3,
                max_value=120,
                step=1,
                unit="日",
                help_text="价格跌破该窗口的低点时退出，必须小于突破窗口。",
            ),
        ),
        signal_builder=_momentum_breakout_signal_builder,
        overlay_builder=_momentum_breakout_overlay_builder,
        constraints=(
            StrategyConstraintDefinition(
                type="lt",
                left="exitWindow",
                right="lookbackWindow",
                message="退出窗口必须小于突破窗口",
            ),
        ),
        validator=_validate_momentum_breakout,
    ),
    "rsi_reversion": StrategyDefinition(
        id="rsi_reversion",
        name="RSI均值回归策略",
        description="RSI 从超卖区修复时买入，进入过热区时卖出，适合震荡和反转研究。",
        category="均值回归",
        params=(
            StrategyParamDefinition(
                key="rsiWindow",
                label="RSI周期",
                value_type="int",
                default=14,
                min_value=2,
                max_value=60,
                step=1,
                unit="日",
                help_text="RSI 计算周期，常用值为 14。",
            ),
            StrategyParamDefinition(
                key="oversold",
                label="超卖阈值",
                value_type="float",
                default=30,
                min_value=1,
                max_value=80,
                step=1,
                unit="",
                help_text="RSI 上穿该阈值时触发买入。",
            ),
            StrategyParamDefinition(
                key="overbought",
                label="过热阈值",
                value_type="float",
                default=60,
                min_value=20,
                max_value=99,
                step=1,
                unit="",
                help_text="RSI 上穿该阈值时触发卖出。",
            ),
        ),
        signal_builder=_rsi_reversion_signal_builder,
        overlay_builder=_empty_price_overlay_builder,
        constraints=(
            StrategyConstraintDefinition(
                type="ordered",
                fields=("oversold", "overbought"),
                min_value=0,
                max_value=100,
                message="RSI 阈值必须满足 0 < 超卖阈值 < 过热阈值 < 100",
            ),
        ),
        validator=_validate_rsi_reversion,
    ),
}
