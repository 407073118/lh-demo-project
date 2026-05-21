"""Yahoo Finance 日线数据下载和解析。"""

from __future__ import annotations

import json
from datetime import UTC, datetime, time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import pandas as pd

from lh_quant.data.schema import BarValidationError, validate_bars

YAHOO_CHART_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"


class YahooDataError(RuntimeError):
    """Yahoo Finance 数据下载或解析失败时抛出的异常。"""


def build_yahoo_chart_url(symbol: str, start: str, end: str) -> str:
    """构造 Yahoo Finance 日线 chart 接口 URL。

    start 和 end 使用 `YYYY-MM-DD` 格式。函数会转换成 Yahoo 接口需要的 Unix 秒级时间戳。
    """

    symbol_path = quote(symbol.upper(), safe=".-")
    params = urlencode(
        {
            "period1": _date_to_epoch(start, end_of_day=False),
            "period2": _date_to_epoch(end, end_of_day=True),
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
        }
    )
    return f"{YAHOO_CHART_BASE_URL}/{symbol_path}?{params}"


def download_yahoo_bars(symbol: str, start: str, end: str) -> pd.DataFrame:
    """从 Yahoo Finance 下载指定标的的日线 OHLCV 数据。

    返回的数据会被转换成项目统一的 K线字段：`symbol, datetime, open, high, low, close, volume`。
    """

    url = build_yahoo_chart_url(symbol=symbol, start=start, end=end)
    request = Request(url, headers={"User-Agent": "lh-quant/0.1"})
    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as error:
        raise YahooDataError(f"Yahoo Finance 返回 HTTP {error.code}") from error
    except URLError as error:
        raise YahooDataError(f"无法连接 Yahoo Finance: {error.reason}") from error
    except TimeoutError as error:
        raise YahooDataError("Yahoo Finance 请求超时") from error

    return parse_yahoo_chart_response(payload, symbol=symbol)


def parse_yahoo_chart_response(payload: str, symbol: str) -> pd.DataFrame:
    """把 Yahoo Finance chart JSON 解析成项目内部 K线数据格式。

    函数会丢弃 OHLCV 关键字段为空的行，并在返回前调用 `validate_bars` 做统一校验。
    """

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as error:
        raise YahooDataError("Yahoo Finance 返回内容不是合法 JSON") from error

    chart = data.get("chart", {})
    if chart.get("error"):
        raise YahooDataError(f"Yahoo Finance 返回错误: {chart['error']}")

    result = chart.get("result") or []
    if not result:
        raise YahooDataError("Yahoo Finance 返回内容缺少 chart 结果")

    first = result[0]
    timestamps = first.get("timestamp") or []
    quotes = first.get("indicators", {}).get("quote") or []
    if not timestamps or not quotes:
        raise YahooDataError("Yahoo Finance 返回内容缺少 OHLCV K线数据")

    quote_data = quotes[0]
    bars = pd.DataFrame(
        {
            "symbol": symbol.upper(),
            "datetime": pd.to_datetime(timestamps, unit="s", utc=True).tz_localize(None),
            "open": quote_data.get("open"),
            "high": quote_data.get("high"),
            "low": quote_data.get("low"),
            "close": quote_data.get("close"),
            "volume": quote_data.get("volume"),
        }
    )
    bars = _drop_invalid_ohlc_rows(bars.dropna(subset=["open", "high", "low", "close", "volume"]))
    if bars.empty:
        raise YahooDataError("Yahoo Finance 没有可用的合法K线数据")

    try:
        return validate_bars(bars)
    except BarValidationError as error:
        raise YahooDataError(f"Yahoo Finance K线数据校验失败: {error}") from error


def _date_to_epoch(value: str, end_of_day: bool) -> int:
    """把 YYYY-MM-DD 日期转换为 UTC Unix 秒级时间戳。"""

    parsed = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    if end_of_day:
        parsed = datetime.combine(parsed.date(), time(23, 59, 59), tzinfo=UTC)
    return int(parsed.timestamp())


def _drop_invalid_ohlc_rows(bars: pd.DataFrame) -> pd.DataFrame:
    """过滤 Yahoo 偶发返回的 OHLC 区间异常行，保留可校验的日线数据。"""

    normalized = bars.copy()
    price_columns = ["open", "high", "low", "close"]
    for column in [*price_columns, "volume"]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    valid = (
        normalized[price_columns].gt(0).all(axis=1)
        & normalized["volume"].ge(0)
        & normalized["high"].ge(normalized["low"])
        & normalized["open"].between(normalized["low"], normalized["high"])
        & normalized["close"].between(normalized["low"], normalized["high"])
    )
    return normalized.loc[valid].copy()
