import pandas as pd
import pytest

from lh_quant.data.schema import BarValidationError, validate_bars


def test_validate_bars_accepts_ordered_ohlcv_data() -> None:
    bars = pd.DataFrame(
        {
            "symbol": ["DEMO", "DEMO"],
            "datetime": ["2024-01-01", "2024-01-02"],
            "open": [10.0, 11.0],
            "high": [12.0, 12.5],
            "low": [9.5, 10.5],
            "close": [11.0, 12.0],
            "volume": [1000, 1200],
        }
    )

    validated = validate_bars(bars)

    assert list(validated.columns) == [
        "symbol",
        "datetime",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    assert str(validated["datetime"].dtype).startswith("datetime64")


def test_validate_bars_rejects_missing_required_columns() -> None:
    bars = pd.DataFrame({"symbol": ["DEMO"], "close": [10.0]})

    with pytest.raises(BarValidationError, match="缺少必填字段"):
        validate_bars(bars)


def test_validate_bars_rejects_impossible_price_ranges() -> None:
    bars = pd.DataFrame(
        {
            "symbol": ["DEMO"],
            "datetime": ["2024-01-01"],
            "open": [10.0],
            "high": [9.0],
            "low": [10.0],
            "close": [9.5],
            "volume": [1000],
        }
    )

    with pytest.raises(BarValidationError, match="最高价必须大于等于最低价"):
        validate_bars(bars)


def test_validate_bars_rejects_non_positive_prices() -> None:
    bars = pd.DataFrame(
        {
            "symbol": ["DEMO"],
            "datetime": ["2024-01-01"],
            "open": [10.0],
            "high": [12.0],
            "low": [0.0],
            "close": [11.0],
            "volume": [1000],
        }
    )

    with pytest.raises(BarValidationError, match="价格字段必须大于 0"):
        validate_bars(bars)


def test_validate_bars_rejects_duplicate_symbol_datetime_rows() -> None:
    bars = pd.DataFrame(
        {
            "symbol": ["DEMO", "DEMO"],
            "datetime": ["2024-01-01", "2024-01-01"],
            "open": [10.0, 10.0],
            "high": [12.0, 12.0],
            "low": [9.0, 9.0],
            "close": [11.0, 11.0],
            "volume": [1000, 1000],
        }
    )

    with pytest.raises(BarValidationError, match="同一标的同一时间不能重复"):
        validate_bars(bars)
