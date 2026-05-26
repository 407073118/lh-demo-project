from __future__ import annotations

import pandas as pd

from lh_quant.data.akshare_provider import download_akshare_bars
from lh_quant.data.providers import (
    AkShareMarketDataProvider,
    MarketDataResult,
    provider_chain_for,
)


class _AkshareFallbackStub:
    def stock_zh_a_hist(self, **_kwargs):
        return pd.DataFrame()

    def stock_zh_a_hist_tx(self, **_kwargs):
        return pd.DataFrame(
            {
                "date": ["2024-01-02", "2024-01-03"],
                "open": [10.0, 10.5],
                "high": [11.0, 11.5],
                "low": [9.8, 10.2],
                "close": [10.8, 11.2],
                "amount": [1000, 1200],
            }
        )


def test_akshare_empty_primary_response_falls_back_to_tencent() -> None:
    bars = download_akshare_bars(
        symbol="000001",
        start="2024-01-02",
        end="2024-01-03",
        akshare_module=_AkshareFallbackStub(),
    )

    assert len(bars) == 2
    assert "腾讯" in bars.attrs["source_detail"]


def test_akshare_market_data_provider_returns_metadata() -> None:
    provider = AkShareMarketDataProvider(akshare_module=_AkshareFallbackStub())

    result = provider.download_bars(
        symbol="000001",
        start="2024-01-02",
        end="2024-01-03",
        adjust="qfq",
    )

    assert isinstance(result, MarketDataResult)
    assert result.provider == "AKShare"
    assert result.actual_provider == "AKShare"
    assert result.requested_provider == "akshare"
    assert result.source_detail
    assert result.version.startswith("akshare:")
    assert result.data_version.startswith("akshare:")
    assert len(result.bars) == 2


def test_provider_chain_uses_tushare_first_for_unadjusted_auto_requests() -> None:
    assert provider_chain_for("auto", "") == ["tushare", "akshare", "yahoo"]


def test_provider_chain_skips_tushare_for_adjusted_auto_requests() -> None:
    assert provider_chain_for("auto", "qfq") == ["akshare", "yahoo"]


def test_provider_chain_keeps_explicit_provider_isolated() -> None:
    assert provider_chain_for("akshare", "qfq") == ["akshare"]
