from __future__ import annotations

from pathlib import Path

from sqlalchemy import update
from sqlalchemy import text
from sqlalchemy.engine import make_url

from lh_quant.backtest.engine import run_signal_backtest
from lh_quant.data.sample import generate_sample_bars
from lh_quant.storage.database import (
    _server_url_without_database,
    create_database_engine,
    initialize_database,
)
from lh_quant.storage.repository import (
    list_backtest_runs,
    load_backtest_run_detail,
    load_market_bars,
    save_backtest_run,
    save_market_bars,
)
from lh_quant.storage.schema import (
    backtest_equity_points,
    backtest_runs,
    backtest_signals,
    backtest_trades,
    corporate_actions,
    factor_definitions,
    factor_runs,
    factor_values,
    instruments,
    market_bars,
    market_data_ingestions,
    metadata,
    strategy_sources,
    sync_jobs,
    trading_calendar,
)
from lh_quant.strategies.moving_average import moving_average_cross_signals


def test_storage_saves_and_loads_market_bars(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}")
    initialize_database(engine)
    bars = generate_sample_bars(symbol="000001", periods=12)

    saved_rows = save_market_bars(
        engine=engine,
        bars=bars,
        provider="AKShare",
        symbol="000001",
        frequency="1d",
        adjust="qfq",
    )
    loaded = load_market_bars(
        engine=engine,
        provider="AKShare",
        symbol="000001",
        frequency="1d",
        adjust="qfq",
        start=str(bars["datetime"].min().date()),
        end=str(bars["datetime"].max().date()),
    )

    assert saved_rows == 12
    assert loaded is not None
    assert len(loaded) == 12
    assert loaded["symbol"].tolist() == ["000001"] * 12
    assert loaded["close"].tolist() == bars["close"].tolist()


def test_storage_persists_market_data_lineage(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}")
    initialize_database(engine)
    bars = generate_sample_bars(symbol="000001", periods=12)

    save_market_bars(
        engine=engine,
        bars=bars,
        provider="AKShare",
        symbol="000001",
        frequency="1d",
        adjust="qfq",
        requested_provider="auto",
        source_detail="AKShare 测试接口",
        raw_symbol="000001",
        normalized_symbol="000001",
        data_version="akshare:test",
        fetched_at="2024-01-01T00:00:00+00:00",
        fallback_chain=[{"provider": "AKShare", "status": "succeeded"}],
    )

    with engine.begin() as connection:
        row = connection.execute(market_data_ingestions.select()).mappings().first()

    assert row["requested_provider"] == "auto"
    assert row["provider"] == "AKShare"
    assert row["source_detail"] == "AKShare 测试接口"
    assert row["raw_symbol"] == "000001"
    assert row["normalized_symbol"] == "000001"
    assert row["data_version"] == "akshare:test"
    assert row["fallback_chain"][0]["provider"] == "AKShare"


def test_market_bars_numeric_columns_use_double_precision() -> None:
    """行情价格和成交量必须用双精度，避免 MySQL FLOAT 把大成交量四舍五入。"""

    assert market_bars.c.open.type.precision == 53
    assert market_bars.c.high.type.precision == 53
    assert market_bars.c.low.type.precision == 53
    assert market_bars.c.close.type.precision == 53
    assert market_bars.c.volume.type.precision == 53


def test_storage_schema_includes_quant_platform_foundation_tables() -> None:
    expected_tables = {
        "instruments",
        "trading_calendar",
        "corporate_actions",
        "sync_jobs",
        "factor_definitions",
        "factor_values",
        "factor_runs",
        "strategy_sources",
    }

    assert expected_tables <= set(metadata.tables)
    assert "uq_trading_calendar_identity" in {
        constraint.name for constraint in trading_calendar.constraints
    }
    assert "uq_factor_values_identity" in {
        constraint.name for constraint in factor_values.constraints
    }
    assert instruments.c.symbol.primary_key
    assert corporate_actions.c.source.nullable is False
    assert sync_jobs.c.status.nullable is False
    assert factor_definitions.c.factor_id.primary_key
    assert factor_runs.c.status.nullable is False
    assert strategy_sources.c.review_status.nullable is False


def test_storage_rejects_cache_when_saved_range_does_not_cover_request(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}")
    initialize_database(engine)
    bars = generate_sample_bars(symbol="000001", periods=60)

    save_market_bars(
        engine=engine,
        bars=bars,
        provider="AKShare",
        symbol="000001",
        frequency="1d",
        adjust="qfq",
    )

    loaded = load_market_bars(
        engine=engine,
        provider="AKShare",
        symbol="000001",
        frequency="1d",
        adjust="qfq",
        start="2024-01-01",
        end="2024-06-30",
    )

    assert loaded is None


def test_storage_accepts_cache_when_ingestion_range_covers_request(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}")
    initialize_database(engine)
    bars = generate_sample_bars(symbol="000001", periods=60)

    save_market_bars(
        engine=engine,
        bars=bars,
        provider="AKShare",
        symbol="000001",
        frequency="1d",
        adjust="qfq",
        requested_start="2024-01-01",
        requested_end="2024-06-30",
    )

    loaded = load_market_bars(
        engine=engine,
        provider="AKShare",
        symbol="000001",
        frequency="1d",
        adjust="qfq",
        start="2024-02-01",
        end="2024-03-31",
    )

    assert loaded is not None
    assert len(loaded) > 0


def test_mysql_server_url_removes_database_before_create_database() -> None:
    url = make_url("mysql+pymysql://root:123456@localhost:3306/lh_quant?charset=utf8mb4")

    server_url = _server_url_without_database(url)

    assert server_url.database == ""
    assert "/lh_quant" not in str(server_url)
    assert "charset=utf8mb4" in str(server_url)


def test_initialize_database_adds_missing_nullable_columns_to_existing_tables(
    tmp_path: Path,
) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE backtest_runs (
                    run_id VARCHAR(64) PRIMARY KEY,
                    symbol VARCHAR(32) NOT NULL,
                    strategy_id VARCHAR(64) NOT NULL,
                    strategy_name VARCHAR(128) NOT NULL,
                    provider VARCHAR(64) NOT NULL,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    params JSON NOT NULL,
                    metrics JSON NOT NULL,
                    logs JSON NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

    initialize_database(engine)

    with engine.begin() as connection:
        columns = {
            row["name"]
            for row in connection.execute(text("PRAGMA table_info(backtest_runs)")).mappings()
        }

    assert {
        "data_source_detail",
        "data_version",
        "requested_provider",
        "fallback_chain",
        "strategy_version",
        "engine_version",
        "engine_assumptions",
        "run_inputs",
    } <= columns


def test_storage_saves_backtest_run_summary(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}")
    initialize_database(engine)
    bars = generate_sample_bars(symbol="000001", periods=80)
    signals = moving_average_cross_signals(bars, fast_window=5, slow_window=20)
    result = run_signal_backtest(bars, signals, cash=100_000)

    run_id = save_backtest_run(
        engine=engine,
        symbol="000001",
        strategy_id="moving_average",
        strategy_name="双均线策略",
        provider="AKShare",
        start="2024-01-01",
        end="2024-06-30",
        params={"fastWindow": 5, "slowWindow": 20, "cash": 100_000},
        metrics=result.metrics,
        logs=["回测完成"],
    )
    runs = list_backtest_runs(engine=engine, limit=5)

    assert run_id.startswith("bt_")
    assert runs[0]["runId"] == run_id
    assert runs[0]["symbol"] == "000001"
    assert runs[0]["strategyName"] == "双均线策略"
    assert runs[0]["metrics"]["trade_count"] == result.metrics["trade_count"]


def test_storage_saves_backtest_run_lineage(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}")
    initialize_database(engine)
    bars = generate_sample_bars(symbol="000001", periods=80)
    signals = moving_average_cross_signals(bars, fast_window=5, slow_window=20)
    result = run_signal_backtest(bars, signals, cash=100_000)

    run_id = save_backtest_run(
        engine=engine,
        symbol="000001",
        strategy_id="moving_average",
        strategy_name="双均线策略",
        provider="AKShare",
        requested_provider="auto",
        start="2024-01-01",
        end="2024-06-30",
        params={"fastWindow": 5, "slowWindow": 20, "cash": 100_000},
        metrics=result.metrics,
        logs=["回测完成"],
        data_source_detail="AKShare 测试接口",
        data_version="akshare:test",
        fallback_chain=[{"provider": "AKShare", "status": "succeeded"}],
    )

    detail = load_backtest_run_detail(engine, run_id)

    assert detail is not None
    assert detail["summary"]["requestedProvider"] == "auto"
    assert detail["summary"]["actualProvider"] == "AKShare"
    assert detail["summary"]["fallbackChain"][0]["provider"] == "AKShare"


def test_storage_lists_backtest_runs_with_stable_tiebreaker(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}")
    initialize_database(engine)
    bars = generate_sample_bars(symbol="000001", periods=80)
    signals = moving_average_cross_signals(bars, fast_window=5, slow_window=20)
    result = run_signal_backtest(bars, signals, cash=100_000)
    run_ids = [
        save_backtest_run(
            engine=engine,
            symbol="000001",
            strategy_id="moving_average",
            strategy_name="双均线策略",
            provider="AKShare",
            start="2024-01-01",
            end="2024-06-30",
            params={"fastWindow": 5, "slowWindow": 20, "cash": 100_000},
            metrics=result.metrics,
            logs=["回测完成"],
        )
        for _ in range(2)
    ]

    with engine.begin() as connection:
        created_at = connection.execute(
            backtest_runs.select().where(backtest_runs.c.run_id == run_ids[0])
        ).mappings().first()["created_at"]
        connection.execute(update(backtest_runs).values(created_at=created_at))

    runs = list_backtest_runs(engine=engine, limit=5)

    assert [run["runId"] for run in runs[:2]] == sorted(run_ids, reverse=True)


def test_storage_saves_backtest_run_artifacts(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}")
    initialize_database(engine)
    bars = generate_sample_bars(symbol="000001", periods=80)
    signals = moving_average_cross_signals(bars, fast_window=5, slow_window=20)
    result = run_signal_backtest(bars, signals, cash=100_000)

    run_id = save_backtest_run(
        engine=engine,
        symbol="000001",
        strategy_id="moving_average",
        strategy_name="双均线策略",
        provider="AKShare",
        start="2024-01-01",
        end="2024-06-30",
        params={"fastWindow": 5, "slowWindow": 20, "cash": 100_000},
        metrics=result.metrics,
        logs=["回测完成"],
        trades=result.trades,
        equity_curve=result.equity_curve,
        signals=signals,
        bars=bars,
    )

    with engine.begin() as connection:
        trade_rows = connection.execute(backtest_trades.select()).mappings().all()
        equity_rows = connection.execute(backtest_equity_points.select()).mappings().all()
        signal_rows = connection.execute(backtest_signals.select()).mappings().all()

    assert all(row["run_id"] == run_id for row in trade_rows)
    assert len(equity_rows) == len(result.equity_curve)
    assert len(signal_rows) == int((signals != 0).sum())


def test_storage_loads_backtest_run_detail_with_artifacts(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}")
    initialize_database(engine)
    bars = generate_sample_bars(symbol="000001", periods=80)
    signals = moving_average_cross_signals(bars, fast_window=5, slow_window=20)
    result = run_signal_backtest(bars, signals, cash=100_000)
    run_id = save_backtest_run(
        engine=engine,
        symbol="000001",
        strategy_id="moving_average",
        strategy_name="双均线策略",
        provider="AKShare",
        start="2024-01-01",
        end="2024-06-30",
        params={"fastWindow": 5, "slowWindow": 20, "cash": 100_000},
        metrics=result.metrics,
        logs=["回测完成"],
        trades=result.trades,
        equity_curve=result.equity_curve,
        signals=signals,
        bars=bars,
    )

    detail = load_backtest_run_detail(engine, run_id)

    assert detail is not None
    assert detail["runId"] == run_id
    assert detail["summary"]["symbol"] == "000001"
    assert len(detail["equityCurve"]) == len(result.equity_curve)
    assert len(detail["signals"]) == int((signals != 0).sum())
    assert detail["trades"]
