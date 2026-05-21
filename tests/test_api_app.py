from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient

from lh_quant.data.akshare_provider import AkShareDataError
from lh_quant.data.sample import generate_sample_bars
from lh_quant.storage.database import DatabaseStatus


def test_create_app_does_not_touch_database_before_first_request(tmp_path, monkeypatch) -> None:
    from lh_quant.api import app as app_module

    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    calls: list[str | None] = []
    real_create_database_engine = app_module.create_database_engine

    def tracked_create_database_engine(url: str | None = None):
        calls.append(url)
        return real_create_database_engine(url)

    monkeypatch.setattr(app_module, "create_database_engine", tracked_create_database_engine)

    app_module.create_app(database_url=database_url)

    assert calls == []


def test_api_health_returns_chinese_platform_status(tmp_path) -> None:
    from lh_quant.api.app import create_app

    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    client = TestClient(create_app(database_url=database_url))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["name"] == "LH Quant A股研究工作台"


def test_api_lists_configurable_strategies(tmp_path) -> None:
    """策略列表接口返回可配置参数和前端校验约束。"""

    from lh_quant.api.app import create_app

    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    client = TestClient(create_app(database_url=database_url))

    response = client.get("/api/strategies")

    assert response.status_code == 200
    payload = response.json()
    assert [strategy["id"] for strategy in payload["strategies"]] == [
        "moving_average",
        "momentum_breakout",
        "rsi_reversion",
    ]
    assert payload["strategies"][0]["params"][0]["label"] == "短均线"
    assert payload["strategies"][0]["constraints"][0]["type"] == "lt"


def test_backtest_request_accepts_parseable_non_padded_dates() -> None:
    from lh_quant.api.app import BacktestRunRequest

    request = BacktestRunRequest(
        symbol="000001",
        start="2024-2-01",
        end="2024-10-01",
    )

    assert request.start == "2024-2-01"
    assert request.end == "2024-10-01"


def test_api_backtest_rejects_run_when_database_is_disconnected(tmp_path, monkeypatch) -> None:
    from lh_quant.api.app import create_app

    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"

    def fake_initialize_database_safely(_engine):
        return DatabaseStatus(connected=False, url="sqlite://", message="数据库连接失败")

    monkeypatch.setattr(
        "lh_quant.api.app.initialize_database_safely",
        fake_initialize_database_safely,
    )
    client = TestClient(create_app(database_url=database_url))

    response = client.post(
        "/api/backtests/moving-average",
        json={
            "symbol": "000001",
            "start": "2024-01-01",
            "end": "2024-06-30",
            "fastWindow": 5,
            "slowWindow": 20,
            "cash": 100000,
            "adjust": "qfq",
        },
    )

    assert response.status_code == 503
    assert "数据库未连接" in response.text


def test_api_backtest_runs_selected_strategy_from_request(tmp_path, monkeypatch) -> None:
    from lh_quant.api.app import create_app

    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    bars = generate_sample_bars(symbol="000001", periods=90)

    def fake_download_akshare_bars(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
        return bars

    monkeypatch.setattr("lh_quant.api.app.download_akshare_bars", fake_download_akshare_bars)
    client = TestClient(create_app(database_url=database_url))

    response = client.post(
        "/api/backtests/run",
        json={
            "symbol": "000001",
            "start": "2024-01-01",
            "end": "2024-06-30",
            "strategyId": "momentum_breakout",
            "strategyParams": {"lookbackWindow": 20, "exitWindow": 8},
            "cash": 100000,
            "adjust": "qfq",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy"]["id"] == "momentum_breakout"
    assert payload["strategy"]["name"] == "动量突破策略"
    assert payload["strategy"]["params"]["strategyParams"]["lookbackWindow"] == 20
    assert payload["indicatorLines"][0]["name"] == "突破上轨"


def test_api_backtest_runs_a_share_moving_average_flow(tmp_path, monkeypatch) -> None:
    from lh_quant.api.app import create_app

    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    bars = generate_sample_bars(symbol="000001", periods=90)

    def fake_download_akshare_bars(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
        assert symbol == "000001"
        assert start == "2024-01-01"
        assert end == "2024-06-30"
        assert adjust == "qfq"
        return bars

    monkeypatch.setattr("lh_quant.api.app.download_akshare_bars", fake_download_akshare_bars)
    client = TestClient(create_app(database_url=database_url))

    response = client.post(
        "/api/backtests/moving-average",
        json={
            "symbol": "000001",
            "start": "2024-01-01",
            "end": "2024-06-30",
            "fastWindow": 5,
            "slowWindow": 20,
            "cash": 100000,
            "adjust": "qfq",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "000001"
    assert payload["strategy"]["name"] == "双均线策略"
    assert payload["dataSource"]["provider"] == "AKShare"
    assert payload["dataSource"]["cached"] is False
    assert len(payload["bars"]) == 90
    assert len(payload["equityCurve"]) == 90
    assert set(payload["metrics"]) >= {
        "startingCash",
        "finalEquity",
        "totalReturn",
        "annualizedReturn",
        "annualizedVolatility",
        "sharpeRatio",
        "maxDrawdown",
        "tradeCount",
        "barCount",
        "signalCount",
    }
    assert set(payload["metrics"]) >= {
        "sortinoRatio",
        "calmarRatio",
        "winRate",
        "profitFactor",
        "expectancy",
        "exposure",
        "turnover",
        "totalCommission",
        "closedTradeCount",
    }


def test_api_backtest_rejects_when_akshare_is_unavailable(
    tmp_path,
    monkeypatch,
) -> None:
    from lh_quant.api.app import create_app

    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"

    def fake_download_akshare_bars(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
        raise AkShareDataError("AKShare 测试超时")

    monkeypatch.setattr("lh_quant.api.app.download_akshare_bars", fake_download_akshare_bars)
    client = TestClient(create_app(database_url=database_url))

    response = client.post(
        "/api/backtests/moving-average",
        json={
            "symbol": "000001",
            "start": "2024-01-01",
            "end": "2024-06-30",
            "fastWindow": 5,
            "slowWindow": 20,
            "cash": 100000,
            "adjust": "qfq",
        },
    )

    assert response.status_code == 400
    assert "AKShare 测试超时" in response.text


def test_api_backtest_ignores_cached_yahoo_bars_for_a_share_flow(
    tmp_path,
    monkeypatch,
) -> None:
    from lh_quant.api.app import create_app
    from lh_quant.storage.database import create_database_engine, initialize_database
    from lh_quant.storage.repository import save_market_bars

    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    engine = create_database_engine(database_url)
    initialize_database(engine)
    bars = generate_sample_bars(symbol="000001", periods=90)
    save_market_bars(
        engine=engine,
        bars=bars,
        provider="Yahoo Finance",
        symbol="000001",
        frequency="1d",
        adjust="qfq",
    )

    def fake_download_akshare_bars(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
        assert symbol == "000001"
        assert adjust == "qfq"
        return bars

    monkeypatch.setattr("lh_quant.api.app.download_akshare_bars", fake_download_akshare_bars)
    client = TestClient(create_app(database_url=database_url))

    response = client.post(
        "/api/backtests/moving-average",
        json={
            "symbol": "000001",
            "start": str(bars["datetime"].min().date()),
            "end": str(bars["datetime"].max().date()),
            "fastWindow": 5,
            "slowWindow": 20,
            "cash": 100000,
            "adjust": "qfq",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["dataSource"]["provider"] == "AKShare"
    assert payload["dataSource"]["cached"] is False
    assert "已通过 AKShare 读取 A股日线数据" in payload["logs"]


def test_api_backtest_persists_run_when_database_is_enabled(tmp_path, monkeypatch) -> None:
    from lh_quant.api.app import create_app
    from lh_quant.storage.repository import list_backtest_runs

    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    bars = generate_sample_bars(symbol="000001", periods=90)

    def fake_download_akshare_bars(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
        return bars

    monkeypatch.setattr("lh_quant.api.app.download_akshare_bars", fake_download_akshare_bars)
    app = create_app(database_url=database_url)
    client = TestClient(app)

    response = client.post(
        "/api/backtests/moving-average",
        json={
            "symbol": "000001",
            "start": "2024-01-01",
            "end": "2024-06-30",
            "fastWindow": 5,
            "slowWindow": 20,
            "cash": 100000,
            "adjust": "qfq",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["runId"].startswith("bt_")
    assert payload["database"]["connected"] is True
    assert "已保存回测记录到数据库" in payload["logs"]
    runs = list_backtest_runs(app.state.db_engine, limit=5)
    assert runs[0]["runId"] == payload["runId"]
    assert "annualized_return" in runs[0]["metrics"]
    assert "calmar_ratio" in runs[0]["metrics"]
    assert "win_rate" in runs[0]["metrics"]
    assert "turnover" in runs[0]["metrics"]

    runs_response = client.get("/api/backtests/runs")
    assert runs_response.status_code == 200
    assert runs_response.json()["runs"][0]["runId"] == payload["runId"]


def test_api_loads_backtest_run_detail(tmp_path, monkeypatch) -> None:
    from lh_quant.api.app import create_app

    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    bars = generate_sample_bars(symbol="000001", periods=90)

    def fake_download_akshare_bars(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
        return bars

    monkeypatch.setattr("lh_quant.api.app.download_akshare_bars", fake_download_akshare_bars)
    client = TestClient(create_app(database_url=database_url))

    run_response = client.post(
        "/api/backtests/run",
        json={
            "symbol": "000001",
            "start": "2024-01-01",
            "end": "2024-06-30",
            "strategyId": "moving_average",
            "strategyParams": {"fastWindow": 5, "slowWindow": 20},
            "cash": 100000,
            "adjust": "qfq",
        },
    )
    assert run_response.status_code == 200
    run_id = run_response.json()["runId"]

    detail_response = client.get(f"/api/backtests/{run_id}")

    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["database"]["connected"] is True
    assert payload["runId"] == run_id
    assert payload["summary"]["symbol"] == "000001"
    assert payload["equityCurve"]
    assert payload["signals"]
    assert payload["trades"]


def test_api_backtest_run_detail_returns_404_for_unknown_run(tmp_path) -> None:
    from lh_quant.api.app import create_app

    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    client = TestClient(create_app(database_url=database_url))

    response = client.get("/api/backtests/bt_missing")

    assert response.status_code == 404


def test_api_backtest_run_detail_returns_503_when_database_is_disconnected(
    tmp_path,
    monkeypatch,
) -> None:
    from lh_quant.api.app import create_app

    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"

    def fake_initialize_database_safely(_engine):
        return DatabaseStatus(connected=False, url="sqlite://", message="数据库连接失败")

    monkeypatch.setattr(
        "lh_quant.api.app.initialize_database_safely",
        fake_initialize_database_safely,
    )
    client = TestClient(create_app(database_url=database_url))

    response = client.get("/api/backtests/bt_missing")

    assert response.status_code == 503
    assert "数据库未连接" in response.text


def test_api_backtest_rejects_commission_rate_that_consumes_cash(tmp_path, monkeypatch) -> None:
    from lh_quant.api.app import create_app

    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    bars = generate_sample_bars(symbol="000001", periods=90)

    def fake_download_akshare_bars(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
        return bars

    monkeypatch.setattr("lh_quant.api.app.download_akshare_bars", fake_download_akshare_bars)
    client = TestClient(create_app(database_url=database_url), raise_server_exceptions=False)

    response = client.post(
        "/api/backtests/run",
        json={
            "symbol": "000001",
            "start": "2024-01-01",
            "end": "2024-06-30",
            "strategyId": "moving_average",
            "strategyParams": {"fastWindow": 5, "slowWindow": 20},
            "cash": 100000,
            "commissionRate": 1.0,
            "adjust": "qfq",
        },
    )

    assert response.status_code == 422
    assert "commissionRate" in response.text


def test_api_backtest_rejects_invalid_moving_average_windows(tmp_path) -> None:
    from lh_quant.api.app import create_app

    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    client = TestClient(create_app(database_url=database_url))

    response = client.post(
        "/api/backtests/moving-average",
        json={
            "symbol": "000001",
            "start": "2024-01-01",
            "end": "2024-06-30",
            "fastWindow": 20,
            "slowWindow": 5,
            "cash": 100000,
        },
    )

    assert response.status_code == 422
    assert "短均线周期必须小于长均线周期" in response.text


def test_api_moving_average_rejects_invalid_date_range_without_500(tmp_path) -> None:
    from lh_quant.api.app import create_app

    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    client = TestClient(create_app(database_url=database_url), raise_server_exceptions=False)

    response = client.post(
        "/api/backtests/moving-average",
        json={
            "symbol": "000001",
            "start": "2024-06-30",
            "end": "2024-01-01",
            "fastWindow": 5,
            "slowWindow": 20,
            "cash": 100000,
        },
    )

    assert response.status_code == 422
    assert "结束日期必须晚于开始日期" in response.text
