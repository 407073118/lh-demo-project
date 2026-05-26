from __future__ import annotations

import pytest

from lh_quant.data.tushare_provider import (
    TusharePermissionError,
    TushareProvider,
    TushareProviderError,
)


def test_tushare_provider_requires_token() -> None:
    with pytest.raises(TushareProviderError, match="token"):
        TushareProvider(token="")


def test_tushare_trade_calendar_maps_http_payload() -> None:
    calls: list[dict] = []

    def fake_post(payload: dict) -> dict:
        calls.append(payload)
        return {
            "code": 0,
            "msg": None,
            "data": {
                "fields": ["exchange", "cal_date", "is_open", "pretrade_date"],
                "items": [["SSE", "20240102", 1, "20231229"], ["SSE", "20240103", 0, "20240102"]],
            },
        }

    provider = TushareProvider(token="secret", post_json=fake_post)

    rows = provider.fetch_trade_calendar(
        exchange="SSE",
        start="2024-01-01",
        end="2024-01-05",
    )

    assert calls[0]["api_name"] == "trade_cal"
    assert calls[0]["params"]["start_date"] == "20240101"
    assert rows == [
        {
            "exchange": "SSE",
            "trade_date": "2024-01-02",
            "is_open": True,
            "pretrade_date": "2023-12-29",
            "source": "Tushare",
        },
        {
            "exchange": "SSE",
            "trade_date": "2024-01-03",
            "is_open": False,
            "pretrade_date": "2024-01-02",
            "source": "Tushare",
        },
    ]


def test_tushare_permission_error_is_explicit() -> None:
    def fake_post(_payload: dict) -> dict:
        return {"code": 2002, "msg": "permission denied", "data": None}

    provider = TushareProvider(token="secret", post_json=fake_post)

    with pytest.raises(TusharePermissionError, match="permission"):
        provider.fetch_trade_calendar(exchange="", start="2024-01-01", end="2024-01-05")


def test_tushare_daily_bars_maps_payload_and_volume_units() -> None:
    calls: list[dict] = []

    def fake_post(payload: dict) -> dict:
        calls.append(payload)
        return {
            "code": 0,
            "msg": None,
            "data": {
                "fields": ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"],
                "items": [
                    ["000001.SZ", "20240102", 10.0, 10.8, 9.8, 10.5, 1234.0, 1300.0],
                    ["000001.SZ", "20240103", 10.5, 11.2, 10.2, 11.0, 1500.0, 1600.0],
                ],
            },
        }

    provider = TushareProvider(token="secret", post_json=fake_post)

    bars = provider.fetch_daily_bars(symbol="000001", start="2024-01-01", end="2024-01-05")

    assert calls[0]["api_name"] == "daily"
    assert calls[0]["params"] == {
        "ts_code": "000001.SZ",
        "start_date": "20240101",
        "end_date": "20240105",
    }
    assert bars["symbol"].tolist() == ["000001", "000001"]
    assert bars["datetime"].dt.strftime("%Y-%m-%d").tolist() == ["2024-01-02", "2024-01-03"]
    assert bars["volume"].tolist() == [123400.0, 150000.0]


def test_tushare_daily_keeps_suffixed_symbol_payload() -> None:
    def fake_post(payload: dict) -> dict:
        assert payload["params"]["ts_code"] == "600519.SH"
        return {
            "code": 0,
            "msg": None,
            "data": {
                "fields": ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"],
                "items": [["600519.SH", "20240102", 1600.0, 1610.0, 1590.0, 1605.0, 10.0, 100.0]],
            },
        }

    provider = TushareProvider(token="secret", post_json=fake_post)

    bars = provider.fetch_daily_bars(symbol="600519.SH", start="2024-01-01", end="2024-01-05")

    assert bars.loc[0, "symbol"] == "600519"
