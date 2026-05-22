"""Tushare Pro 授权数据同步的最小连接器。"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any
from urllib import request

import pandas as pd


class TushareProviderError(RuntimeError):
    """Tushare 配置或响应无效时抛出的错误。"""


class TusharePermissionError(TushareProviderError):
    """Tushare 返回权限、积分或额度问题时抛出的错误。"""


PostJson = Callable[[dict[str, Any]], dict[str, Any]]


class TushareProvider:
    """面向 Tushare HTTP API 的轻量 provider。"""

    endpoint = "http://api.tushare.pro"

    def __init__(self, token: str | None = None, post_json: PostJson | None = None) -> None:
        """读取 token 并保存可注入的 HTTP 调用函数。"""

        self.token = token if token is not None else os.getenv("TUSHARE_TOKEN", "")
        if not self.token:
            raise TushareProviderError("Tushare token is required; set TUSHARE_TOKEN.")
        self._post_json = post_json or self._default_post_json

    def fetch_trade_calendar(
        self,
        exchange: str,
        start: str,
        end: str,
    ) -> list[dict[str, Any]]:
        """同步交易日历并转换为项目内部记录格式。"""

        payload = {
            "api_name": "trade_cal",
            "token": self.token,
            "params": {
                "exchange": exchange,
                "start_date": _to_tushare_date(start),
                "end_date": _to_tushare_date(end),
            },
            "fields": "exchange,cal_date,is_open,pretrade_date",
        }
        response = self._request(payload)
        return [_trade_calendar_record(row) for row in _rows(response)]

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """发送请求并把 Tushare 错误码转换为明确异常。"""

        response = self._post_json(payload)
        code = int(response.get("code", -1))
        if code == 2002:
            raise TusharePermissionError(str(response.get("msg") or "Tushare permission denied"))
        if code != 0:
            raise TushareProviderError(str(response.get("msg") or f"Tushare error code {code}"))
        return response

    def _default_post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        """使用标准库发送 JSON POST 请求。"""

        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(http_request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


def _rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    """把 Tushare 的 fields/items 结构转换成字典列表。"""

    data = response.get("data")
    if not isinstance(data, dict):
        return []
    fields = data.get("fields") or []
    items = data.get("items") or []
    return [dict(zip(fields, item, strict=False)) for item in items]


def _trade_calendar_record(row: dict[str, Any]) -> dict[str, Any]:
    """把 Tushare 交易日历行转换成内部字段。"""

    return {
        "exchange": str(row["exchange"]),
        "trade_date": _to_iso_date(row["cal_date"]),
        "is_open": bool(int(row["is_open"])),
        "pretrade_date": _to_iso_date(row["pretrade_date"]) if row.get("pretrade_date") else None,
        "source": "Tushare",
    }


def _to_tushare_date(value: str) -> str:
    """把日期转换为 Tushare 需要的 YYYYMMDD。"""

    return pd.Timestamp(value).strftime("%Y%m%d")


def _to_iso_date(value: str) -> str:
    """把 Tushare 日期转换为 ISO 日期。"""

    return pd.Timestamp(str(value)).strftime("%Y-%m-%d")
