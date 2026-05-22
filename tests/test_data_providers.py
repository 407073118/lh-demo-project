from __future__ import annotations

import pandas as pd

from lh_quant.data.akshare_provider import download_akshare_bars
from lh_quant.data.providers import AkShareMarketDataProvider, MarketDataResult


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
    assert result.source_detail
    assert result.version.startswith("akshare:")
    assert len(result.bars) == 2
