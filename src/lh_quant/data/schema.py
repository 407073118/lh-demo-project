"""项目内部统一的K线数据契约和校验逻辑。"""

from typing import Final

import pandas as pd

REQUIRED_BAR_COLUMNS: Final[tuple[str, ...]] = (
    "symbol",
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
)


class BarValidationError(ValueError):
    """K线数据不符合项目数据契约时抛出的异常。"""


def validate_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """校验并规范化 OHLCV K线数据。

    输入数据必须包含 `symbol, datetime, open, high, low, close, volume` 七个字段。
    函数会解析时间、把价格和成交量转成数字、检查价格区间是否合法，并按标的和时间排序。
    返回值仍然是 DataFrame，字段顺序会被整理成项目内部标准顺序。
    """

    missing = [column for column in REQUIRED_BAR_COLUMNS if column not in bars.columns]
    if missing:
        raise BarValidationError(f"缺少必填字段: {', '.join(missing)}")

    validated = bars.loc[:, REQUIRED_BAR_COLUMNS].copy()
    validated["datetime"] = pd.to_datetime(validated["datetime"], errors="coerce")

    if validated["datetime"].isna().any():
        raise BarValidationError("datetime 字段包含无法解析的时间")

    price_columns = ["open", "high", "low", "close"]
    for column in [*price_columns, "volume"]:
        validated[column] = pd.to_numeric(validated[column], errors="coerce")

    if validated[[*price_columns, "volume"]].isna().any().any():
        raise BarValidationError("价格和成交量字段必须是数字")

    if (validated[price_columns] <= 0).any().any():
        raise BarValidationError("价格字段必须大于 0")

    if (validated["high"] < validated["low"]).any():
        raise BarValidationError("最高价必须大于等于最低价")

    if (validated["open"] > validated["high"]).any() or (
        validated["open"] < validated["low"]
    ).any():
        raise BarValidationError("开盘价必须落在最高价和最低价之间")

    if (validated["close"] > validated["high"]).any() or (
        validated["close"] < validated["low"]
    ).any():
        raise BarValidationError("收盘价必须落在最高价和最低价之间")

    if (validated["volume"] < 0).any():
        raise BarValidationError("成交量不能为负数")

    if validated.duplicated(subset=["symbol", "datetime"]).any():
        raise BarValidationError("同一标的同一时间不能重复")

    return validated.sort_values(["symbol", "datetime"]).reset_index(drop=True)
