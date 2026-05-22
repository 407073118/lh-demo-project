"""数据资产、交易日历、同步任务和因子的数据库读写函数。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import uuid4

import pandas as pd
from sqlalchemy import Engine, delete, func, insert, select, update

from lh_quant.storage.schema import (
    factor_definitions,
    market_bars,
    market_data_ingestions,
    sync_jobs,
    trading_calendar,
)

CoverageStatus = Literal["complete", "missing", "unknown"]


@dataclass(frozen=True)
class CoverageReport:
    """行情缓存覆盖率检查结果。"""

    status: CoverageStatus
    expected_rows: int | None
    actual_rows: int
    missing_dates: list[str]
    last_trade_date: str | None

    def to_json(self) -> dict[str, Any]:
        """转换为 API 使用的驼峰 JSON。"""

        return {
            "status": self.status,
            "expectedRows": self.expected_rows,
            "actualRows": self.actual_rows,
            "missingDates": self.missing_dates,
            "lastTradeDate": self.last_trade_date,
        }


def upsert_trading_calendar(engine: Engine, records: list[dict[str, Any]]) -> int:
    """按交易所和日期写入或替换交易日历。"""

    if not records:
        return 0
    normalized = [_calendar_record(record) for record in records]
    with engine.begin() as connection:
        for record in normalized:
            connection.execute(
                delete(trading_calendar).where(
                    trading_calendar.c.exchange == record["exchange"],
                    trading_calendar.c.trade_date == record["trade_date"],
                )
            )
        connection.execute(insert(trading_calendar), normalized)
    return len(normalized)


def get_open_trade_dates(engine: Engine, exchange: str, start: str, end: str) -> list[date]:
    """读取指定区间内开市的交易日。"""

    statement = (
        select(trading_calendar.c.trade_date)
        .where(
            trading_calendar.c.exchange == exchange,
            trading_calendar.c.trade_date >= _to_date(start),
            trading_calendar.c.trade_date <= _to_date(end),
            trading_calendar.c.is_open.is_(True),
        )
        .order_by(trading_calendar.c.trade_date)
    )
    with engine.begin() as connection:
        return [row[0] for row in connection.execute(statement).all()]


def inspect_market_bar_coverage(
    engine: Engine,
    provider: str,
    symbol: str,
    exchange: str,
    frequency: str,
    adjust: str,
    start: str,
    end: str,
) -> CoverageReport:
    """按交易日历检查本地行情缓存是否完整。"""

    start_date = _to_date(start)
    end_date = _to_date(end)
    trade_dates = get_open_trade_dates(engine, exchange=exchange, start=start, end=end)
    actual_dates = _market_bar_dates(
        engine,
        provider=provider,
        symbol=symbol,
        frequency=frequency,
        adjust=adjust,
        start=start_date,
        end=end_date,
    )

    if not trade_dates:
        return CoverageReport(
            status="unknown",
            expected_rows=None,
            actual_rows=len(actual_dates),
            missing_dates=[],
            last_trade_date=max(actual_dates).isoformat() if actual_dates else None,
        )

    actual_set = set(actual_dates)
    missing = [trade_date for trade_date in trade_dates if trade_date not in actual_set]
    return CoverageReport(
        status="complete" if not missing else "missing",
        expected_rows=len(trade_dates),
        actual_rows=len(actual_dates),
        missing_dates=[trade_date.isoformat() for trade_date in missing],
        last_trade_date=max(actual_dates).isoformat() if actual_dates else None,
    )


def create_sync_job(
    engine: Engine,
    job_type: str,
    provider: str,
    params: dict[str, Any],
) -> str:
    """创建一个数据同步任务记录。"""

    job_id = f"sync_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
    with engine.begin() as connection:
        connection.execute(
            insert(sync_jobs).values(
                job_id=job_id,
                job_type=job_type,
                provider=provider,
                status="queued",
                progress=0.0,
                params=params,
                message=None,
                error=None,
            )
        )
    return job_id


def update_sync_job(
    engine: Engine,
    job_id: str,
    status: str,
    progress: float,
    message: str | None = None,
    error: str | None = None,
) -> None:
    """更新同步任务的状态、进度和错误信息。"""

    values: dict[str, Any] = {
        "status": status,
        "progress": progress,
        "message": message,
        "error": error,
    }
    if status in {"succeeded", "failed", "canceled"}:
        values["completed_at"] = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(update(sync_jobs).where(sync_jobs.c.job_id == job_id).values(**values))


def upsert_factor_definitions(engine: Engine, definitions: list[dict[str, Any]]) -> int:
    """写入或替换因子定义。"""

    if not definitions:
        return 0
    normalized = [_factor_definition_record(definition) for definition in definitions]
    with engine.begin() as connection:
        for definition in normalized:
            connection.execute(
                delete(factor_definitions).where(
                    factor_definitions.c.factor_id == definition["factor_id"]
                )
            )
        connection.execute(insert(factor_definitions), normalized)
    return len(normalized)


def list_factor_definitions(engine: Engine) -> list[dict[str, Any]]:
    """按因子 ID 返回已持久化的因子定义。"""

    statement = select(factor_definitions).order_by(factor_definitions.c.factor_id)
    with engine.begin() as connection:
        rows = connection.execute(statement).mappings().all()
    return [_factor_definition_to_json(row) for row in rows]


def list_data_assets(engine: Engine) -> list[dict[str, Any]]:
    """汇总当前数据库中的数据资产状态。"""

    with engine.begin() as connection:
        bar_count = connection.execute(select(func.count()).select_from(market_bars)).scalar_one()
        ingestion = (
            connection.execute(
                select(market_data_ingestions).order_by(
                    market_data_ingestions.c.created_at.desc(),
                    market_data_ingestions.c.id.desc(),
                )
            )
            .mappings()
            .first()
        )
        factor_count = connection.execute(
            select(func.count()).select_from(factor_definitions)
        ).scalar_one()

    last_sync = ingestion["created_at"].isoformat(sep=" ") if ingestion else None
    coverage = (
        f"{ingestion['start_date']} to {ingestion['end_date']}"
        if ingestion
        else "No local bars yet"
    )
    return [
        {
            "id": "a_share_daily_bars",
            "name": "A-share daily bars",
            "provider": ingestion["provider"] if ingestion else "AKShare",
            "status": "available" if bar_count else "preview",
            "coverage": coverage,
            "lastSync": last_sync,
            "quality": _quality_json(
                "unknown",
                None,
                "Calendar-aware quality requires synced calendar.",
            ),
            "rowCount": int(bar_count),
            "fields": ["open", "high", "low", "close", "volume"],
        },
        {
            "id": "local_factors",
            "name": "Local factor library",
            "provider": "local",
            "status": "available" if factor_count else "preview",
            "coverage": "Computed from local market bars",
            "lastSync": None,
            "quality": _quality_json(
                "unknown",
                None,
                "Factor values are computed on demand in P0.",
            ),
            "rowCount": int(factor_count),
            "fields": ["factor_id", "symbol", "trade_date", "value"],
        },
    ]


def get_data_asset_detail(engine: Engine, asset_id: str) -> dict[str, Any] | None:
    """读取单个数据资产详情和最近同步任务。"""

    assets = {asset["id"]: asset for asset in list_data_assets(engine)}
    asset = assets.get(asset_id)
    if asset is None:
        return None

    with engine.begin() as connection:
        jobs = (
            connection.execute(
                select(sync_jobs)
                .order_by(sync_jobs.c.started_at.desc())
                .limit(10)
            )
            .mappings()
            .all()
        )

    return {
        **asset,
        "description": _asset_description(asset_id),
        "syncJobs": [_sync_job_to_json(row) for row in jobs],
    }


def _market_bar_dates(
    engine: Engine,
    provider: str,
    symbol: str,
    frequency: str,
    adjust: str,
    start: date,
    end: date,
) -> list[date]:
    """读取本地行情表中已有的交易日期。"""

    statement = (
        select(market_bars.c.trade_date)
        .where(
            market_bars.c.provider == provider,
            market_bars.c.symbol == symbol,
            market_bars.c.frequency == frequency,
            market_bars.c.adjust == (adjust or ""),
            market_bars.c.trade_date >= start,
            market_bars.c.trade_date <= end,
        )
        .order_by(market_bars.c.trade_date)
    )
    with engine.begin() as connection:
        return [row[0] for row in connection.execute(statement).all()]


def _calendar_record(record: dict[str, Any]) -> dict[str, Any]:
    """规范化交易日历入库记录。"""

    return {
        "exchange": str(record["exchange"]),
        "trade_date": _to_date(record["trade_date"]),
        "is_open": bool(record["is_open"]),
        "pretrade_date": _optional_date(record.get("pretrade_date")),
        "source": str(record["source"]),
    }


def _factor_definition_record(definition: dict[str, Any]) -> dict[str, Any]:
    """规范化因子定义入库记录。"""

    return {
        "factor_id": str(definition["factor_id"]),
        "name": str(definition["name"]),
        "category": str(definition["category"]),
        "frequency": str(definition["frequency"]),
        "direction": str(definition["direction"]),
        "formula": str(definition["formula"]),
        "source": str(definition["source"]),
        "license": str(definition["license"]),
        "status": str(definition["status"]),
        "description": str(definition["description"]),
    }


def _factor_definition_to_json(row: Any) -> dict[str, Any]:
    """把因子定义数据库行转换成 API JSON。"""

    return {
        "factorId": row["factor_id"],
        "name": row["name"],
        "category": row["category"],
        "frequency": row["frequency"],
        "direction": row["direction"],
        "formula": row["formula"],
        "source": row["source"],
        "license": row["license"],
        "status": row["status"],
        "description": row["description"],
    }


def _sync_job_to_json(row: Any) -> dict[str, Any]:
    """把同步任务数据库行转换成 API JSON。"""

    return {
        "jobId": row["job_id"],
        "jobType": row["job_type"],
        "provider": row["provider"],
        "status": row["status"],
        "progress": row["progress"],
        "startedAt": row["started_at"].isoformat(sep=" ") if row["started_at"] else None,
        "completedAt": row["completed_at"].isoformat(sep=" ") if row["completed_at"] else None,
        "params": row["params"],
        "message": row["message"],
        "error": row["error"],
    }


def _quality_json(status: CoverageStatus, score: float | None, message: str) -> dict[str, Any]:
    """构造数据质量摘要。"""

    return {"status": status, "score": score, "message": message}


def _asset_description(asset_id: str) -> str:
    """返回数据资产的人类可读说明。"""

    descriptions = {
        "a_share_daily_bars": (
            "Daily OHLCV bars persisted from the configured market data provider."
        ),
        "local_factors": "Local factor definitions and computed factor values.",
    }
    return descriptions.get(asset_id, "")


def _to_date(value: Any) -> date:
    """把输入值转换为日期对象。"""

    return pd.Timestamp(value).date()


def _optional_date(value: Any) -> date | None:
    """把可空输入值转换为日期对象。"""

    if value in {None, ""}:
        return None
    return _to_date(value)
