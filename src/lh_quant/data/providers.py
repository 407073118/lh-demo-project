"""行情数据源协议和内置适配器。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import pandas as pd

from lh_quant.data.akshare_provider import AkShareDataError, download_akshare_bars
from lh_quant.data.tushare_provider import (
    TushareProvider,
    TushareProviderError,
    _to_tushare_symbol,
)
from lh_quant.data.yahoo import YahooDataError, download_yahoo_bars

ProviderId = Literal["auto", "tushare", "akshare", "yahoo"]

PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    "tushare": "Tushare",
    "akshare": "AKShare",
    "yahoo": "Yahoo Finance",
}


class MarketDataProviderError(RuntimeError):
    """统一 provider 选择、下载或能力不支持时抛出的错误。"""


@dataclass(frozen=True)
class ProviderAttempt:
    """一次 provider 尝试的可序列化记录。"""

    provider: str
    status: str
    reason: str | None = None
    source_detail: str | None = None

    def to_json(self) -> dict[str, str]:
        """转换成 API 和数据库可直接保存的字典。"""

        payload = {"provider": self.provider, "status": self.status}
        if self.reason:
            payload["reason"] = self.reason
        if self.source_detail:
            payload["sourceDetail"] = self.source_detail
        return payload


@dataclass(frozen=True)
class MarketDataResult:
    """一次行情下载的标准结果，包含数据和来源血缘。"""

    bars: pd.DataFrame
    requested_provider: str
    actual_provider: str
    source_detail: str
    raw_symbol: str
    normalized_symbol: str
    frequency: str
    adjust: str
    data_version: str
    fetched_at: str
    fallback_chain: list[dict[str, str]]

    @property
    def provider(self) -> str:
        """兼容旧调用方读取实际 provider。"""

        return self.actual_provider

    @property
    def version(self) -> str:
        """兼容旧调用方读取数据版本。"""

        return self.data_version


class MarketDataProvider(Protocol):
    """行情数据源需要实现的最小接口。"""

    provider_id: str
    display_name: str

    def download_bars(
        self,
        symbol: str,
        start: str,
        end: str,
        adjust: str,
    ) -> MarketDataResult:
        """下载指定区间的 K 线并返回统一结果。"""
        ...


class AkShareMarketDataProvider:
    """AKShare 行情数据源适配器。"""

    provider_id = "akshare"
    display_name = PROVIDER_DISPLAY_NAMES[provider_id]

    def __init__(self, akshare_module: Any | None = None) -> None:
        """保存可选的 AKShare 依赖注入对象，便于测试。"""

        self._akshare_module = akshare_module

    def download_bars(
        self,
        symbol: str,
        start: str,
        end: str,
        adjust: str,
    ) -> MarketDataResult:
        """通过 AKShare 下载 A 股日线并补充来源元数据。"""

        try:
            bars = download_akshare_bars(
                symbol=symbol,
                start=start,
                end=end,
                adjust=adjust,
                akshare_module=self._akshare_module,
            )
        except AkShareDataError as error:
            raise MarketDataProviderError(str(error)) from error

        source_detail = str(bars.attrs.get("source_detail", self.display_name))
        version = f"akshare:{getattr(self._akshare_module, '__version__', 'runtime')}"
        return _result(
            bars=bars,
            requested_provider=self.provider_id,
            actual_provider=self.display_name,
            source_detail=source_detail,
            raw_symbol=symbol,
            normalized_symbol=symbol.strip(),
            adjust=adjust,
            data_version=version,
        )


class TushareMarketDataProvider:
    """Tushare 未复权日线行情适配器。"""

    provider_id = "tushare"
    display_name = PROVIDER_DISPLAY_NAMES[provider_id]

    def __init__(self, tushare_provider: TushareProvider | None = None) -> None:
        """保存可选的 Tushare provider 注入对象，便于测试。"""

        self._provider = tushare_provider

    def download_bars(
        self,
        symbol: str,
        start: str,
        end: str,
        adjust: str,
    ) -> MarketDataResult:
        """通过 Tushare `daily` 下载未复权日线并补充来源元数据。"""

        if adjust:
            raise MarketDataProviderError("第一版暂不支持 Tushare 复权，请选择不复权或切换 AKShare")

        try:
            provider = self._provider or TushareProvider()
            bars = provider.fetch_daily_bars(symbol=symbol, start=start, end=end)
        except TushareProviderError as error:
            raise MarketDataProviderError(str(error)) from error

        raw_symbol = _to_tushare_symbol(symbol)
        return _result(
            bars=bars,
            requested_provider=self.provider_id,
            actual_provider=self.display_name,
            source_detail="Tushare daily 日线接口",
            raw_symbol=raw_symbol,
            normalized_symbol=str(bars.loc[0, "symbol"]),
            adjust=adjust,
            data_version=f"tushare:daily:{_utc_now_text()}",
        )


class YahooMarketDataProvider:
    """Yahoo Finance 日线行情适配器。"""

    provider_id = "yahoo"
    display_name = PROVIDER_DISPLAY_NAMES[provider_id]

    def download_bars(
        self,
        symbol: str,
        start: str,
        end: str,
        adjust: str,
    ) -> MarketDataResult:
        """通过 Yahoo Finance 下载日线并补充来源元数据。"""

        try:
            bars = download_yahoo_bars(symbol=symbol, start=start, end=end)
        except YahooDataError as error:
            raise MarketDataProviderError(str(error)) from error

        return _result(
            bars=bars,
            requested_provider=self.provider_id,
            actual_provider=self.display_name,
            source_detail="Yahoo Finance chart 日线接口",
            raw_symbol=symbol.upper(),
            normalized_symbol=symbol.upper(),
            adjust=adjust,
            data_version=f"yahoo:chart:{_utc_now_text()}",
        )


def normalize_provider_id(value: str | None) -> ProviderId:
    """把请求中的 provider ID 归一化为稳定枚举。"""

    normalized = (value or "auto").strip().lower()
    if normalized in {"auto", "tushare", "akshare", "yahoo"}:
        return normalized  # type: ignore[return-value]
    raise ValueError(f"未知行情数据源: {value}")


def provider_chain_for(requested_provider: str | None, adjust: str) -> list[str]:
    """根据用户请求和复权口径生成 provider 尝试顺序。"""

    provider_id = normalize_provider_id(requested_provider)
    if provider_id != "auto":
        return [provider_id]
    if adjust:
        return ["akshare", "yahoo"]
    return ["tushare", "akshare", "yahoo"]


def build_market_data_provider(provider_id: str) -> MarketDataProvider:
    """创建单个具体 provider，`auto` 需要先展开 chain。"""

    normalized = normalize_provider_id(provider_id)
    if normalized == "akshare":
        return AkShareMarketDataProvider()
    if normalized == "tushare":
        return TushareMarketDataProvider()
    if normalized == "yahoo":
        return YahooMarketDataProvider()
    raise ValueError("auto cannot be built directly")


def provider_display_name(provider_id: str) -> str:
    """返回 provider 入库使用的展示名称。"""

    normalized = normalize_provider_id(provider_id)
    if normalized == "auto":
        return "auto"
    return PROVIDER_DISPLAY_NAMES[normalized]


def _result(
    bars: pd.DataFrame,
    requested_provider: str,
    actual_provider: str,
    source_detail: str,
    raw_symbol: str,
    normalized_symbol: str,
    adjust: str,
    data_version: str,
) -> MarketDataResult:
    """组装统一行情下载结果，并附带一次成功尝试记录。"""

    fetched_at = _utc_now_text()
    return MarketDataResult(
        bars=bars,
        requested_provider=requested_provider,
        actual_provider=actual_provider,
        source_detail=source_detail,
        raw_symbol=raw_symbol,
        normalized_symbol=normalized_symbol,
        frequency="1d",
        adjust=adjust or "",
        data_version=data_version,
        fetched_at=fetched_at,
        fallback_chain=[
            ProviderAttempt(
                provider=actual_provider,
                status="succeeded",
                source_detail=source_detail,
            ).to_json()
        ],
    )


def _utc_now_text() -> str:
    """生成 UTC ISO 时间戳，用作运行时数据版本的一部分。"""

    return datetime.now(UTC).isoformat()
