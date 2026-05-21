"""AKShare A股日线数据下载和字段规范化。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from lh_quant.data.schema import BarValidationError, validate_bars


class AkShareDataError(RuntimeError):
    """AKShare 数据下载、字段转换或数据校验失败时抛出的异常。"""


def download_akshare_bars(
    symbol: str,
    start: str,
    end: str,
    adjust: str = "qfq",
    timeout: float = 15,
    akshare_module: Any | None = None,
) -> pd.DataFrame:
    """从 AKShare 下载 A股日线数据，并转换成项目统一K线格式。

    参数：
    - symbol：A股代码，例如 `000001`、`600519`，不带交易所后缀。
    - start/end：日期，使用 `YYYY-MM-DD` 格式。
    - adjust：复权方式，`qfq` 表示前复权，`hfq` 表示后复权，空字符串表示不复权。
    - timeout：单个 AKShare 接口的网络超时时间，避免外部数据源卡死回测流程。
    - akshare_module：测试用依赖注入；正常运行时无需传入。
    """

    ak = akshare_module or _import_akshare()
    try:
        raw = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=_to_akshare_date(start),
            end_date=_to_akshare_date(end),
            adjust=adjust,
            timeout=timeout,
        )
    except Exception as error:
        eastmoney_error = error
    else:
        if raw.empty:
            raise AkShareDataError(f"AKShare 没有返回数据: {symbol} {start} 到 {end}")
        bars = normalize_akshare_stock_hist(raw, symbol=symbol)
        bars.attrs["source_detail"] = "AKShare 东方财富日线接口"
        return bars

    try:
        raw_tx = ak.stock_zh_a_hist_tx(
            symbol=_to_tencent_symbol(symbol),
            start_date=_to_akshare_date(start),
            end_date=_to_akshare_date(end),
            adjust=adjust,
            timeout=timeout,
        )
    except Exception as tencent_error:
        message = f"AKShare 东方财富接口失败: {eastmoney_error}；腾讯接口也失败: {tencent_error}"
        raise AkShareDataError(message) from tencent_error

    if raw_tx.empty:
        raise AkShareDataError(f"AKShare 腾讯接口没有返回数据: {symbol} {start} 到 {end}")
    bars = normalize_akshare_stock_hist_tx(raw_tx, symbol=symbol)
    bars.attrs["source_detail"] = "AKShare 腾讯日线接口"
    return bars


def normalize_akshare_stock_hist(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """把 AKShare `stock_zh_a_hist` 的中文字段转换为项目K线契约。

    AKShare 返回字段通常包括 `日期、开盘、收盘、最高、最低、成交量`。项目内部统一使用
    `symbol, datetime, open, high, low, close, volume`，方便后续策略和回测复用。
    """

    required = ["日期", "开盘", "最高", "最低", "收盘", "成交量"]
    missing = [column for column in required if column not in raw.columns]
    if missing:
        raise AkShareDataError(f"AKShare 数据缺少字段: {', '.join(missing)}")

    bars = pd.DataFrame(
        {
            "symbol": symbol,
            "datetime": raw["日期"],
            "open": raw["开盘"],
            "high": raw["最高"],
            "low": raw["最低"],
            "close": raw["收盘"],
            "volume": raw["成交量"],
        }
    )

    try:
        return validate_bars(bars)
    except BarValidationError as error:
        raise AkShareDataError(f"AKShare K线数据校验失败: {error}") from error


def normalize_akshare_stock_hist_tx(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """把 AKShare 腾讯日线接口字段转换为项目 K线契约。

    `stock_zh_a_hist_tx` 返回的 `amount` 是成交量，单位通常是“手”；项目内部统一按“股”
    保存，所以这里乘以 100，便于和东方财富、Yahoo 等源的 volume 口径对齐。
    """

    required = ["date", "open", "high", "low", "close", "amount"]
    missing = [column for column in required if column not in raw.columns]
    if missing:
        raise AkShareDataError(f"AKShare 腾讯接口数据缺少字段: {', '.join(missing)}")

    bars = pd.DataFrame(
        {
            "symbol": symbol,
            "datetime": raw["date"],
            "open": raw["open"],
            "high": raw["high"],
            "low": raw["low"],
            "close": raw["close"],
            "volume": pd.to_numeric(raw["amount"], errors="coerce") * 100,
        }
    )

    try:
        return validate_bars(bars)
    except BarValidationError as error:
        raise AkShareDataError(f"AKShare 腾讯接口K线数据校验失败: {error}") from error


def _import_akshare() -> Any:
    """延迟导入 AKShare，让没有安装依赖时也能看到清楚的中文错误。"""

    try:
        import akshare as ak
    except ImportError as error:
        raise AkShareDataError("当前环境未安装 AKShare，请先执行 pip install -e .") from error
    return ak


def _to_akshare_date(value: str) -> str:
    """把 `YYYY-MM-DD` 日期转换成 AKShare 需要的 `YYYYMMDD` 格式。"""

    try:
        return pd.Timestamp(value).strftime("%Y%m%d")
    except ValueError as error:
        raise AkShareDataError(f"日期格式无效: {value}，请使用 YYYY-MM-DD") from error


def _to_tencent_symbol(symbol: str) -> str:
    """把 6 位 A股代码转换成 AKShare 腾讯接口使用的 `sz000001`/`sh600000` 格式。"""

    normalized = symbol.strip().lower()
    if normalized.startswith(("sh", "sz")):
        return normalized
    if normalized.startswith("6"):
        return f"sh{normalized}"
    return f"sz{normalized}"
