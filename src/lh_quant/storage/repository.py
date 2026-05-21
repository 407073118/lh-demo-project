"""行情缓存和回测运行记录的数据库读写函数。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
from sqlalchemy import Engine, delete, desc, insert, select

from lh_quant.data.schema import validate_bars
from lh_quant.storage.schema import (
    backtest_equity_points,
    backtest_runs,
    backtest_signals,
    backtest_trades,
    market_bars,
    market_data_ingestions,
)


def save_market_bars(
    engine: Engine,
    bars: pd.DataFrame,
    provider: str,
    symbol: str,
    frequency: str,
    adjust: str,
    requested_start: str | None = None,
    requested_end: str | None = None,
) -> int:
    """保存标准 K线数据和本次下载覆盖区间，供后续缓存完整性校验。"""

    if bars.empty:
        return 0

    normalized = validate_bars(bars.assign(symbol=symbol))
    records = [
        {
            "provider": provider,
            "symbol": symbol,
            "frequency": frequency,
            "adjust": adjust or "",
            "trade_date": pd.Timestamp(row.datetime).date(),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
            "volume": float(row.volume),
        }
        for row in normalized.itertuples(index=False)
    ]
    trade_dates = [record["trade_date"] for record in records]
    ingestion_start = pd.Timestamp(requested_start).date() if requested_start else min(trade_dates)
    ingestion_end = pd.Timestamp(requested_end).date() if requested_end else max(trade_dates)

    with engine.begin() as connection:
        connection.execute(
            delete(market_bars).where(
                market_bars.c.provider == provider,
                market_bars.c.symbol == symbol,
                market_bars.c.frequency == frequency,
                market_bars.c.adjust == (adjust or ""),
                market_bars.c.trade_date.in_(trade_dates),
            )
        )
        connection.execute(insert(market_bars), records)
        connection.execute(
            delete(market_data_ingestions).where(
                market_data_ingestions.c.provider == provider,
                market_data_ingestions.c.symbol == symbol,
                market_data_ingestions.c.frequency == frequency,
                market_data_ingestions.c.adjust == (adjust or ""),
                market_data_ingestions.c.start_date == ingestion_start,
                market_data_ingestions.c.end_date == ingestion_end,
            )
        )
        connection.execute(
            insert(market_data_ingestions).values(
                provider=provider,
                symbol=symbol,
                frequency=frequency,
                adjust=adjust or "",
                start_date=ingestion_start,
                end_date=ingestion_end,
                row_count=len(records),
            )
        )

    return len(records)


def load_market_bars(
    engine: Engine,
    provider: str,
    symbol: str,
    frequency: str,
    adjust: str,
    start: str,
    end: str,
) -> pd.DataFrame | None:
    """按数据身份读取完整覆盖请求区间的 K线缓存，没有完整命中时返回空值。"""

    start_date = pd.Timestamp(start).date()
    end_date = pd.Timestamp(end).date()
    coverage_statement = (
        select(market_data_ingestions.c.id)
        .where(
            market_data_ingestions.c.provider == provider,
            market_data_ingestions.c.symbol == symbol,
            market_data_ingestions.c.frequency == frequency,
            market_data_ingestions.c.adjust == (adjust or ""),
            market_data_ingestions.c.start_date <= start_date,
            market_data_ingestions.c.end_date >= end_date,
        )
        .limit(1)
    )
    statement = (
        select(
            market_bars.c.symbol,
            market_bars.c.trade_date,
            market_bars.c.open,
            market_bars.c.high,
            market_bars.c.low,
            market_bars.c.close,
            market_bars.c.volume,
        )
        .where(
            market_bars.c.provider == provider,
            market_bars.c.symbol == symbol,
            market_bars.c.frequency == frequency,
            market_bars.c.adjust == (adjust or ""),
            market_bars.c.trade_date >= start_date,
            market_bars.c.trade_date <= end_date,
        )
        .order_by(market_bars.c.trade_date)
    )

    with engine.begin() as connection:
        coverage = connection.execute(coverage_statement).first()
        if coverage is None:
            return None
        rows = connection.execute(statement).mappings().all()

    if not rows:
        return None

    bars = pd.DataFrame(
        {
            "symbol": [row["symbol"] for row in rows],
            "datetime": [row["trade_date"] for row in rows],
            "open": [row["open"] for row in rows],
            "high": [row["high"] for row in rows],
            "low": [row["low"] for row in rows],
            "close": [row["close"] for row in rows],
            "volume": [row["volume"] for row in rows],
        }
    )
    return validate_bars(bars)


def save_backtest_run(
    engine: Engine,
    symbol: str,
    strategy_id: str,
    strategy_name: str,
    provider: str,
    start: str,
    end: str,
    params: dict[str, Any],
    metrics: dict[str, Any],
    logs: list[str],
    trades: pd.DataFrame | None = None,
    equity_curve: pd.DataFrame | None = None,
    signals: pd.Series | None = None,
    bars: pd.DataFrame | None = None,
) -> str:
    """保存一次回测运行摘要和可复盘的明细数据，并返回运行编号。"""

    run_id = _new_run_id()
    with engine.begin() as connection:
        connection.execute(
            insert(backtest_runs).values(
                run_id=run_id,
                symbol=symbol,
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                provider=provider,
                start_date=pd.Timestamp(start).date(),
                end_date=pd.Timestamp(end).date(),
                params=params,
                metrics=metrics,
                logs=logs,
            )
        )
        if trades is not None and not trades.empty:
            connection.execute(insert(backtest_trades), _trade_records(run_id, trades))
        if equity_curve is not None and not equity_curve.empty:
            connection.execute(
                insert(backtest_equity_points),
                _equity_records(run_id, equity_curve),
            )
        if signals is not None and bars is not None:
            signal_records = _signal_records(run_id, signals, bars)
            if signal_records:
                connection.execute(insert(backtest_signals), signal_records)
    return run_id


def list_backtest_runs(engine: Engine, limit: int = 20) -> list[dict[str, Any]]:
    """按创建时间倒序读取最近的回测运行摘要。"""

    statement = (
        select(backtest_runs)
        .order_by(desc(backtest_runs.c.created_at), desc(backtest_runs.c.run_id))
        .limit(limit)
    )
    with engine.begin() as connection:
        rows = connection.execute(statement).mappings().all()

    return [
        {
            "runId": row["run_id"],
            "symbol": row["symbol"],
            "strategyId": row["strategy_id"],
            "strategyName": row["strategy_name"],
            "provider": row["provider"],
            "start": str(row["start_date"]),
            "end": str(row["end_date"]),
            "params": row["params"],
            "metrics": row["metrics"],
            "logs": row["logs"],
            "createdAt": row["created_at"].isoformat(sep=" "),
        }
        for row in rows
    ]


def load_backtest_run_detail(engine: Engine, run_id: str) -> dict[str, Any] | None:
    """读取一次回测运行摘要和已持久化的成交、权益、信号明细。"""

    with engine.begin() as connection:
        run = (
            connection.execute(
                select(backtest_runs).where(backtest_runs.c.run_id == run_id)
            )
            .mappings()
            .first()
        )
        if run is None:
            return None
        trade_rows = connection.execute(
            select(backtest_trades)
            .where(backtest_trades.c.run_id == run_id)
            .order_by(backtest_trades.c.trade_date, backtest_trades.c.id)
        ).mappings().all()
        equity_rows = connection.execute(
            select(backtest_equity_points)
            .where(backtest_equity_points.c.run_id == run_id)
            .order_by(backtest_equity_points.c.trade_date, backtest_equity_points.c.id)
        ).mappings().all()
        signal_rows = connection.execute(
            select(backtest_signals)
            .where(backtest_signals.c.run_id == run_id)
            .order_by(backtest_signals.c.trade_date, backtest_signals.c.id)
        ).mappings().all()

    return {
        "runId": run["run_id"],
        "summary": {
            "runId": run["run_id"],
            "symbol": run["symbol"],
            "strategyId": run["strategy_id"],
            "strategyName": run["strategy_name"],
            "provider": run["provider"],
            "start": str(run["start_date"]),
            "end": str(run["end_date"]),
            "params": run["params"],
            "metrics": run["metrics"],
            "logs": run["logs"],
            "createdAt": run["created_at"].isoformat(sep=" "),
        },
        "trades": [
            {
                "datetime": str(row["trade_date"]),
                "side": row["side"],
                "sideText": "买入" if row["side"] == "buy" else "卖出",
                "price": row["price"],
                "quantity": row["quantity"],
                "amount": row["amount"],
                "commission": row["commission"],
            }
            for row in trade_rows
        ],
        "equityCurve": [
            {
                "datetime": str(row["trade_date"]),
                "cash": row["cash"],
                "position": row["position"],
                "price": row["price"],
                "equity": row["equity"],
            }
            for row in equity_rows
        ],
        "signals": [
            {
                "datetime": str(row["trade_date"]),
                "signal": row["signal"],
                "label": "买入" if row["signal"] == 1 else "卖出",
                "price": row["price"],
            }
            for row in signal_rows
        ],
    }


def _new_run_id() -> str:
    """生成按时间排序的回测运行编号。"""

    return f"bt_{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"


def _trade_records(run_id: str, trades: pd.DataFrame) -> list[dict[str, Any]]:
    """把成交 DataFrame 转换成可以批量写入数据库的记录。"""

    return [
        {
            "run_id": run_id,
            "trade_date": pd.Timestamp(row.datetime).date(),
            "side": row.side,
            "price": float(row.price),
            "quantity": float(row.quantity),
            "amount": float(row.price * row.quantity),
            "commission": float(row.commission),
        }
        for row in trades.itertuples(index=False)
    ]


def _equity_records(run_id: str, equity_curve: pd.DataFrame) -> list[dict[str, Any]]:
    """把每日权益曲线转换成可以批量写入数据库的记录。"""

    return [
        {
            "run_id": run_id,
            "trade_date": pd.Timestamp(row.datetime).date(),
            "cash": float(row.cash),
            "position": float(row.position),
            "price": float(row.price),
            "equity": float(row.equity),
        }
        for row in equity_curve.itertuples(index=False)
    ]


def _signal_records(
    run_id: str,
    signals: pd.Series,
    bars: pd.DataFrame,
) -> list[dict[str, Any]]:
    """把非零交易信号和对应收盘价转换成数据库记录。"""

    records: list[dict[str, Any]] = []
    for index, signal in signals.items():
        if int(signal) == 0:
            continue
        row = bars.loc[index]
        records.append(
            {
                "run_id": run_id,
                "trade_date": pd.Timestamp(row["datetime"]).date(),
                "signal": int(signal),
                "price": float(row["close"]),
            }
        )
    return records
