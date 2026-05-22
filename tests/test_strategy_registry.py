from __future__ import annotations

from lh_quant.data.sample import generate_sample_bars
from lh_quant.strategies.registry import (
    build_strategy_overlays,
    generate_strategy_signals,
    get_strategy_specs,
    normalize_strategy_params,
)


def test_strategy_specs_expose_initial_configurable_strategies() -> None:
    specs = get_strategy_specs()

    assert [spec["id"] for spec in specs] == [
        "moving_average",
        "momentum_breakout",
        "rsi_reversion",
    ]
    assert specs[0]["name"] == "双均线策略"
    assert specs[0]["params"][0]["key"] == "fastWindow"


def test_strategy_specs_include_asset_metadata() -> None:
    specs = get_strategy_specs()
    strategy = specs[0]

    assert set(strategy) >= {
        "version",
        "source",
        "license",
        "tags",
        "supportedFrequencies",
        "riskLevel",
    }
    assert strategy["version"]
    assert strategy["source"]["type"] == "built_in"
    assert strategy["license"] == "internal"
    assert isinstance(strategy["tags"], list)
    assert strategy["supportedFrequencies"] == ["1d"]
    assert {param["valueType"] for param in strategy["params"]} <= {
        "int",
        "float",
        "bool",
        "enum",
        "factor",
        "universe",
    }


def test_strategy_specs_include_constraints_for_frontend_validation() -> None:
    """策略规格会暴露前端可复用的参数关系约束。"""

    specs = get_strategy_specs()
    moving_average = next(spec for spec in specs if spec["id"] == "moving_average")
    momentum = next(spec for spec in specs if spec["id"] == "momentum_breakout")
    rsi = next(spec for spec in specs if spec["id"] == "rsi_reversion")

    assert moving_average["constraints"] == [
        {
            "type": "lt",
            "left": "fastWindow",
            "right": "slowWindow",
            "message": "短均线周期必须小于长均线周期",
        }
    ]
    assert momentum["constraints"][0]["left"] == "exitWindow"
    assert momentum["constraints"][0]["right"] == "lookbackWindow"
    assert rsi["constraints"][0]["type"] == "ordered"
    assert rsi["constraints"][0]["fields"] == ["oversold", "overbought"]


def test_strategy_params_fill_defaults_and_validate_boundaries() -> None:
    params = normalize_strategy_params("moving_average", {"fastWindow": 8})

    assert params["fastWindow"] == 8
    assert params["slowWindow"] == 20


def test_momentum_breakout_strategy_generates_signals_without_future_data() -> None:
    bars = generate_sample_bars(symbol="000001", periods=80)
    params = normalize_strategy_params(
        "momentum_breakout",
        {"lookbackWindow": 20, "exitWindow": 8},
    )

    signals = generate_strategy_signals("momentum_breakout", bars, params)

    assert signals.index.equals(bars.index)
    assert set(signals.unique()) <= {-1, 0, 1}


def test_rsi_reversion_strategy_generates_price_overlays() -> None:
    bars = generate_sample_bars(symbol="000001", periods=80)
    params = normalize_strategy_params("rsi_reversion", {})

    signals = generate_strategy_signals("rsi_reversion", bars, params)
    overlays = build_strategy_overlays("rsi_reversion", bars, params)

    assert signals.index.equals(bars.index)
    assert overlays == []
