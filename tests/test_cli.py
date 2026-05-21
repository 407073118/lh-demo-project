import os
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from lh_quant.cli import app
from lh_quant.data.sample import generate_sample_bars
from lh_quant.storage.database import create_database_engine, initialize_database
from lh_quant.storage.repository import list_backtest_runs, load_market_bars, save_market_bars


def test_cli_demo_backtest_runs_through_database(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "demo-backtest",
            "--database-url",
            database_url,
            "--periods",
            "80",
            "--fast",
            "5",
            "--slow",
            "20",
        ],
    )

    assert result.exit_code == 0
    assert "总收益率" in result.stdout
    assert "交易次数" in result.stdout
    assert "运行编号" in result.stdout
    runs = list_backtest_runs(create_database_engine(database_url), limit=5)
    assert len(runs) == 1


def test_cli_demo_backtest_reports_invalid_windows_without_traceback() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["demo-backtest", "--fast", "30", "--slow", "10"])

    assert result.exit_code == 2
    assert "短均线窗口必须小于长均线窗口" in result.output
    assert "Traceback" not in result.output


def test_cli_backtest_db_reads_market_bars_from_database(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    engine = create_database_engine(database_url)
    initialize_database(engine)
    bars = generate_sample_bars(symbol="000001", periods=80)
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
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "backtest-db",
            "--database-url",
            database_url,
            "--symbol",
            "000001",
            "--start",
            "2024-01-01",
            "--end",
            "2024-06-30",
            "--fast",
            "5",
            "--slow",
            "20",
        ],
    )

    assert result.exit_code == 0
    assert "总收益率" in result.stdout


def test_cli_download_yahoo_saves_bars_to_database(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    bars = generate_sample_bars(symbol="AAPL", periods=50)

    def fake_download_yahoo_bars(symbol: str, start: str, end: str):
        assert symbol == "AAPL"
        assert start == "2024-01-01"
        assert end == "2024-03-31"
        return bars

    monkeypatch.setattr("lh_quant.cli.download_yahoo_bars", fake_download_yahoo_bars)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "data",
            "download-yahoo",
            "--database-url",
            database_url,
            "--symbol",
            "AAPL",
            "--start",
            "2024-01-01",
            "--end",
            "2024-03-31",
        ],
    )

    assert result.exit_code == 0
    assert "已下载并入库 50 根日K线" in result.stdout
    loaded = load_market_bars(
        engine=create_database_engine(database_url),
        provider="Yahoo Finance",
        symbol="AAPL",
        frequency="1d",
        adjust="",
        start="2024-01-01",
        end="2024-03-31",
    )
    assert loaded is not None
    assert len(loaded) == 50


def test_cli_download_akshare_saves_a_share_bars_to_database(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    bars = generate_sample_bars(symbol="000001", periods=50)

    def fake_download_akshare_bars(symbol: str, start: str, end: str, adjust: str):
        assert symbol == "000001"
        assert start == "2024-01-01"
        assert end == "2024-03-31"
        assert adjust == "qfq"
        return bars

    monkeypatch.setattr("lh_quant.cli.download_akshare_bars", fake_download_akshare_bars)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "data",
            "download-akshare",
            "--database-url",
            database_url,
            "--symbol",
            "000001",
            "--start",
            "2024-01-01",
            "--end",
            "2024-03-31",
        ],
    )

    assert result.exit_code == 0
    assert "已下载并入库 50 根A股日K线" in result.stdout
    loaded = load_market_bars(
        engine=create_database_engine(database_url),
        provider="AKShare",
        symbol="000001",
        frequency="1d",
        adjust="qfq",
        start="2024-01-01",
        end="2024-03-31",
    )
    assert loaded is not None
    assert len(loaded) == 50


def test_cli_file_can_run_directly_from_pycharm_style_configuration() -> None:
    project_root = Path(__file__).resolve().parents[1]
    cli_file = project_root / "src" / "lh_quant" / "cli.py"
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    result = subprocess.run(
        [sys.executable, str(cli_file), "demo-backtest", "--help"],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0
    assert "运行入库演示回测" in result.stdout
