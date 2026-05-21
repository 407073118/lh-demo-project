"""LH Quant 的数据库表结构定义。"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    func,
)

metadata = MetaData()

market_bars = Table(
    "market_bars",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("provider", String(64), nullable=False),
    Column("symbol", String(32), nullable=False),
    Column("frequency", String(16), nullable=False),
    Column("adjust", String(16), nullable=False, default=""),
    Column("trade_date", Date, nullable=False),
    Column("open", Float(53), nullable=False),
    Column("high", Float(53), nullable=False),
    Column("low", Float(53), nullable=False),
    Column("close", Float(53), nullable=False),
    Column("volume", Float(53), nullable=False),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    UniqueConstraint(
        "provider",
        "symbol",
        "frequency",
        "adjust",
        "trade_date",
        name="uq_market_bars_identity",
    ),
)

market_data_ingestions = Table(
    "market_data_ingestions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("provider", String(64), nullable=False),
    Column("symbol", String(32), nullable=False),
    Column("frequency", String(16), nullable=False),
    Column("adjust", String(16), nullable=False, default=""),
    Column("start_date", Date, nullable=False),
    Column("end_date", Date, nullable=False),
    Column("row_count", Integer, nullable=False),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    UniqueConstraint(
        "provider",
        "symbol",
        "frequency",
        "adjust",
        "start_date",
        "end_date",
        name="uq_market_data_ingestions_range",
    ),
)

Index(
    "ix_market_bars_query",
    market_bars.c.provider,
    market_bars.c.symbol,
    market_bars.c.trade_date,
)

Index(
    "ix_market_data_ingestions_query",
    market_data_ingestions.c.provider,
    market_data_ingestions.c.symbol,
    market_data_ingestions.c.start_date,
    market_data_ingestions.c.end_date,
)

backtest_runs = Table(
    "backtest_runs",
    metadata,
    Column("run_id", String(64), primary_key=True),
    Column("symbol", String(32), nullable=False),
    Column("strategy_id", String(64), nullable=False),
    Column("strategy_name", String(128), nullable=False),
    Column("provider", String(64), nullable=False),
    Column("start_date", Date, nullable=False),
    Column("end_date", Date, nullable=False),
    Column("params", JSON, nullable=False),
    Column("metrics", JSON, nullable=False),
    Column("logs", JSON, nullable=False),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
)

Index("ix_backtest_runs_created_at", backtest_runs.c.created_at)

backtest_trades = Table(
    "backtest_trades",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(64), nullable=False),
    Column("trade_date", Date, nullable=False),
    Column("side", String(16), nullable=False),
    Column("price", Float(53), nullable=False),
    Column("quantity", Float(53), nullable=False),
    Column("amount", Float(53), nullable=False),
    Column("commission", Float(53), nullable=False),
)

backtest_equity_points = Table(
    "backtest_equity_points",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(64), nullable=False),
    Column("trade_date", Date, nullable=False),
    Column("cash", Float(53), nullable=False),
    Column("position", Float(53), nullable=False),
    Column("price", Float(53), nullable=False),
    Column("equity", Float(53), nullable=False),
)

backtest_signals = Table(
    "backtest_signals",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(64), nullable=False),
    Column("trade_date", Date, nullable=False),
    Column("signal", Integer, nullable=False),
    Column("price", Float(53), nullable=False),
)

Index("ix_backtest_trades_run_id", backtest_trades.c.run_id)
Index("ix_backtest_equity_points_run_id", backtest_equity_points.c.run_id)
Index("ix_backtest_signals_run_id", backtest_signals.c.run_id)
