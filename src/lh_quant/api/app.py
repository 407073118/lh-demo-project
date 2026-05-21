"""A股量化研究工作台的 FastAPI 应用。"""

from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from lh_quant.backtest.engine import BacktestResult, run_signal_backtest
from lh_quant.data.akshare_provider import AkShareDataError, download_akshare_bars
from lh_quant.storage.database import (
    DatabaseStatus,
    create_database_engine,
    initialize_database_safely,
)
from lh_quant.storage.repository import (
    list_backtest_runs,
    load_backtest_run_detail,
    load_market_bars,
    save_backtest_run,
    save_market_bars,
)
from lh_quant.strategies.registry import (
    build_strategy_overlays,
    generate_strategy_signals,
    get_strategy_definition,
    get_strategy_specs,
    normalize_strategy_params,
)


def _parse_request_date(value: str) -> pd.Timestamp:
    """把请求里的日期字符串解析为 pandas 时间戳，解析失败时抛出中文错误。"""

    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError) as error:
        raise ValueError("日期格式必须是有效日期") from error
    if pd.isna(parsed):
        raise ValueError("日期格式必须是有效日期")
    return parsed


def _validate_request_date_range(start: str, end: str) -> None:
    """校验回测日期区间，使用真实日期比较而不是字符串排序。"""

    start_date = _parse_request_date(start)
    end_date = _parse_request_date(end)
    if start_date >= end_date:
        raise ValueError("结束日期必须晚于开始日期")


class MovingAverageBacktestRequest(BaseModel):
    """双均线回测请求参数。"""

    symbol: str = Field(min_length=6, max_length=12, description="A股代码")
    start: str = Field(description="开始日期，格式为 YYYY-MM-DD")
    end: str = Field(description="结束日期，格式为 YYYY-MM-DD")
    fastWindow: int = Field(default=5, ge=2, description="短均线周期")
    slowWindow: int = Field(default=20, ge=3, description="长均线周期")
    cash: float = Field(default=100_000.0, gt=0, description="初始资金")
    commissionRate: float = Field(default=0.001, ge=0, lt=1, description="单边手续费率")
    adjust: str = Field(default="qfq", description="复权方式")

    @model_validator(mode="after")
    def validate_windows(self) -> MovingAverageBacktestRequest:
        """校验短均线周期必须小于长均线周期。"""

        _validate_request_date_range(self.start, self.end)
        if self.fastWindow >= self.slowWindow:
            raise ValueError("短均线周期必须小于长均线周期")
        return self


class BacktestRunRequest(BaseModel):
    """通用策略回测请求参数。"""

    symbol: str = Field(min_length=6, max_length=12, description="A股代码")
    start: str = Field(description="开始日期，格式为 YYYY-MM-DD")
    end: str = Field(description="结束日期，格式为 YYYY-MM-DD")
    strategyId: str = Field(default="moving_average", description="策略注册表里的策略 ID")
    strategyParams: dict[str, Any] = Field(default_factory=dict, description="策略专属参数")
    cash: float = Field(default=100_000.0, gt=0, description="初始资金")
    commissionRate: float = Field(default=0.001, ge=0, lt=1, description="单边手续费率")
    adjust: str = Field(default="qfq", description="复权方式")

    @model_validator(mode="after")
    def validate_date_range(self) -> BacktestRunRequest:
        """校验回测结束日期必须晚于开始日期。"""

        _validate_request_date_range(self.start, self.end)
        return self


def create_app(database_url: str | None = None) -> FastAPI:
    """创建 FastAPI 应用实例，供测试和本地服务复用。"""

    application = FastAPI(
        title="LH Quant A股研究工作台",
        description="提供 A股真实行情、策略回测和前端可视化所需的数据接口。",
        version="0.1.0",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
            "http://127.0.0.1:5178",
            "http://127.0.0.1:5188",
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:5178",
            "http://localhost:5188",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.state.db_engine = None
    application.state.db_status = DatabaseStatus(
        connected=False,
        url="",
        message="数据库尚未初始化",
    )

    @application.get("/api/health")
    def health() -> dict[str, Any]:
        """返回前端用于判断服务可用性的健康状态。"""

        _ensure_database_initialized(application, database_url)
        return {
            "status": "ok",
            "name": "LH Quant A股研究工作台",
            "dataSource": "AKShare",
            "database": _database_status_to_json(application.state.db_status),
        }

    @application.get("/api/backtests/runs")
    def recent_backtest_runs(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
        """返回最近的回测运行记录。"""

        _ensure_database_initialized(application, database_url)
        if not application.state.db_status.connected:
            return {"database": _database_status_to_json(application.state.db_status), "runs": []}
        return {
            "database": _database_status_to_json(application.state.db_status),
            "runs": list_backtest_runs(application.state.db_engine, limit=limit),
        }

    @application.get("/api/backtests/{run_id}")
    def backtest_run_detail(run_id: str) -> dict[str, Any]:
        """返回一次已持久化的回测运行和可用明细。"""

        _ensure_database_initialized(application, database_url)
        if not application.state.db_status.connected:
            raise HTTPException(status_code=503, detail="数据库未连接，无法读取回测详情")
        detail = load_backtest_run_detail(application.state.db_engine, run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="回测运行不存在")
        return {
            "database": _database_status_to_json(application.state.db_status),
            **detail,
        }

    @application.get("/api/strategies")
    def list_strategies() -> dict[str, Any]:
        """返回当前系统支持的策略模板和参数定义。"""

        return {"strategies": get_strategy_specs()}

    @application.post("/api/backtests/run")
    def run_configurable_backtest(request: BacktestRunRequest) -> dict[str, Any]:
        """按策略 ID 和参数运行通用回测。"""

        return _run_strategy_backtest(application, database_url, request)

    @application.post("/api/backtests/moving-average")
    def run_moving_average_backtest(request: MovingAverageBacktestRequest) -> dict[str, Any]:
        """兼容旧接口：把双均线请求转换成通用策略回测请求。"""

        generic_request = BacktestRunRequest(
            symbol=request.symbol,
            start=request.start,
            end=request.end,
            strategyId="moving_average",
            strategyParams={
                "fastWindow": request.fastWindow,
                "slowWindow": request.slowWindow,
            },
            cash=request.cash,
            commissionRate=request.commissionRate,
            adjust=request.adjust,
        )
        return _run_strategy_backtest(application, database_url, generic_request)

    return application


def _run_strategy_backtest(
    application: FastAPI,
    database_url: str | None,
    request: BacktestRunRequest,
) -> dict[str, Any]:
    """执行通用策略回测，并把行情、信号、成交和运行日志全部落库。"""

    _ensure_database_initialized(application, database_url)
    if not application.state.db_status.connected:
        raise HTTPException(
            status_code=503,
            detail="数据库未连接，回测已停止；请先确认 MySQL 或 LH_QUANT_DATABASE_URL。",
        )

    try:
        strategy = get_strategy_definition(request.strategyId)
        strategy_params = normalize_strategy_params(request.strategyId, request.strategyParams)
        bars, provider, cached, data_logs = _get_a_share_bars(
            engine=application.state.db_engine,
            db_status=application.state.db_status,
            symbol=request.symbol,
            start=request.start,
            end=request.end,
            adjust=request.adjust,
        )
        signals = generate_strategy_signals(request.strategyId, bars, strategy_params)
        indicator_lines = build_strategy_overlays(request.strategyId, bars, strategy_params)
        result = run_signal_backtest(
            bars,
            signals,
            cash=request.cash,
            commission_rate=request.commissionRate,
        )
    except (AkShareDataError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    payload = _build_backtest_payload(
        bars=bars,
        signals=signals,
        result=result,
        request=request,
        strategy_name=strategy.name,
        strategy_params=strategy_params,
        indicator_lines=indicator_lines,
        provider=provider,
        cached=cached,
        data_logs=data_logs,
        db_status=application.state.db_status,
    )
    run_id = save_backtest_run(
        engine=application.state.db_engine,
        symbol=request.symbol,
        strategy_id=payload["strategy"]["id"],
        strategy_name=payload["strategy"]["name"],
        provider=provider,
        start=request.start,
        end=request.end,
        params=payload["strategy"]["params"],
        metrics=result.metrics,
        logs=payload["logs"],
        trades=result.trades,
        equity_curve=result.equity_curve,
        signals=signals,
        bars=bars,
    )
    payload["runId"] = run_id
    payload["logs"].append("已保存回测记录到数据库")
    return payload


def _ensure_database_initialized(application: FastAPI, database_url: str | None) -> None:
    """在第一次请求到达时初始化数据库，避免导入模块就触碰真实 MySQL。"""

    if application.state.db_engine is not None:
        return
    application.state.db_engine = create_database_engine(database_url)
    application.state.db_status = initialize_database_safely(application.state.db_engine)


def _build_backtest_payload(
    bars: pd.DataFrame,
    signals: pd.Series,
    result: BacktestResult,
    request: BacktestRunRequest,
    strategy_name: str,
    strategy_params: dict[str, int | float],
    indicator_lines: list[dict[str, Any]],
    provider: str,
    cached: bool,
    data_logs: list[str],
    db_status: DatabaseStatus,
) -> dict[str, Any]:
    """把回测结果转换成前端稳定消费的 JSON 结构。"""

    running_peak = result.equity_curve["equity"].cummax()
    drawdown = result.equity_curve["equity"] / running_peak - 1.0
    legacy_moving_averages = (
        _moving_average_overlay_to_legacy_json(bars, indicator_lines)
        if request.strategyId == "moving_average"
        else []
    )

    return {
        "symbol": request.symbol,
        "strategy": {
            "id": request.strategyId,
            "name": strategy_name,
            "params": {
                "symbol": request.symbol,
                "start": request.start,
                "end": request.end,
                "strategyId": request.strategyId,
                "strategyParams": strategy_params,
                "cash": request.cash,
                "commissionRate": request.commissionRate,
                "adjust": request.adjust,
            },
        },
        "dataSource": {
            "provider": provider,
            "frequency": "1d",
            "adjust": request.adjust,
            "start": request.start,
            "end": request.end,
            "cached": cached,
        },
        "database": _database_status_to_json(db_status),
        "metrics": _metrics_to_json(result.metrics, result.equity_curve, signals),
        "bars": _bars_to_json(bars),
        "indicatorLines": _indicator_lines_to_json(bars, indicator_lines),
        "movingAverages": legacy_moving_averages,
        "signals": _signals_to_json(bars, signals),
        "equityCurve": _equity_to_json(result.equity_curve, drawdown),
        "trades": _trades_to_json(result.trades),
        "logs": [
            *data_logs,
            f"已读取 {len(bars)} 根A股日K线",
            f"已生成{strategy_name}信号：{_strategy_params_text(strategy_params)}",
            f"回测完成，成交 {result.metrics['trade_count']} 次",
        ],
    }


def _get_a_share_bars(
    engine: Any,
    db_status: DatabaseStatus,
    symbol: str,
    start: str,
    end: str,
    adjust: str,
) -> tuple[pd.DataFrame, str, bool, list[str]]:
    """优先使用 AKShare 的完整缓存，未命中时下载并强制写入数据库。"""

    if not db_status.connected:
        raise ValueError("数据库未连接，不能运行需要落库审计的回测")

    cached_akshare = load_market_bars(
        engine=engine,
        provider="AKShare",
        symbol=symbol,
        frequency="1d",
        adjust=adjust,
        start=start,
        end=end,
    )
    if cached_akshare is not None:
        return cached_akshare, "AKShare", True, ["已从数据库读取 AKShare A股日线缓存"]

    bars = download_akshare_bars(symbol=symbol, start=start, end=end, adjust=adjust)
    provider = "AKShare"
    source_detail = bars.attrs.get("source_detail", "AKShare")
    logs = [f"已通过 {source_detail} 读取 A股日线数据"]

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
    logs.append(f"已保存 {saved} 根日K线到数据库")
    return bars, provider, False, logs


def _metrics_to_json(
    metrics: dict[str, float | int | None],
    equity_curve: pd.DataFrame,
    signals: pd.Series,
) -> dict[str, float | int | None]:
    """把内部蛇形命名指标转换成前端使用的驼峰命名。"""

    return {
        "startingCash": metrics["starting_cash"],
        "finalEquity": metrics["final_equity"],
        "totalReturn": metrics["total_return"],
        "annualizedReturn": metrics.get("annualized_return"),
        "annualizedVolatility": metrics.get("annualized_volatility"),
        "sharpeRatio": metrics.get("sharpe_ratio"),
        "sortinoRatio": metrics.get("sortino_ratio"),
        "calmarRatio": metrics.get("calmar_ratio"),
        "maxDrawdown": metrics["max_drawdown"],
        "tradeCount": metrics["trade_count"],
        "closedTradeCount": metrics.get("closed_trade_count"),
        "winRate": metrics.get("win_rate"),
        "profitFactor": metrics.get("profit_factor"),
        "expectancy": metrics.get("expectancy"),
        "averageWin": metrics.get("average_win"),
        "averageLoss": metrics.get("average_loss"),
        "totalCommission": metrics.get("total_commission"),
        "exposure": metrics.get("exposure"),
        "averagePositionWeight": metrics.get("average_position_weight"),
        "maxPositionWeight": metrics.get("max_position_weight"),
        "turnover": metrics.get("turnover"),
        "barCount": len(equity_curve),
        "signalCount": int((signals != 0).sum()),
    }


def _database_status_to_json(status: DatabaseStatus) -> dict[str, Any]:
    """把数据库状态转换成前端和健康检查接口使用的 JSON。"""

    return {
        "connected": status.connected,
        "url": "已隐藏",
        "message": status.message,
    }


def _bars_to_json(bars: pd.DataFrame) -> list[dict[str, Any]]:
    """把 K线 DataFrame 转成前端 K线图需要的记录列表。"""

    records: list[dict[str, Any]] = []
    for row in bars.itertuples(index=False):
        records.append(
            {
                "datetime": _date_text(row.datetime),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume),
            }
        )
    return records


def _moving_averages_to_json(
    bars: pd.DataFrame,
    fast_ma: pd.Series,
    slow_ma: pd.Series,
) -> list[dict[str, Any]]:
    """把快慢均线转换成和 K线日期对齐的图表数据。"""

    records: list[dict[str, Any]] = []
    for index, row in bars.iterrows():
        records.append(
            {
                "datetime": _date_text(row["datetime"]),
                "fast": _optional_float(fast_ma.loc[index]),
                "slow": _optional_float(slow_ma.loc[index]),
            }
        )
    return records


def _moving_average_overlay_to_legacy_json(
    bars: pd.DataFrame,
    indicator_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """把新的指标线结构转换成旧版 movingAverages 字段，兼容已有前端和测试。"""

    if len(indicator_lines) < 2:
        return []
    fast_ma = indicator_lines[0]["values"]
    slow_ma = indicator_lines[1]["values"]
    return _moving_averages_to_json(bars, fast_ma, slow_ma)


def _indicator_lines_to_json(
    bars: pd.DataFrame,
    indicator_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """把任意策略的主图叠加线转换成前端 ECharts 可以使用的数据点。"""

    records: list[dict[str, Any]] = []
    for line in indicator_lines:
        values = line["values"]
        points = []
        for index, row in bars.iterrows():
            points.append(
                {
                    "datetime": _date_text(row["datetime"]),
                    "value": _optional_float(values.loc[index]),
                }
            )
        records.append(
            {
                "name": str(line["name"]),
                "color": str(line["color"]),
                "points": points,
            }
        )
    return records


def _strategy_params_text(strategy_params: dict[str, int | float]) -> str:
    """把策略参数格式化成中文运行日志中的短文本。"""

    if not strategy_params:
        return "使用默认参数"
    labels = {
        "fastWindow": "短均线",
        "slowWindow": "长均线",
        "lookbackWindow": "突破窗口",
        "exitWindow": "退出窗口",
        "rsiWindow": "RSI周期",
        "oversold": "超卖阈值",
        "overbought": "过热阈值",
    }
    return "，".join(f"{labels.get(key, key)}={value:g}" for key, value in strategy_params.items())


def _signals_to_json(bars: pd.DataFrame, signals: pd.Series) -> list[dict[str, Any]]:
    """把非零交易信号转换成图表买卖点数据。"""

    records: list[dict[str, Any]] = []
    for index, signal in signals.items():
        if int(signal) == 0:
            continue
        row = bars.loc[index]
        records.append(
            {
                "datetime": _date_text(row["datetime"]),
                "signal": int(signal),
                "label": "买入" if int(signal) == 1 else "卖出",
                "price": float(row["close"]),
            }
        )
    return records


def _equity_to_json(equity_curve: pd.DataFrame, drawdown: pd.Series) -> list[dict[str, Any]]:
    """把权益曲线和回撤序列转换成前端折线图数据。"""

    records: list[dict[str, Any]] = []
    for index, row in equity_curve.iterrows():
        records.append(
            {
                "datetime": _date_text(row["datetime"]),
                "cash": float(row["cash"]),
                "position": float(row["position"]),
                "price": float(row["price"]),
                "equity": float(row["equity"]),
                "drawdown": float(drawdown.loc[index]),
            }
        )
    return records


def _trades_to_json(trades: pd.DataFrame) -> list[dict[str, Any]]:
    """把成交明细转换成前端表格数据。"""

    records: list[dict[str, Any]] = []
    for row in trades.itertuples(index=False):
        records.append(
            {
                "datetime": _date_text(row.datetime),
                "side": row.side,
                "sideText": "买入" if row.side == "buy" else "卖出",
                "price": float(row.price),
                "quantity": float(row.quantity),
                "amount": float(row.price * row.quantity),
                "commission": float(row.commission),
            }
        )
    return records


def _date_text(value: Any) -> str:
    """把 pandas 时间或普通值统一格式化为 YYYY-MM-DD。"""

    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _optional_float(value: Any) -> float | None:
    """把可为空的 pandas 数值转换成 JSON 支持的浮点数或空值。"""

    if pd.isna(value):
        return None
    return float(value)


app = create_app()
