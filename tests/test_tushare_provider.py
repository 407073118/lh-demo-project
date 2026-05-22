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
