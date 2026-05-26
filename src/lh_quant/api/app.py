"""A股量化研究工作台的 FastAPI 应用。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from lh_quant.backtest.engine import BacktestResult, run_signal_backtest
from lh_quant.data.providers import (
    MarketDataProviderError,
    build_market_data_provider,
    normalize_provider_id,
    provider_chain_for,
    provider_display_name,
)
from lh_quant.factors.registry import get_factor_specs
from lh_quant.storage.data_repository import (
    get_data_asset_detail,
    inspect_market_bar_coverage,
    list_data_assets,
)
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
    dataProvider: str = Field(default="auto", description="行情数据来源：auto/tushare/akshare/yahoo")

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
    dataProvider: str = Field(default="auto", description="行情数据来源：auto/tushare/akshare/yahoo")

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
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):\d+$",
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

    @application.get("/api/platform/capabilities")
    def platform_capabilities() -> dict[str, Any]:
        """返回平台能力地图，供前端展示数据、研究、回测和模拟交易模块。"""

        return _platform_capabilities_to_json()

    @application.get("/api/data/catalog")
    def data_catalog() -> dict[str, Any]:
        """返回数据服务目录，标注可用数据和待建设数据域。"""

        _ensure_database_initialized(application, database_url)
        return {
            "database": _database_status_to_json(application.state.db_status),
            "datasets": _data_catalog_to_json(),
        }

    @application.get("/api/data/assets")
    def data_assets() -> dict[str, Any]:
        """返回持久化数据资产及其覆盖率和质量摘要。"""

        _ensure_database_initialized(application, database_url)
        if not application.state.db_status.connected:
            return {"database": _database_status_to_json(application.state.db_status), "assets": []}
        return {
            "database": _database_status_to_json(application.state.db_status),
            "assets": list_data_assets(application.state.db_engine),
        }

    @application.get("/api/data/assets/{asset_id}")
    def data_asset_detail(asset_id: str) -> dict[str, Any]:
        """返回单个数据资产的字段和最近同步任务。"""

        _ensure_database_initialized(application, database_url)
        if not application.state.db_status.connected:
            raise HTTPException(status_code=503, detail="Database is not connected.")
        asset = get_data_asset_detail(application.state.db_engine, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Data asset not found.")
        return {
            "database": _database_status_to_json(application.state.db_status),
            "asset": asset,
        }

    @application.get("/api/factors")
    def list_factors() -> dict[str, Any]:
        """返回本地和未来外部同步的因子定义。"""

        return {"factors": get_factor_specs()}

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

    @application.post("/api/backtests/jobs")
    def create_backtest_job(request: BacktestRunRequest) -> dict[str, Any]:
        """以任务形态提交回测，当前使用本地同步引擎执行并立即返回结果。"""

        submitted_at = _utc_now_text()
        result = _run_strategy_backtest(application, database_url, request)
        completed_at = _utc_now_text()
        return {
            "job": _job_to_json(
                result=result,
                submitted_at=submitted_at,
                completed_at=completed_at,
            ),
            "result": result,
        }

    @application.get("/api/backtests/jobs/{run_id}")
    def backtest_job_detail(run_id: str) -> dict[str, Any]:
        """按任务编号读取回测任务状态和已恢复的结果。"""

        _ensure_database_initialized(application, database_url)
        if not application.state.db_status.connected:
            raise HTTPException(status_code=503, detail="数据库未连接，无法读取回测任务")
        detail = load_backtest_run_detail(application.state.db_engine, run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="回测任务不存在")
        detail = _hydrate_persisted_run_detail(application.state.db_engine, detail)
        result = _persisted_detail_to_backtest_result(
            detail=detail,
            db_status=application.state.db_status,
        )
        return {
            "job": _job_to_json(
                result=result,
                submitted_at=detail["summary"]["createdAt"],
                completed_at=detail["summary"]["createdAt"],
            ),
            "result": result,
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
        detail = _hydrate_persisted_run_detail(application.state.db_engine, detail)
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
            dataProvider=request.dataProvider,
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
        bars, provider, cached, data_logs, data_lineage = _get_market_bars(
            engine=application.state.db_engine,
            db_status=application.state.db_status,
            requested_provider=request.dataProvider,
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
    except (MarketDataProviderError, ValueError) as error:
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
        data_lineage=data_lineage,
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
        data_source_detail=data_lineage["sourceDetail"],
        data_version=data_lineage["dataVersion"],
        requested_provider=data_lineage["requestedProvider"],
        fallback_chain=data_lineage["fallbackChain"],
        strategy_version=strategy.version,
        engine_version=data_lineage["engineVersion"],
        engine_assumptions=data_lineage["engineAssumptions"],
        run_inputs=payload["strategy"]["params"],
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


def _platform_capabilities_to_json() -> dict[str, Any]:
    """把平台能力整理成前端工作台导航可以直接消费的模块列表。"""

    return {
        "apiVersion": "v1",
        "modules": [
            {
                "id": "data",
                "name": "数据服务",
                "status": "available",
                "description": "A股日线行情入库、缓存命中和数据血缘展示。",
                "features": ["A股日线", "行情缓存", "数据血缘"],
            },
            {
                "id": "research",
                "name": "研究环境",
                "status": "preview",
                "description": "策略模板、参数约束和指标叠加已经可在工作台配置。",
                "features": ["策略模板", "参数校验", "指标叠加"],
            },
            {
                "id": "backtest",
                "name": "回测分析",
                "status": "available",
                "description": "任务化提交回测，保存运行摘要并恢复图表明细。",
                "features": ["任务化回测", "历史详情恢复"],
            },
            {
                "id": "simulation",
                "name": "模拟交易",
                "status": "planned",
                "description": "组合持仓、订单撮合和实时监控仍处在规划阶段。",
                "features": ["组合持仓", "订单撮合", "实时监控"],
            },
        ],
    }


def _data_catalog_to_json() -> list[dict[str, Any]]:
    """返回对齐量化平台的数据目录，区分已可用和待建设数据域。"""

    return [
        {
            "id": "a_share_daily_bars",
            "name": "A股日线行情",
            "status": "available",
            "provider": "AKShare",
            "frequency": "1d",
            "coverage": "按请求区间入库，支持前复权、后复权和不复权。",
            "fields": ["open", "high", "low", "close", "volume"],
        },
        {
            "id": "fundamentals",
            "name": "财务与估值",
            "status": "planned",
            "provider": "待接入",
            "frequency": "quarterly",
            "coverage": "利润表、资产负债表、现金流和常用估值因子。",
            "fields": ["revenue", "net_profit", "pe_ratio", "market_cap"],
        },
        {
            "id": "factors",
            "name": "因子库",
            "status": "planned",
            "provider": "待接入",
            "frequency": "1d",
            "coverage": "动量、波动、质量、规模和自定义研究因子。",
            "fields": ["factor_value", "neutralized_value", "rank", "zscore"],
        },
        {
            "id": "market_rules",
            "name": "交易规则",
            "status": "planned",
            "provider": "本地规则表",
            "frequency": "event",
            "coverage": "停复牌、涨跌停、手续费、滑点和成交约束。",
            "fields": ["is_paused", "limit_up", "limit_down", "commission", "slippage"],
        },
    ]


def _utc_now_text() -> str:
    """生成 API 返回中统一使用的 UTC 时间文本。"""

    return datetime.now(UTC).isoformat(timespec="seconds")


def _job_to_json(
    result: dict[str, Any],
    submitted_at: str,
    completed_at: str,
) -> dict[str, Any]:
    """把同步回测结果包装成任务状态，给前端保留异步任务形态。"""

    strategy = result.get("strategy") if isinstance(result.get("strategy"), dict) else {}
    return {
        "runId": result.get("runId"),
        "status": "succeeded",
        "progress": 1,
        "engine": "sync-local",
        "submittedAt": submitted_at,
        "completedAt": completed_at,
        "symbol": result.get("symbol"),
        "strategyName": strategy.get("name", ""),
        "message": "本地同步回测已完成",
    }


def _persisted_detail_to_backtest_result(
    detail: dict[str, Any],
    db_status: DatabaseStatus,
) -> dict[str, Any]:
    """把已持久化的运行详情恢复成与新回测相同的前端结果结构。"""

    summary = detail["summary"]
    request = _request_from_run_summary(summary)
    requested_provider = summary.get("requestedProvider") or request.get("dataProvider") or "auto"
    actual_provider = summary.get("actualProvider") or summary["provider"]
    return {
        "runId": detail["runId"],
        "symbol": summary["symbol"],
        "strategy": {
            "id": summary["strategyId"],
            "name": summary["strategyName"],
            "params": request,
        },
        "dataSource": {
            "provider": actual_provider,
            "requestedProvider": requested_provider,
            "actualProvider": actual_provider,
            "frequency": "1d",
            "adjust": request["adjust"],
            "start": summary["start"],
            "end": summary["end"],
            "cached": True,
            "sourceDetail": summary.get("dataSourceDetail") or "persisted run",
            "dataVersion": summary.get("dataVersion") or "unknown",
            "fallbackChain": summary.get("fallbackChain") or [],
            "coverage": {
                "status": "unknown",
                "expectedRows": None,
                "actualRows": len(detail.get("bars", [])),
                "missingDates": [],
                "lastTradeDate": None,
            },
            "engineVersion": summary.get("engineVersion") or "signal-close-v1",
            "engineAssumptions": summary.get("engineAssumptions") or _engine_assumptions_json(),
        },
        "database": _database_status_to_json(db_status),
        "metrics": _metrics_from_run_summary(summary, detail),
        "bars": detail.get("bars", []),
        "indicatorLines": detail.get("indicatorLines", []),
        "movingAverages": detail.get("movingAverages", []),
        "signals": detail.get("signals", []),
        "equityCurve": _equity_with_drawdown_from_persisted(detail.get("equityCurve", [])),
        "trades": detail.get("trades", []),
        "logs": ["历史回测任务结果已恢复", *summary.get("logs", [])],
    }


def _request_from_run_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """从历史运行摘要中恢复回测请求参数，并为旧数据填补默认值。"""

    raw_params = summary["params"] if isinstance(summary.get("params"), dict) else {}
    metrics = summary["metrics"] if isinstance(summary.get("metrics"), dict) else {}
    strategy_params = raw_params.get("strategyParams")
    if not isinstance(strategy_params, dict):
        strategy_params = {
            key: value
            for key, value in raw_params.items()
            if isinstance(value, (int, float)) and key not in {"cash", "commissionRate"}
        }
    cash = raw_params.get("cash", metrics.get("starting_cash", 100_000.0))
    commission_rate = raw_params.get("commissionRate", 0.001)
    return {
        "symbol": raw_params.get("symbol", summary["symbol"]),
        "start": raw_params.get("start", summary["start"]),
        "end": raw_params.get("end", summary["end"]),
        "strategyId": raw_params.get("strategyId", summary["strategyId"]),
        "strategyParams": strategy_params,
        "cash": cash if isinstance(cash, (int, float)) else 100_000.0,
        "commissionRate": commission_rate if isinstance(commission_rate, (int, float)) else 0.001,
        "adjust": raw_params.get("adjust", "qfq"),
        "dataProvider": raw_params.get(
            "dataProvider",
            summary.get("requestedProvider") or "auto",
        ),
    }


def _metrics_from_run_summary(
    summary: dict[str, Any],
    detail: dict[str, Any],
) -> dict[str, float | int | None]:
    """把历史运行摘要里的蛇形指标恢复为前端使用的驼峰指标。"""

    request = _request_from_run_summary(summary)
    metrics = summary["metrics"] if isinstance(summary.get("metrics"), dict) else {}
    return {
        "startingCash": metrics.get("starting_cash", request["cash"]),
        "finalEquity": metrics.get("final_equity", request["cash"]),
        "totalReturn": metrics.get("total_return", 0),
        "annualizedReturn": metrics.get("annualized_return"),
        "annualizedVolatility": metrics.get("annualized_volatility"),
        "sharpeRatio": metrics.get("sharpe_ratio"),
        "sortinoRatio": metrics.get("sortino_ratio"),
        "calmarRatio": metrics.get("calmar_ratio"),
        "maxDrawdown": metrics.get("max_drawdown", 0),
        "tradeCount": metrics.get("trade_count", 0),
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
        "barCount": len(detail.get("bars", [])) or len(detail.get("equityCurve", [])),
        "signalCount": len(detail.get("signals", [])),
    }


def _equity_with_drawdown_from_persisted(
    equity_curve: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """为历史权益曲线补计算回撤字段，让任务详情与实时回测保持一致。"""

    peak = 0.0
    records: list[dict[str, Any]] = []
    for point in equity_curve:
        equity = float(point.get("equity", 0) or 0)
        peak = max(peak, equity)
        records.append(
            {
                **point,
                "drawdown": equity / peak - 1.0 if peak > 0 else 0.0,
            }
        )
    return records


def _hydrate_persisted_run_detail(engine: Any, detail: dict[str, Any]) -> dict[str, Any]:
    """在缓存可用时，为历史运行详情补齐图表所需的行情和指标线。"""

    summary = detail["summary"]
    params = summary["params"] if isinstance(summary.get("params"), dict) else {}
    strategy_id = str(summary["strategyId"])
    adjust = str(params.get("adjust", "qfq"))

    bars = load_market_bars(
        engine=engine,
        provider=str(summary["provider"]),
        symbol=str(summary["symbol"]),
        frequency="1d",
        adjust=adjust,
        start=str(summary["start"]),
        end=str(summary["end"]),
    )
    if bars is None:
        return {**detail, "bars": [], "indicatorLines": [], "movingAverages": []}

    raw_strategy_params = params.get("strategyParams")
    if not isinstance(raw_strategy_params, dict):
        raw_strategy_params = params

    try:
        strategy_params = normalize_strategy_params(strategy_id, raw_strategy_params)
        indicator_lines = build_strategy_overlays(strategy_id, bars, strategy_params)
    except ValueError:
        indicator_lines = []

    return {
        **detail,
        "bars": _bars_to_json(bars),
        "indicatorLines": _indicator_lines_to_json(bars, indicator_lines),
        "movingAverages": (
            _moving_average_overlay_to_legacy_json(bars, indicator_lines)
            if strategy_id == "moving_average"
            else []
        ),
    }


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
    data_lineage: dict[str, Any],
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
                "dataProvider": request.dataProvider,
            },
        },
        "dataSource": {
            "provider": provider,
            "requestedProvider": data_lineage["requestedProvider"],
            "actualProvider": data_lineage["actualProvider"],
            "frequency": "1d",
            "adjust": request.adjust,
            "start": request.start,
            "end": request.end,
            "cached": cached,
            "sourceDetail": data_lineage["sourceDetail"],
            "dataVersion": data_lineage["dataVersion"],
            "fallbackChain": data_lineage["fallbackChain"],
            "coverage": data_lineage["coverage"],
            "engineVersion": data_lineage["engineVersion"],
            "engineAssumptions": data_lineage["engineAssumptions"],
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


def _get_market_bars(
    engine: Any,
    db_status: DatabaseStatus,
    requested_provider: str,
    symbol: str,
    start: str,
    end: str,
    adjust: str,
) -> tuple[pd.DataFrame, str, bool, list[str], dict[str, Any]]:
    """按用户选择的数据源读取缓存或下载，并记录完整来源血缘。"""

    if not db_status.connected:
        raise ValueError("数据库未连接，不能运行需要落库审计的回测")

    normalized_requested = normalize_provider_id(requested_provider)
    if normalized_requested == "tushare" and adjust:
        raise MarketDataProviderError("第一版暂不支持 Tushare 复权，请选择不复权或切换 AKShare")

    fallback_chain: list[dict[str, str]] = []
    errors: list[str] = []
    for provider_id in provider_chain_for(normalized_requested, adjust):
        provider_name = provider_display_name(provider_id)
        cached = load_market_bars(
            engine=engine,
            provider=provider_name,
            symbol=symbol,
            frequency="1d",
            adjust=adjust,
            start=start,
            end=end,
        )
        if cached is not None:
            attempt = {
                "provider": provider_name,
                "status": "cache_hit",
                "sourceDetail": "database cache",
            }
            chain = [*fallback_chain, attempt]
            coverage = inspect_market_bar_coverage(
                engine,
                provider=provider_name,
                symbol=symbol,
                exchange=_exchange_for_symbol(symbol),
                frequency="1d",
                adjust=adjust,
                start=start,
                end=end,
            )
            lineage = _data_lineage_json(
                requested_provider=normalized_requested,
                actual_provider=provider_name,
                source_detail="database cache",
                data_version="cache:market_bars",
                fallback_chain=chain,
                coverage=coverage.to_json(),
            )
            return cached, provider_name, True, [f"已从数据库读取 {provider_name} A股日线缓存"], lineage

        try:
            provider = build_market_data_provider(provider_id)
            result = provider.download_bars(symbol=symbol, start=start, end=end, adjust=adjust)
        except Exception as error:
            reason = str(error)
            fallback_chain.append(
                {
                    "provider": provider_name,
                    "status": "failed",
                    "reason": reason,
                }
            )
            errors.append(f"{provider_name}: {reason}")
            if normalized_requested != "auto":
                raise MarketDataProviderError(reason) from error
            continue

        chain = [
            *fallback_chain,
            {
                "provider": result.actual_provider,
                "status": "succeeded",
                "sourceDetail": result.source_detail,
            },
        ]
        logs = [f"已通过 {result.source_detail} 读取 A股日线数据"]
        saved = save_market_bars(
            engine=engine,
            bars=result.bars,
            provider=result.actual_provider,
            symbol=symbol,
            frequency=result.frequency,
            adjust=adjust,
            requested_start=start,
            requested_end=end,
            requested_provider=normalized_requested,
            source_detail=result.source_detail,
            raw_symbol=result.raw_symbol,
            normalized_symbol=result.normalized_symbol,
            data_version=result.data_version,
            fetched_at=result.fetched_at,
            fallback_chain=chain,
        )
        logs.append(f"已保存 {saved} 根日K线到数据库")
        coverage = inspect_market_bar_coverage(
            engine,
            provider=result.actual_provider,
            symbol=symbol,
            exchange=_exchange_for_symbol(symbol),
            frequency=result.frequency,
            adjust=adjust,
            start=start,
            end=end,
        )
        lineage = _data_lineage_json(
            requested_provider=normalized_requested,
            actual_provider=result.actual_provider,
            source_detail=result.source_detail,
            data_version=result.data_version,
            fallback_chain=chain,
            coverage=coverage.to_json(),
        )
        return result.bars, result.actual_provider, False, logs, lineage

    raise MarketDataProviderError("所有行情数据源均不可用：" + "；".join(errors))


def _data_lineage_json(
    requested_provider: str,
    actual_provider: str,
    source_detail: str,
    data_version: str,
    fallback_chain: list[dict[str, str]],
    coverage: dict[str, Any],
) -> dict[str, Any]:
    """生成回测结果使用的数据血缘摘要。"""

    return {
        "requestedProvider": requested_provider,
        "actualProvider": actual_provider,
        "sourceDetail": source_detail,
        "dataVersion": data_version,
        "fallbackChain": fallback_chain,
        "coverage": coverage,
        "engineVersion": "signal-close-v1",
        "engineAssumptions": _engine_assumptions_json(),
    }


def _engine_assumptions_json() -> dict[str, Any]:
    """返回当前简化回测引擎的关键假设。"""

    return {
        "assetScope": "single_symbol",
        "direction": "long_only",
        "executionPrice": "same_bar_close",
        "positionSizing": "all_in_or_flat",
        "slippage": "none",
        "marketRules": "t_plus_1_limit_and_suspend_rules_not_modelled",
    }


def _exchange_for_symbol(symbol: str) -> str:
    """根据 A 股代码推断交易所。"""

    normalized = symbol.strip().lower()
    if normalized.startswith(("6", "sh")):
        return "SSE"
    return "SZSE"


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
