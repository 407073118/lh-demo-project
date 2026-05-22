"""LH Quant 的数据库表结构定义。"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
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

instruments = Table(
    "instruments",
    metadata,
    Column("symbol", String(32), primary_key=True),
    Column("name", String(128), nullable=False),
    Column("exchange", String(16), nullable=False),
    Column("asset_type", String(32), nullable=False, default="stock"),
    Column("list_date", Date, nullable=True),
    Column("delist_date", Date, nullable=True),
    Column("status", String(32), nullable=False, default="active"),
    Column("source", String(64), nullable=False),
    Column("source_updated_at", DateTime, nullable=True),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
)

trading_calendar = Table(
    "trading_calendar",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("exchange", String(16), nullable=False),
    Column("trade_date", Date, nullable=False),
    Column("is_open", Boolean, nullable=False),
    Column("pretrade_date", Date, nullable=True),
    Column("source", String(64), nullable=False),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    UniqueConstraint(
        "exchange",
        "trade_date",
        name="uq_trading_calendar_identity",
    ),
)

corporate_actions = Table(
    "corporate_actions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("symbol", String(32), nullable=False),
    Column("event_date", Date, nullable=False),
    Column("action_type", String(64), nullable=False),
    Column("value", Float(53), nullable=True),
    Column("source", String(64), nullable=False),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    UniqueConstraint(
        "symbol",
        "event_date",
        "action_type",
        "source",
        name="uq_corporate_actions_identity",
    ),
)

sync_jobs = Table(
    "sync_jobs",
    metadata,
    Column("job_id", String(64), primary_key=True),
    Column("job_type", String(64), nullable=False),
    Column("provider", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("progress", Float(53), nullable=False, default=0),
    Column("started_at", DateTime, nullable=False, server_default=func.now()),
    Column("completed_at", DateTime, nullable=True),
    Column("params", JSON, nullable=False),
    Column("message", String(512), nullable=True),
    Column("error", String(1024), nullable=True),
)

factor_definitions = Table(
    "factor_definitions",
    metadata,
    Column("factor_id", String(128), primary_key=True),
    Column("name", String(128), nullable=False),
    Column("category", String(64), nullable=False),
    Column("frequency", String(16), nullable=False),
    Column("direction", String(32), nullable=False),
    Column("formula", String(1024), nullable=False),
    Column("source", String(64), nullable=False),
    Column("license", String(128), nullable=False),
    Column("status", String(32), nullable=False),
    Column("description", String(1024), nullable=False),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
)

factor_values = Table(
    "factor_values",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("factor_id", String(128), nullable=False),
    Column("symbol", String(32), nullable=False),
    Column("trade_date", Date, nullable=False),
    Column("value", Float(53), nullable=False),
    Column("source", String(64), nullable=False),
    Column("version", String(128), nullable=False),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    UniqueConstraint(
        "factor_id",
        "symbol",
        "trade_date",
        "source",
        "version",
        name="uq_factor_values_identity",
    ),
)

factor_runs = Table(
    "factor_runs",
    metadata,
    Column("run_id", String(64), primary_key=True),
    Column("factor_id", String(128), nullable=False),
    Column("provider", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("start_date", Date, nullable=True),
    Column("end_date", Date, nullable=True),
    Column("row_count", Integer, nullable=False, default=0),
    Column("message", String(512), nullable=True),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
)

strategy_sources = Table(
    "strategy_sources",
    metadata,
    Column("source_id", String(128), primary_key=True),
    Column("name", String(128), nullable=False),
    Column("source_type", String(64), nullable=False),
    Column("url", String(1024), nullable=True),
    Column("license", String(128), nullable=False),
    Column("sync_policy", String(128), nullable=False),
    Column("executable", Boolean, nullable=False, default=False),
    Column("review_status", String(64), nullable=False),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
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
Index("ix_trading_calendar_query", trading_calendar.c.exchange, trading_calendar.c.trade_date)
Index("ix_sync_jobs_status", sync_jobs.c.status, sync_jobs.c.started_at)
Index(
    "ix_factor_values_query",
    factor_values.c.factor_id,
    factor_values.c.symbol,
    factor_values.c.trade_date,
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
    Column("data_source_detail", String(256), nullable=True),
    Column("data_version", String(128), nullable=True),
    Column("strategy_version", String(128), nullable=True),
    Column("engine_version", String(128), nullable=True),
    Column("engine_assumptions", JSON, nullable=True),
    Column("run_inputs", JSON, nullable=True),
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
