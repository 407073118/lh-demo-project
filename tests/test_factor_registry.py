from __future__ import annotations

from lh_quant.data.sample import generate_sample_bars
from lh_quant.factors.registry import calculate_factor, get_factor_specs


def test_factor_registry_exposes_core_local_factors() -> None:
    specs = get_factor_specs()

    assert {factor["id"] for factor in specs} >= {
        "return_20d",
        "volatility_20d",
        "ma_20d",
        "rsi_14d",
    }
    assert specs[0]["source"] == "local"
    assert "license" in specs[0]


def test_factor_calculation_returns_series_aligned_to_bars() -> None:
    bars = generate_sample_bars(symbol="000001", periods=40)

    values = calculate_factor("return_20d", bars)

    assert values.name == "return_20d"
    assert len(values) == len(bars)
    assert values.index.equals(bars.index)
