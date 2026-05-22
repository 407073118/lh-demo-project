from __future__ import annotations

from pathlib import Path

from lh_quant.data.sample import generate_sample_bars
from lh_quant.storage.data_repository import (
    CoverageReport,
    create_sync_job,
    get_open_trade_dates,
    inspect_market_bar_coverage,
    list_factor_definitions,
    update_sync_job,
    upsert_factor_definitions,
    upsert_trading_calendar,
)
from lh_quant.storage.database import create_database_engine, initialize_database
from lh_quant.storage.repository import save_market_bars


def _engine(tmp_path: Path):
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}")
    initialize_database(engine)
    return engine


def test_trading_calendar_upsert_and_open_dates(tmp_path: Path) -> None:
    engine = _engine(tmp_path)

    count = upsert_trading_calendar(
        engine,
        [
            {"exchange": "SSE", "trade_date": "2024-01-02", "is_open": True, "source": "test"},
            {"exchange": "SSE", "trade_date": "2024-01-03", "is_open": False, "source": "test"},
            {"exchange": "SSE", "trade_date": "2024-01-04", "is_open": True, "source": "test"},
        ],
    )
    dates = get_open_trade_dates(engine, exchange="SSE", start="2024-01-01", end="2024-01-05")

    assert count == 3
    assert [date.isoformat() for date in dates] == ["2024-01-02", "2024-01-04"]


def test_market_bar_coverage_detects_missing_trading_day(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    upsert_trading_calendar(
        engine,
        [
            {"exchange": "SSE", "trade_date": "2024-01-02", "is_open": True, "source": "test"},
            {"exchange": "SSE", "trade_date": "2024-01-03", "is_open": True, "source": "test"},
        ],
    )
    bars = generate_sample_bars(symbol="600519", periods=1).assign(datetime=["2024-01-02"])
    save_market_bars(
        engine,
        bars,
        provider="AKShare",
        symbol="600519",
        frequency="1d",
        adjust="qfq",
        requested_start="2024-01-02",
        requested_end="2024-01-03",
    )

    coverage = inspect_market_bar_coverage(
        engine,
        provider="AKShare",
        symbol="600519",
        exchange="SSE",
        frequency="1d",
        adjust="qfq",
        start="2024-01-02",
        end="2024-01-03",
    )

    assert coverage == CoverageReport(
        status="missing",
        expected_rows=2,
        actual_rows=1,
        missing_dates=["2024-01-03"],
        last_trade_date="2024-01-02",
    )


def test_market_bar_coverage_is_unknown_without_calendar(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    bars = generate_sample_bars(symbol="000001", periods=2)
    save_market_bars(
        engine,
        bars,
        provider="AKShare",
        symbol="000001",
        frequency="1d",
        adjust="qfq",
        requested_start=str(bars["datetime"].min().date()),
        requested_end=str(bars["datetime"].max().date()),
    )

    coverage = inspect_market_bar_coverage(
        engine,
        provider="AKShare",
        symbol="000001",
        exchange="SZSE",
        frequency="1d",
        adjust="qfq",
        start=str(bars["datetime"].min().date()),
        end=str(bars["datetime"].max().date()),
    )

    assert coverage.status == "unknown"
    assert coverage.expected_rows is None
    assert coverage.actual_rows == 2


def test_sync_jobs_and_factor_definitions_round_trip(tmp_path: Path) -> None:
    engine = _engine(tmp_path)

    job_id = create_sync_job(
        engine,
        job_type="calendar",
        provider="Tushare",
        params={"start": "2024-01-01", "end": "2024-01-31"},
    )
    update_sync_job(engine, job_id, status="succeeded", progress=1, message="done")
    count = upsert_factor_definitions(
        engine,
        [
            {
                "factor_id": "return_20d",
                "name": "20 day return",
                "category": "return",
                "frequency": "1d",
                "direction": "positive",
                "formula": "close / close.shift(20) - 1",
                "source": "local",
                "license": "internal",
                "status": "available",
                "description": "Trailing 20 day return.",
            }
        ],
    )
    factors = list_factor_definitions(engine)

    assert job_id.startswith("sync_")
    assert count == 1
    assert factors[0]["factorId"] == "return_20d"
