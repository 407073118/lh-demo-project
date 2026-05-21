import json

import pytest

from lh_quant.data.yahoo import (
    YahooDataError,
    build_yahoo_chart_url,
    download_yahoo_bars,
    parse_yahoo_chart_response,
)


def test_build_yahoo_chart_url_uses_epoch_range_and_daily_interval() -> None:
    url = build_yahoo_chart_url("AAPL", start="2024-01-01", end="2024-01-31")

    assert url.startswith("https://query1.finance.yahoo.com/v8/finance/chart/AAPL?")
    assert "interval=1d" in url
    assert "period1=1704067200" in url
    assert "period2=1706745599" in url


def test_parse_yahoo_chart_response_returns_valid_bar_contract() -> None:
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1704211200, 1704297600],
                    "indicators": {
                        "quote": [
                            {
                                "open": [184.22, 182.15],
                                "high": [185.88, 183.09],
                                "low": [183.43, 180.88],
                                "close": [185.64, 181.91],
                                "volume": [82488700, 58414500],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }

    bars = parse_yahoo_chart_response(json.dumps(payload), symbol="AAPL")

    assert bars["symbol"].tolist() == ["AAPL", "AAPL"]
    assert bars["close"].tolist() == [185.64, 181.91]
    assert list(bars.columns) == ["symbol", "datetime", "open", "high", "low", "close", "volume"]


def test_parse_yahoo_chart_response_drops_invalid_ohlc_rows() -> None:
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1704211200, 1704297600],
                    "indicators": {
                        "quote": [
                            {
                                "open": [10.0, 11.0],
                                "high": [10.5, 10.8],
                                "low": [9.8, 10.7],
                                "close": [10.2, 10.9],
                                "volume": [1000, 1200],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }

    bars = parse_yahoo_chart_response(json.dumps(payload), symbol="000001.SZ")

    assert len(bars) == 1
    assert bars["close"].tolist() == [10.2]


def test_download_yahoo_bars_wraps_timeout_as_chinese_data_error(monkeypatch) -> None:
    def fake_urlopen(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr("lh_quant.data.yahoo.urlopen", fake_urlopen)

    with pytest.raises(YahooDataError, match="Yahoo Finance 请求超时"):
        download_yahoo_bars("AAPL", start="2024-01-01", end="2024-01-31")
