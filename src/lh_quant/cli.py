"""命令行入口，负责下载数据和运行回测。"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import click.core as click_core
import click.decorators as click_decorators
import click.exceptions as click_exceptions
import click.formatting as click_formatting
import pandas as pd
import typer
import typer.rich_utils as typer_rich_utils
from rich import box
from rich.console import Console
from rich.table import Table

from lh_quant.backtest.engine import run_signal_backtest
from lh_quant.data.akshare_provider import AkShareDataError, download_akshare_bars
from lh_quant.data.sample import generate_sample_bars
from lh_quant.data.schema import validate_bars
from lh_quant.data.yahoo import YahooDataError, download_yahoo_bars
from lh_quant.storage.database import create_database_engine, initialize_database
from lh_quant.storage.repository import load_market_bars, save_backtest_run, save_market_bars
from lh_quant.strategies.moving_average import moving_average_cross_signals

CLICK_ZH_TRANSLATIONS = {
    "Usage:": "用法:",
    "Options": "选项",
    "Arguments": "参数",
    "Commands": "命令",
    "Show this message and exit.": "显示帮助信息并退出。",
    "Try '{command} {option}' for help.": "可运行 '{command} {option}' 查看帮助。",
    "Error: {message}": "错误: {message}",
    "Invalid value: {message}": "值无效: {message}",
    "Invalid value for {param_hint}: {message}": "参数 {param_hint} 的值无效: {message}",
}


def _install_click_chinese_messages() -> None:
    """把 Click/Typer 自动生成的通用帮助和错误提示切换成中文。

    Typer 的帮助页有一部分文字来自 Click 的 gettext 函数，还有一部分是在
    `typer.rich_utils` 模块加载时就固定下来的常量。这里集中改写这些入口，
    避免命令帮助里出现半中文半英文的提示。
    """

    def zh_gettext(message: str) -> str:
        """返回 Click 内置英文提示的中文翻译。"""

        return CLICK_ZH_TRANSLATIONS.get(message, message)

    click_core._ = zh_gettext
    click_decorators._ = zh_gettext
    click_exceptions._ = zh_gettext
    click_formatting._ = zh_gettext
    typer_rich_utils.ARGUMENTS_PANEL_TITLE = "参数"
    typer_rich_utils.OPTIONS_PANEL_TITLE = "选项"
    typer_rich_utils.COMMANDS_PANEL_TITLE = "命令"
    typer_rich_utils.ERRORS_PANEL_TITLE = "错误"
    typer_rich_utils.DEFAULT_STRING = "[默认值: {}]"
    typer_rich_utils.REQUIRED_LONG_STRING = "[必填]"
    typer_rich_utils.ABORTED_TEXT = "已中止。"
    typer_rich_utils.RICH_HELP = "可运行 [blue]'{command_path} {help_option}'[/] 查看帮助。"


_install_click_chinese_messages()

app = typer.Typer(no_args_is_help=True)
data_app = typer.Typer(no_args_is_help=True)
app.add_typer(data_app, name="data")
console = Console()


@app.callback()
def main() -> None:
    """LH Quant 命令行工具。"""


@app.command("demo-backtest")
def demo_backtest(
    periods: Annotated[
        int,
        typer.Option(min=40, metavar="整数", help="生成多少根交易日K线。"),
    ] = 120,
    fast: Annotated[int, typer.Option(min=2, metavar="整数", help="短均线窗口。")] = 10,
    slow: Annotated[int, typer.Option(min=3, metavar="整数", help="长均线窗口。")] = 30,
    cash: Annotated[float, typer.Option(min=1.0, metavar="金额", help="初始资金。")] = 100_000.0,
    database_url: Annotated[
        str | None,
        typer.Option(help="数据库连接地址；不传则读取 LH_QUANT_DATABASE_URL 或本地 MySQL 默认值。"),
    ] = None,
) -> None:
    """运行入库演示回测，样例K线会先写入数据库再读取回测。"""

    if fast >= slow:
        raise typer.BadParameter("短均线窗口必须小于长均线窗口", param_hint="--fast")

    engine = _initialize_cli_database(database_url)
    bars = generate_sample_bars(periods=periods)
    start = str(bars["datetime"].min().date())
    end = str(bars["datetime"].max().date())
    saved = save_market_bars(
        engine=engine,
        bars=bars,
        provider="开发演示",
        symbol="DEMO",
        frequency="1d",
        adjust="",
        requested_start=start,
        requested_end=end,
    )
    loaded = load_market_bars(
        engine=engine,
        provider="开发演示",
        symbol="DEMO",
        frequency="1d",
        adjust="",
        start=start,
        end=end,
    )
    if loaded is None:
        raise typer.ClickException("演示K线已经入库，但读取数据库缓存失败")

    console.print(f"已入库 {saved} 根演示日K线")
    run_id = _run_and_save_backtest(
        engine=engine,
        bars=loaded,
        symbol="DEMO",
        provider="开发演示",
        start=start,
        end=end,
        fast=fast,
        slow=slow,
        cash=cash,
    )
    console.print(f"运行编号：{run_id}")


@app.command("backtest-db")
def backtest_db(
    symbol: Annotated[str, typer.Option(help="已经入库的标的代码，例如 000001。")],
    start: Annotated[str, typer.Option(help="开始日期，格式为 YYYY-MM-DD。")],
    end: Annotated[str, typer.Option(help="结束日期，格式为 YYYY-MM-DD。")],
    provider: Annotated[str, typer.Option(help="行情供应商标识。")] = "AKShare",
    adjust: Annotated[
        str,
        typer.Option(help="复权方式：qfq 前复权，hfq 后复权，空字符串表示不复权。"),
    ] = "qfq",
    fast: Annotated[int, typer.Option(min=2, metavar="整数", help="短均线窗口。")] = 10,
    slow: Annotated[int, typer.Option(min=3, metavar="整数", help="长均线窗口。")] = 30,
    cash: Annotated[float, typer.Option(min=1.0, metavar="金额", help="初始资金。")] = 100_000.0,
    database_url: Annotated[
        str | None,
        typer.Option(help="数据库连接地址；不传则读取 LH_QUANT_DATABASE_URL 或本地 MySQL 默认值。"),
    ] = None,
) -> None:
    """从数据库读取已入库行情，并运行双均线回测。"""

    if fast >= slow:
        raise typer.BadParameter("短均线窗口必须小于长均线窗口", param_hint="--fast")

    engine = _initialize_cli_database(database_url)
    bars = load_market_bars(
        engine=engine,
        provider=provider,
        symbol=symbol,
        frequency="1d",
        adjust=adjust,
        start=start,
        end=end,
    )
    if bars is None:
        raise typer.ClickException(
            "数据库没有覆盖该区间的完整行情，请先运行 data download-akshare 入库"
        )

    run_id = _run_and_save_backtest(
        engine=engine,
        bars=bars,
        symbol=symbol,
        provider=provider,
        start=start,
        end=end,
        fast=fast,
        slow=slow,
        cash=cash,
    )
    console.print(f"运行编号：{run_id}")


@data_app.command("import-csv")
def import_csv(
    file: Annotated[
        Path,
        typer.Option(exists=True, readable=True, help="待导入数据库的 K线 CSV 文件。"),
    ],
    symbol: Annotated[str, typer.Option(help="入库使用的标的代码。")],
    provider: Annotated[str, typer.Option(help="入库使用的数据来源标识。")] = "CSV导入",
    adjust: Annotated[str, typer.Option(help="复权方式。")] = "",
    database_url: Annotated[
        str | None,
        typer.Option(help="数据库连接地址；不传则读取 LH_QUANT_DATABASE_URL 或本地 MySQL 默认值。"),
    ] = None,
) -> None:
    """把 CSV 作为迁移来源导入数据库；回测仍然只能从数据库读取。"""

    engine = _initialize_cli_database(database_url)
    bars = validate_bars(pd.read_csv(file).assign(symbol=symbol))
    start = str(bars["datetime"].min().date())
    end = str(bars["datetime"].max().date())
    saved = save_market_bars(
        engine=engine,
        bars=bars,
        provider=provider,
        symbol=symbol,
        frequency="1d",
        adjust=adjust,
        requested_start=start,
        requested_end=end,
    )
    console.print(f"已从 CSV 导入并入库 {saved} 根日K线")


def _run_and_save_backtest(
    engine,
    bars,
    symbol: str,
    provider: str,
    start: str,
    end: str,
    fast: int,
    slow: int,
    cash: float,
) -> str:
    """运行双均线回测，保存运行摘要，并打印中文指标表。"""

    signals = moving_average_cross_signals(bars, fast_window=fast, slow_window=slow)
    result = run_signal_backtest(bars, signals, cash=cash)
    _print_backtest_result(result.metrics)
    return save_backtest_run(
        engine=engine,
        symbol=symbol,
        strategy_id="moving_average",
        strategy_name="双均线策略",
        provider=provider,
        start=start,
        end=end,
        params={"fastWindow": fast, "slowWindow": slow, "cash": cash},
        metrics=result.metrics,
        logs=["命令行回测完成，结果已经入库"],
        trades=result.trades,
        equity_curve=result.equity_curve,
        signals=signals,
        bars=bars,
    )


@data_app.command("download-yahoo")
def download_yahoo(
    symbol: Annotated[str, typer.Option(help="Yahoo Finance 标的代码，例如 AAPL 或 SPY。")],
    start: Annotated[str, typer.Option(help="开始日期，格式为 YYYY-MM-DD。")],
    end: Annotated[str, typer.Option(help="结束日期，格式为 YYYY-MM-DD。")],
    database_url: Annotated[
        str | None,
        typer.Option(help="数据库连接地址；不传则读取 LH_QUANT_DATABASE_URL 或本地 MySQL 默认值。"),
    ] = None,
) -> None:
    """从 Yahoo Finance 下载日线行情，并保存到数据库。"""

    try:
        bars = download_yahoo_bars(symbol=symbol, start=start, end=end)
    except YahooDataError as error:
        raise typer.ClickException(str(error)) from error

    engine = _initialize_cli_database(database_url)
    saved = save_market_bars(
        engine=engine,
        bars=bars,
        provider="Yahoo Finance",
        symbol=symbol,
        frequency="1d",
        adjust="",
        requested_start=start,
        requested_end=end,
    )
    console.print(f"已下载并入库 {saved} 根日K线")


@data_app.command("download-akshare")
def download_akshare(
    symbol: Annotated[str, typer.Option(help="A股代码，例如 000001 或 600519。")],
    start: Annotated[str, typer.Option(help="开始日期，格式为 YYYY-MM-DD。")],
    end: Annotated[str, typer.Option(help="结束日期，格式为 YYYY-MM-DD。")],
    adjust: Annotated[
        str,
        typer.Option(help="复权方式：qfq 前复权，hfq 后复权，空字符串表示不复权。"),
    ] = "qfq",
    database_url: Annotated[
        str | None,
        typer.Option(help="数据库连接地址；不传则读取 LH_QUANT_DATABASE_URL 或本地 MySQL 默认值。"),
    ] = None,
) -> None:
    """从 AKShare 下载 A股日线行情，并保存到数据库。"""

    try:
        bars = download_akshare_bars(symbol=symbol, start=start, end=end, adjust=adjust)
    except AkShareDataError as error:
        raise typer.ClickException(str(error)) from error

    engine = _initialize_cli_database(database_url)
    saved = save_market_bars(
        engine=engine,
        bars=bars,
        provider="AKShare",
        symbol=symbol,
        frequency="1d",
        adjust=adjust,
        requested_start=start,
        requested_end=end,
    )
    console.print(f"已下载并入库 {saved} 根A股日K线")


def _initialize_cli_database(database_url: str | None):
    """初始化命令行使用的数据库连接，失败时给出中文错误。"""

    try:
        engine = create_database_engine(database_url)
        initialize_database(engine)
    except Exception as error:
        raise typer.ClickException(f"数据库初始化失败：{error}") from error
    return engine


def _print_backtest_result(metrics: dict[str, float | int]) -> None:
    """用中文表格打印回测指标。"""

    table = Table(title="量化回测结果", box=box.ASCII)
    table.add_column("指标")
    table.add_column("数值", justify="right")
    table.add_row("总收益率", f"{metrics['total_return']:.2%}")
    table.add_row("最大回撤", f"{metrics['max_drawdown']:.2%}")
    table.add_row("最终权益", f"{metrics['final_equity']:,.2f}")
    table.add_row("交易次数", str(metrics["trade_count"]))
    console.print(table)


if __name__ == "__main__":
    app()
