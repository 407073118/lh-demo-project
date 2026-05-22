"""行情数据源协议和内置适配器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd

from lh_quant.data.akshare_provider import download_akshare_bars


@dataclass(frozen=True)
class MarketDataResult:
    """一次行情下载的标准结果，包含数据和来源血缘。"""

    bars: pd.DataFrame
    provider: str
    source_detail: str
    version: str


class MarketDataProvider(Protocol):
    """行情数据源需要实现的最小接口。"""

    provider_id: str

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

    provider_id = "AKShare"

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

        bars = download_akshare_bars(
            symbol=symbol,
            start=start,
            end=end,
            adjust=adjust,
            akshare_module=self._akshare_module,
        )
        version = f"akshare:{getattr(self._akshare_module, '__version__', 'runtime')}"
        return MarketDataResult(
            bars=bars,
            provider=self.provider_id,
            source_detail=str(bars.attrs.get("source_detail", self.provider_id)),
            version=version,
        )
