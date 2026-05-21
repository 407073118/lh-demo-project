# Workbench Phase 1-2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade LH Quant from a single-run demo UI into a more credible research workbench by adding richer backtest results, persisted run detail loading, clickable run history, and schema-driven strategy configuration.

**Architecture:** Phase 1 adds richer backend metrics and a run-detail API, then splits the React result area into tabs for overview, risk, price/signals, trades, and lineage. Phase 2 extends the strategy registry with parameter UI metadata and constraints so the frontend renders and validates strategy forms from backend schema instead of hard-coded strategy IDs.

**Tech Stack:** Python 3.11+, pandas, FastAPI, SQLAlchemy Core, pytest, React 19, TypeScript, Vite, ECharts.

---

## Scope

Implement Phase 1 and Phase 2 from `docs/plans/2026-05-21-quant-workbench-upgrade-design.md`.

Included:

- Extended backtest metrics in core backend code.
- Persisted enriched metrics.
- `GET /api/backtests/{runId}` detail endpoint.
- Frontend API types for enriched results and run detail.
- Result workspace tabs.
- Clickable recent runs.
- Strategy parameter constraints exposed by `/api/strategies`.
- Frontend generic constraint validation.
- Configuration form sections for Strategy, Data, Execution, and Portfolio.

Excluded for this plan:

- New factor registry.
- Multi-symbol portfolio engine.
- Benchmark curve and alpha/beta metrics.
- Orders/fills tables.
- Parameter optimization endpoint.
- Notebook or online code editor.

## Preflight

**Step 1: Confirm repository state**

Run:

```powershell
Get-Location
Get-ChildItem -Force
git status --short --branch
```

Expected:

- Current directory is `E:\lh`.
- If this is still not a Git repository, skip commit steps and record that in the execution notes.

**Step 2: Run baseline verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd apps\web
npm run build
cd ..\..
```

Expected:

- Python tests pass.
- Frontend TypeScript/build passes.

Do not continue if baseline is red unless the failure is clearly unrelated and documented.

---

## Task 1: Add Extended Backtest Metrics

**Files:**

- Create: `src/lh_quant/backtest/metrics.py`
- Modify: `src/lh_quant/backtest/engine.py`
- Modify: `src/lh_quant/backtest/__init__.py`
- Test: `tests/test_backtest_metrics.py`
- Test: `tests/test_backtest_engine.py`

**Step 1: Write failing tests for metric formulas**

Create `tests/test_backtest_metrics.py`:

```python
import pandas as pd

from lh_quant.backtest.metrics import calculate_backtest_metrics


def test_calculate_backtest_metrics_includes_risk_trade_exposure_and_turnover() -> None:
    equity_curve = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=5, freq="B"),
            "cash": [100_000, 0, 0, 105_000, 105_000],
            "position": [0, 1_000, 1_000, 0, 0],
            "price": [100, 100, 103, 105, 105],
            "equity": [100_000, 100_000, 103_000, 105_000, 105_000],
        }
    )
    trades = pd.DataFrame(
        {
            "datetime": [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-04")],
            "side": ["buy", "sell"],
            "price": [100.0, 105.0],
            "quantity": [1_000.0, 1_000.0],
            "commission": [100.0, 105.0],
        }
    )

    metrics = calculate_backtest_metrics(
        equity_curve=equity_curve,
        trades=trades,
        starting_cash=100_000,
    )

    assert metrics["starting_cash"] == 100_000
    assert metrics["final_equity"] == 105_000
    assert metrics["total_return"] == 0.05
    assert metrics["max_drawdown"] == 0
    assert metrics["trade_count"] == 2
    assert metrics["closed_trade_count"] == 1
    assert metrics["win_rate"] == 1.0
    assert metrics["profit_factor"] is None
    assert metrics["expectancy"] == 4795.0
    assert metrics["total_commission"] == 205.0
    assert metrics["turnover"] > 1.9
    assert metrics["exposure"] == 0.4
    assert metrics["calmar_ratio"] is None


def test_calculate_backtest_metrics_handles_losing_round_trip() -> None:
    equity_curve = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=4, freq="B"),
            "cash": [100_000, 0, 95_000, 95_000],
            "position": [0, 1_000, 0, 0],
            "price": [100, 100, 95, 95],
            "equity": [100_000, 100_000, 95_000, 95_000],
        }
    )
    trades = pd.DataFrame(
        {
            "datetime": [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")],
            "side": ["buy", "sell"],
            "price": [100.0, 95.0],
            "quantity": [1_000.0, 1_000.0],
            "commission": [100.0, 95.0],
        }
    )

    metrics = calculate_backtest_metrics(equity_curve, trades, starting_cash=100_000)

    assert metrics["total_return"] == -0.05
    assert metrics["max_drawdown"] == -0.05
    assert metrics["closed_trade_count"] == 1
    assert metrics["win_rate"] == 0.0
    assert metrics["profit_factor"] == 0.0
    assert metrics["expectancy"] == -5195.0
```

**Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_backtest_metrics.py -q
```

Expected:

- FAIL because `lh_quant.backtest.metrics` does not exist.

**Step 3: Implement metrics module**

Create `src/lh_quant/backtest/metrics.py`:

```python
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252


def calculate_backtest_metrics(
    equity_curve: pd.DataFrame,
    trades: pd.DataFrame,
    starting_cash: float,
) -> dict[str, float | int | None]:
    """Calculate core, risk, trade-quality, exposure, and cost metrics."""

    if equity_curve.empty:
        raise ValueError("equity_curve must not be empty")
    if starting_cash <= 0:
        raise ValueError("starting_cash must be positive")

    equity = equity_curve["equity"].astype(float)
    final_equity = float(equity.iloc[-1])
    total_return = final_equity / float(starting_cash) - 1.0
    running_peak = equity.cummax()
    drawdown = equity / running_peak - 1.0
    max_drawdown = float(drawdown.min())
    daily_returns = equity.pct_change().dropna()

    risk_metrics = _risk_metrics(
        total_return=total_return,
        max_drawdown=max_drawdown,
        equity_count=len(equity),
        daily_returns=daily_returns,
    )
    trade_metrics = _trade_quality_metrics(trades)
    exposure_metrics = _exposure_metrics(equity_curve)
    turnover_metrics = _turnover_metrics(trades, equity)

    return {
        "starting_cash": float(starting_cash),
        "final_equity": final_equity,
        "total_return": round(float(total_return), 6),
        "max_drawdown": round(max_drawdown, 6),
        "trade_count": int(len(trades)),
        **risk_metrics,
        **trade_metrics,
        **exposure_metrics,
        **turnover_metrics,
    }


def _risk_metrics(
    total_return: float,
    max_drawdown: float,
    equity_count: int,
    daily_returns: pd.Series,
) -> dict[str, float | None]:
    if equity_count < 2:
        return {
            "annualized_return": None,
            "annualized_volatility": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "calmar_ratio": None,
        }

    annualized_return = (1.0 + total_return) ** (TRADING_DAYS_PER_YEAR / equity_count) - 1.0
    annualized_volatility = float(daily_returns.std(ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR))
    sharpe_ratio = (
        None
        if annualized_volatility == 0
        else float(daily_returns.mean() / daily_returns.std(ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR))
    )

    downside = daily_returns.loc[daily_returns < 0]
    downside_std = float(downside.std(ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR)) if not downside.empty else 0.0
    sortino_ratio = None if downside_std == 0 else float(annualized_return / downside_std)
    calmar_ratio = None if max_drawdown == 0 else float(annualized_return / abs(max_drawdown))

    return {
        "annualized_return": round(float(annualized_return), 6),
        "annualized_volatility": round(annualized_volatility, 6),
        "sharpe_ratio": _round_optional(sharpe_ratio),
        "sortino_ratio": _round_optional(sortino_ratio),
        "calmar_ratio": _round_optional(calmar_ratio),
    }


def _trade_quality_metrics(trades: pd.DataFrame) -> dict[str, float | int | None]:
    if trades.empty:
        return {
            "closed_trade_count": 0,
            "win_rate": None,
            "profit_factor": None,
            "expectancy": None,
            "average_win": None,
            "average_loss": None,
            "total_commission": 0.0,
        }

    round_trips = _round_trip_pnls(trades)
    total_commission = float(trades["commission"].sum()) if "commission" in trades else 0.0
    if not round_trips:
        return {
            "closed_trade_count": 0,
            "win_rate": None,
            "profit_factor": None,
            "expectancy": None,
            "average_win": None,
            "average_loss": None,
            "total_commission": round(total_commission, 6),
        }

    wins = [pnl for pnl in round_trips if pnl > 0]
    losses = [pnl for pnl in round_trips if pnl < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    return {
        "closed_trade_count": len(round_trips),
        "win_rate": round(len(wins) / len(round_trips), 6),
        "profit_factor": None if gross_loss == 0 and gross_profit > 0 else round(gross_profit / gross_loss, 6) if gross_loss else 0.0,
        "expectancy": round(float(np.mean(round_trips)), 6),
        "average_win": round(float(np.mean(wins)), 6) if wins else None,
        "average_loss": round(float(np.mean(losses)), 6) if losses else None,
        "total_commission": round(total_commission, 6),
    }


def _round_trip_pnls(trades: pd.DataFrame) -> list[float]:
    pnls: list[float] = []
    open_lot: dict[str, float] | None = None
    for row in trades.itertuples(index=False):
        side = str(row.side)
        price = float(row.price)
        quantity = float(row.quantity)
        commission = float(row.commission)
        if side == "buy" and open_lot is None:
            open_lot = {"price": price, "quantity": quantity, "commission": commission}
        elif side == "sell" and open_lot is not None:
            quantity_used = min(quantity, open_lot["quantity"])
            pnl = (price - open_lot["price"]) * quantity_used - open_lot["commission"] - commission
            pnls.append(round(float(pnl), 6))
            open_lot = None
    return pnls


def _exposure_metrics(equity_curve: pd.DataFrame) -> dict[str, float | None]:
    if equity_curve.empty or "position" not in equity_curve or "price" not in equity_curve:
        return {"exposure": None, "average_position_weight": None, "max_position_weight": None}
    market_value = equity_curve["position"].astype(float) * equity_curve["price"].astype(float)
    equity = equity_curve["equity"].astype(float).replace(0, np.nan)
    weights = (market_value / equity).fillna(0)
    return {
        "exposure": round(float((weights.abs() > 0).mean()), 6),
        "average_position_weight": round(float(weights.abs().mean()), 6),
        "max_position_weight": round(float(weights.abs().max()), 6),
    }


def _turnover_metrics(trades: pd.DataFrame, equity: pd.Series) -> dict[str, float | None]:
    if trades.empty:
        return {"turnover": 0.0}
    amounts = trades["price"].astype(float) * trades["quantity"].astype(float)
    average_equity = float(equity.mean())
    return {"turnover": None if average_equity == 0 else round(float(amounts.sum() / average_equity), 6)}


def _round_optional(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return round(float(value), 6)
```

**Step 4: Wire metrics into the engine**

Modify `src/lh_quant/backtest/engine.py`:

- Import `calculate_backtest_metrics`.
- Replace the old `_calculate_metrics(...)` call with:

```python
metrics = calculate_backtest_metrics(equity_curve, trades, starting_cash=cash)
```

- Delete or stop using the old private `_calculate_metrics`.

Modify `src/lh_quant/backtest/__init__.py` to export `calculate_backtest_metrics`.

**Step 5: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_backtest_metrics.py tests\test_backtest_engine.py -q
```

Expected:

- PASS.

**Step 6: Commit**

Run only if inside a Git repository:

```powershell
git add src/lh_quant/backtest tests/test_backtest_metrics.py tests/test_backtest_engine.py
git commit -m "feat: add extended backtest metrics"
```

---

## Task 2: Return and Persist Enriched Metrics

**Files:**

- Modify: `src/lh_quant/api/app.py:353-401`
- Modify: `tests/test_api_app.py`
- Modify: `tests/test_storage_database.py`

**Step 1: Write failing API assertion**

In `tests/test_api_app.py`, extend the successful backtest test that already asserts metric keys around `test_api_backtest_runs_a_share_moving_average_flow`.

Add assertions:

```python
    expected_metric_keys = {
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
    assert expected_metric_keys <= set(payload["metrics"])
```

Add persistence assertion in `test_api_backtest_persists_run_when_database_is_enabled`:

```python
    assert "annualized_return" in runs[0]["metrics"]
    assert "calmar_ratio" in runs[0]["metrics"]
    assert "win_rate" in runs[0]["metrics"]
    assert "turnover" in runs[0]["metrics"]
```

**Step 2: Run focused test to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_api_app.py::test_api_backtest_runs_a_share_moving_average_flow tests\test_api_app.py::test_api_backtest_persists_run_when_database_is_enabled -q
```

Expected:

- FAIL because new camelCase fields are missing or persisted metrics are not enriched.

**Step 3: Simplify API metric conversion**

Modify `src/lh_quant/api/app.py`:

- Delete `_calculate_risk_metrics` or leave unused for a later cleanup.
- Change `_metrics_to_json` to map enriched snake_case metrics to camelCase:

```python
def _metrics_to_json(
    metrics: dict[str, float | int | None],
    equity_curve: pd.DataFrame,
    signals: pd.Series,
) -> dict[str, float | int | None]:
    """Convert internal snake_case metrics to frontend camelCase metrics."""

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
```

**Step 4: Persist enriched metrics**

In `_run_strategy_backtest`, change `save_backtest_run(... metrics=...)` from:

```python
metrics=result.metrics,
```

to:

```python
metrics=result.metrics,
```

This line may already be correct after Task 1 because `result.metrics` now contains enriched snake_case metrics. Confirm by test; do not change if Task 1 already made it true.

**Step 5: Run API/storage tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_api_app.py tests\test_storage_database.py -q
```

Expected:

- PASS.

**Step 6: Commit**

Run only if inside a Git repository:

```powershell
git add src/lh_quant/api/app.py tests/test_api_app.py tests/test_storage_database.py
git commit -m "feat: expose enriched backtest metrics"
```

---

## Task 3: Add Run Detail Repository Function and API Endpoint

**Files:**

- Modify: `src/lh_quant/storage/repository.py:210-294`
- Modify: `src/lh_quant/api/app.py:120-138`
- Test: `tests/test_storage_database.py`
- Test: `tests/test_api_app.py`

**Step 1: Write failing repository test**

Add to `tests/test_storage_database.py`:

```python
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
```

Update imports:

```python
from lh_quant.storage.repository import load_backtest_run_detail
```

**Step 2: Run test to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_storage_database.py::test_storage_loads_backtest_run_detail_with_artifacts -q
```

Expected:

- FAIL because `load_backtest_run_detail` does not exist.

**Step 3: Implement repository detail loader**

In `src/lh_quant/storage/repository.py`, add:

```python
def load_backtest_run_detail(engine: Engine, run_id: str) -> dict[str, Any] | None:
    """Load one backtest run summary plus persisted trades, equity points, and signals."""

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
            .order_by(backtest_equity_points.c.trade_date)
        ).mappings().all()
        signal_rows = connection.execute(
            select(backtest_signals)
            .where(backtest_signals.c.run_id == run_id)
            .order_by(backtest_signals.c.trade_date)
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
```

**Step 4: Write failing API test**

Add to `tests/test_api_app.py`:

```python
def test_api_loads_backtest_run_detail(tmp_path, monkeypatch) -> None:
    from lh_quant.api.app import create_app
    from lh_quant.storage.repository import list_backtest_runs

    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    bars = generate_sample_bars(symbol="000001", periods=90)

    def fake_download_akshare_bars(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
        return bars

    monkeypatch.setattr("lh_quant.api.app.download_akshare_bars", fake_download_akshare_bars)
    app = create_app(database_url=database_url)
    client = TestClient(app)

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
    run_id = run_response.json()["runId"]

    detail_response = client.get(f"/api/backtests/{run_id}")

    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["runId"] == run_id
    assert payload["summary"]["symbol"] == "000001"
    assert payload["equityCurve"]
    assert payload["signals"]
```

Add not-found assertion:

```python
def test_api_backtest_run_detail_returns_404_for_unknown_run(tmp_path) -> None:
    from lh_quant.api.app import create_app

    database_url = f"sqlite+pysqlite:///{tmp_path / 'lh_quant.db'}"
    client = TestClient(create_app(database_url=database_url))

    response = client.get("/api/backtests/bt_missing")

    assert response.status_code == 404
```

**Step 5: Implement API endpoint**

Modify imports in `src/lh_quant/api/app.py`:

```python
from lh_quant.storage.repository import (
    list_backtest_runs,
    load_backtest_run_detail,
    load_market_bars,
    save_backtest_run,
    save_market_bars,
)
```

Inside `create_app`, after recent runs route:

```python
    @application.get("/api/backtests/{run_id}")
    def backtest_run_detail(run_id: str) -> dict[str, Any]:
        """Return one persisted backtest run with available artifacts."""

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
```

**Step 6: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_storage_database.py::test_storage_loads_backtest_run_detail_with_artifacts tests\test_api_app.py::test_api_loads_backtest_run_detail tests\test_api_app.py::test_api_backtest_run_detail_returns_404_for_unknown_run -q
```

Expected:

- PASS.

**Step 7: Commit**

Run only if inside a Git repository:

```powershell
git add src/lh_quant/storage/repository.py src/lh_quant/api/app.py tests/test_storage_database.py tests/test_api_app.py
git commit -m "feat: add backtest run detail endpoint"
```

---

## Task 4: Update Frontend API Types and Client

**Files:**

- Modify: `apps/web/src/api.ts`
- Test: `apps/web/src/api.ts` via TypeScript build

**Step 1: Extend frontend types**

In `apps/web/src/api.ts`, extend `BacktestResponse["metrics"]` with:

```ts
sortinoRatio: number | null;
calmarRatio: number | null;
closedTradeCount: number | null;
winRate: number | null;
profitFactor: number | null;
expectancy: number | null;
averageWin: number | null;
averageLoss: number | null;
totalCommission: number | null;
exposure: number | null;
averagePositionWeight: number | null;
maxPositionWeight: number | null;
turnover: number | null;
```

Add run detail types:

```ts
export type PersistedRunDetail = {
  database: DatabaseStatus;
  runId: string;
  summary: RunSummary;
  trades: TradeRecord[];
  equityCurve: Omit<EquityRecord, "drawdown">[];
  signals: SignalRecord[];
};
```

Add API function:

```ts
export async function fetchRunDetail(runId: string): Promise<PersistedRunDetail> {
  const response = await fetch(`${API_BASE_URL}/api/backtests/${runId}`);
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(normalizeApiError(detail?.detail, response.status));
  }
  return response.json();
}
```

**Step 2: Build to verify type safety**

Run:

```powershell
cd apps\web
npm run build
cd ..\..
```

Expected:

- PASS.

**Step 3: Commit**

Run only if inside a Git repository:

```powershell
git add apps/web/src/api.ts
git commit -m "feat: add frontend run detail api"
```

---

## Task 5: Split Result Area into Workbench Tabs

**Files:**

- Create: `apps/web/src/features/results/ResultTabs.tsx`
- Create: `apps/web/src/features/results/ResultOverview.tsx`
- Create: `apps/web/src/features/results/RiskReturnPanel.tsx`
- Create: `apps/web/src/features/results/PriceSignalPanel.tsx`
- Create: `apps/web/src/features/results/OrdersTradesPanel.tsx`
- Create: `apps/web/src/features/results/DataLineagePanel.tsx`
- Modify: `apps/web/src/App.tsx:365-402`
- Modify: `apps/web/src/styles.css`

**Step 1: Create result components with existing behavior moved out**

Create `apps/web/src/features/results/ResultOverview.tsx`:

```tsx
import type { BacktestResponse } from "../../api";
import { formatMoney, formatNumber, formatPercent } from "../../format";

export function ResultOverview({ result }: { result: BacktestResponse | null }) {
  const metrics = result?.metrics;
  const items = [
    ["累计收益", metrics ? formatPercent(metrics.totalReturn) : "--"],
    ["年化收益", metrics?.annualizedReturn != null ? formatPercent(metrics.annualizedReturn) : "--"],
    ["最大回撤", metrics ? formatPercent(metrics.maxDrawdown) : "--"],
    ["夏普比率", metrics?.sharpeRatio != null ? formatNumber(metrics.sharpeRatio) : "--"],
    ["Calmar", metrics?.calmarRatio != null ? formatNumber(metrics.calmarRatio) : "--"],
    ["胜率", metrics?.winRate != null ? formatPercent(metrics.winRate) : "--"],
    ["换手", metrics?.turnover != null ? formatNumber(metrics.turnover) : "--"],
    ["最终权益", metrics ? formatMoney(metrics.finalEquity) : "--"]
  ];

  return (
    <div className="metric-strip">
      {items.map(([label, value]) => (
        <div className="metric-item" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}
```

Create `RiskReturnPanel.tsx`:

```tsx
import type { BacktestResponse } from "../../api";
import { EChart } from "../../EChart";

export function RiskReturnPanel({ equityOption }: { result: BacktestResponse; equityOption: echarts.EChartsCoreOption | null }) {
  return equityOption ? <EChart option={equityOption} className="chart chart-small" /> : null;
}
```

If importing `echarts.EChartsCoreOption` is awkward, import `type { EChartsCoreOption } from "echarts/core"` instead.

Create `ResultTabs.tsx`:

```tsx
import { useState } from "react";
import type { ReactNode } from "react";

type ResultTabId = "overview" | "price" | "risk" | "trades" | "lineage" | "logs";

const tabs: Array<{ id: ResultTabId; label: string }> = [
  { id: "overview", label: "概览" },
  { id: "price", label: "价格/信号" },
  { id: "risk", label: "收益/风险" },
  { id: "trades", label: "交易" },
  { id: "lineage", label: "数据血缘" },
  { id: "logs", label: "日志" }
];

export function ResultTabs({ panels }: { panels: Record<ResultTabId, ReactNode> }) {
  const [activeTab, setActiveTab] = useState<ResultTabId>("overview");
  return (
    <section className="panel">
      <div className="tab-bar">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={activeTab === tab.id ? "tab active" : "tab"}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="result-tab-panel">{panels[activeTab]}</div>
    </section>
  );
}
```

Create placeholder panels for `PriceSignalPanel`, `OrdersTradesPanel`, `DataLineagePanel` by moving existing chart/table/overview blocks from `App.tsx`.

**Step 2: Wire tabs in App**

In `App.tsx`, replace the current single stacked result panel with:

```tsx
{result ? (
  <ResultTabs
    panels={{
      overview: <ResultOverview result={result} />,
      price: <PriceSignalPanel candlestickOption={candlestickOption} volumeOption={volumeOption} />,
      risk: <RiskReturnPanel result={result} equityOption={equityOption} />,
      trades: <OrdersTradesPanel result={result} />,
      lineage: <DataLineagePanel result={result} />,
      logs: <RunLogs result={result} />
    }}
  />
) : (
  <div className="empty-state">...</div>
)}
```

Keep existing local functions in `App.tsx` until moved; do not refactor every helper in one commit.

**Step 3: Add CSS**

Add to `apps/web/src/styles.css`:

```css
.result-tab-panel {
  padding: 12px;
}

.result-tab-panel .panel {
  margin-bottom: 12px;
}
```

**Step 4: Build**

Run:

```powershell
cd apps\web
npm run build
cd ..\..
```

Expected:

- PASS.

**Step 5: Commit**

Run only if inside a Git repository:

```powershell
git add apps/web/src/App.tsx apps/web/src/styles.css apps/web/src/features/results
git commit -m "feat: organize backtest results into tabs"
```

---

## Task 6: Make Recent Runs Clickable

**Files:**

- Modify: `apps/web/src/App.tsx:77-87`
- Modify: `apps/web/src/App.tsx:485-522`
- Modify: `apps/web/src/api.ts`

**Step 1: Add state and loader**

Import `fetchRunDetail` in `App.tsx`.

Add:

```tsx
const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
const [isLoadingRunDetail, setIsLoadingRunDetail] = useState(false);
```

Add function:

```tsx
async function openRunDetail(runId: string) {
  setIsLoadingRunDetail(true);
  setError(null);
  try {
    const detail = await fetchRunDetail(runId);
    setSelectedRunId(runId);
    setDatabaseStatus(detail.database);
    setLastRunAt(detail.summary.createdAt);
    setError("已加载历史运行摘要；完整价格图需要重新运行或后续保存 bars 快照。");
  } catch (caught) {
    setError(caught instanceof Error ? caught.message : "读取回测详情失败");
  } finally {
    setIsLoadingRunDetail(false);
  }
}
```

For this phase, do not force persisted detail into `BacktestResponse` because persisted detail does not include bars. Use it to prove navigation and data loading, then Phase 3 can persist full bars/returns.

**Step 2: Update RecentRunsPanel props**

Change `RecentRunsPanel` props:

```tsx
function RecentRunsPanel({
  status,
  runs,
  error,
  selectedRunId,
  isLoading,
  onOpenRun
}: {
  status: DatabaseStatus | null;
  runs: RunSummary[];
  error: string | null;
  selectedRunId: string | null;
  isLoading: boolean;
  onOpenRun: (runId: string) => void;
}) {
```

Render each run as a button:

```tsx
<button
  type="button"
  className={run.runId === selectedRunId ? "run-list-item active" : "run-list-item"}
  onClick={() => onOpenRun(run.runId)}
  disabled={isLoading}
>
```

**Step 3: Add CSS**

In `styles.css`, make `.run-list-item` work as a button:

```css
.run-list-item {
  width: 100%;
  border: 0;
  border-bottom: 1px solid #edf0f4;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.run-list-item.active {
  background: #eff6ff;
}
```

**Step 4: Build**

Run:

```powershell
cd apps\web
npm run build
cd ..\..
```

Expected:

- PASS.

**Step 5: Commit**

Run only if inside a Git repository:

```powershell
git add apps/web/src/App.tsx apps/web/src/styles.css apps/web/src/api.ts
git commit -m "feat: make recent runs clickable"
```

---

## Task 7: Expose Strategy Constraints from Backend

**Files:**

- Modify: `src/lh_quant/strategies/registry.py:31-180`
- Test: `tests/test_strategy_registry.py`
- Test: `tests/test_api_app.py`

**Step 1: Write failing registry test**

In `tests/test_strategy_registry.py`, add:

```python
def test_strategy_specs_include_constraints_for_frontend_validation() -> None:
    specs = get_strategy_specs()
    moving_average = next(spec for spec in specs if spec["id"] == "moving_average")
    momentum = next(spec for spec in specs if spec["id"] == "momentum_breakout")
    rsi = next(spec for spec in specs if spec["id"] == "rsi_reversion")

    assert moving_average["constraints"] == [
        {
            "type": "lt",
            "left": "fastWindow",
            "right": "slowWindow",
            "message": "短均线周期必须小于长均线周期",
        }
    ]
    assert momentum["constraints"][0]["left"] == "exitWindow"
    assert momentum["constraints"][0]["right"] == "lookbackWindow"
    assert rsi["constraints"][0]["type"] == "ordered"
    assert rsi["constraints"][0]["fields"] == ["oversold", "overbought"]
```

**Step 2: Run test to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_strategy_registry.py::test_strategy_specs_include_constraints_for_frontend_validation -q
```

Expected:

- FAIL because `constraints` is missing.

**Step 3: Implement constraint dataclass**

In `src/lh_quant/strategies/registry.py`, add:

```python
@dataclass(frozen=True)
class StrategyConstraintDefinition:
    """Frontend-visible and backend-enforced relation between strategy parameters."""

    type: str
    message: str
    left: str | None = None
    right: str | None = None
    fields: tuple[str, ...] = ()
    min_value: int | float | None = None
    max_value: int | float | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": self.type, "message": self.message}
        if self.left is not None:
            payload["left"] = self.left
        if self.right is not None:
            payload["right"] = self.right
        if self.fields:
            payload["fields"] = list(self.fields)
        if self.min_value is not None:
            payload["min"] = self.min_value
        if self.max_value is not None:
            payload["max"] = self.max_value
        return payload
```

Extend `StrategyDefinition`:

```python
constraints: tuple[StrategyConstraintDefinition, ...] = ()
```

Add to `to_json`:

```python
"constraints": [constraint.to_json() for constraint in self.constraints],
```

Add generic validator:

```python
def _validate_constraints(params: StrategyParams, constraints: tuple[StrategyConstraintDefinition, ...]) -> None:
    for constraint in constraints:
        if constraint.type == "lt":
            if constraint.left is None or constraint.right is None:
                raise ValueError("lt constraint requires left and right")
            if not params[constraint.left] < params[constraint.right]:
                raise ValueError(constraint.message)
        elif constraint.type == "ordered":
            values = [params[field] for field in constraint.fields]
            if any(left >= right for left, right in zip(values, values[1:])):
                raise ValueError(constraint.message)
            if constraint.min_value is not None and values[0] <= constraint.min_value:
                raise ValueError(constraint.message)
            if constraint.max_value is not None and values[-1] >= constraint.max_value:
                raise ValueError(constraint.message)
        else:
            raise ValueError(f"未知策略参数约束: {constraint.type}")
```

In `normalize_strategy_params`, call:

```python
_validate_constraints(normalized, strategy.constraints)
```

Keep existing `validator` call for compatibility for now; remove old validators only after tests prove no behavior change.

Add constraints to the three strategy definitions:

```python
constraints=(
    StrategyConstraintDefinition(
        type="lt",
        left="fastWindow",
        right="slowWindow",
        message="短均线周期必须小于长均线周期",
    ),
),
```

For RSI:

```python
constraints=(
    StrategyConstraintDefinition(
        type="ordered",
        fields=("oversold", "overbought"),
        min_value=0,
        max_value=100,
        message="RSI 阈值必须满足 0 < 超卖阈值 < 过热阈值 < 100",
    ),
),
```

**Step 4: Add API assertion**

In `tests/test_api_app.py::test_api_lists_configurable_strategies`, add:

```python
    assert payload["strategies"][0]["constraints"][0]["type"] == "lt"
```

**Step 5: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_strategy_registry.py tests\test_api_app.py::test_api_lists_configurable_strategies -q
```

Expected:

- PASS.

**Step 6: Commit**

Run only if inside a Git repository:

```powershell
git add src/lh_quant/strategies/registry.py tests/test_strategy_registry.py tests/test_api_app.py
git commit -m "feat: expose strategy parameter constraints"
```

---

## Task 8: Add Frontend Constraint Evaluation

**Files:**

- Modify: `apps/web/src/api.ts:1-25`
- Create: `apps/web/src/strategyConstraints.ts`
- Modify: `apps/web/src/App.tsx:89-130`

**Step 1: Update frontend types**

In `apps/web/src/api.ts`, add:

```ts
export type StrategyConstraint =
  | {
      type: "lt";
      left: string;
      right: string;
      message: string;
    }
  | {
      type: "ordered";
      fields: string[];
      min?: number;
      max?: number;
      message: string;
    };
```

Add to `StrategyDefinition`:

```ts
constraints: StrategyConstraint[];
```

**Step 2: Add evaluator**

Create `apps/web/src/strategyConstraints.ts`:

```ts
import type { StrategyConstraint, StrategyParams } from "./api";

export function evaluateStrategyConstraints(
  params: StrategyParams,
  constraints: StrategyConstraint[]
): string | null {
  for (const constraint of constraints) {
    if (constraint.type === "lt") {
      if (!(params[constraint.left] < params[constraint.right])) {
        return constraint.message;
      }
    }
    if (constraint.type === "ordered") {
      const values = constraint.fields.map((field) => params[field]);
      if (values.some((value) => !Number.isFinite(value))) {
        return constraint.message;
      }
      for (let index = 0; index < values.length - 1; index += 1) {
        if (!(values[index] < values[index + 1])) {
          return constraint.message;
        }
      }
      if (constraint.min != null && !(values[0] > constraint.min)) {
        return constraint.message;
      }
      if (constraint.max != null && !(values[values.length - 1] < constraint.max)) {
        return constraint.message;
      }
    }
  }
  return null;
}
```

**Step 3: Replace hard-coded frontend strategy validation**

In `App.tsx`, import:

```ts
import { evaluateStrategyConstraints } from "./strategyConstraints";
```

Replace these hard-coded blocks:

```tsx
if (form.strategyId === "moving_average" && ...)
if (form.strategyId === "momentum_breakout" && ...)
if (form.strategyId === "rsi_reversion" && ...)
```

with:

```tsx
const constraintError = evaluateStrategyConstraints(
  form.strategyParams,
  selectedStrategy.constraints ?? []
);
if (constraintError) {
  return constraintError;
}
```

**Step 4: Build**

Run:

```powershell
cd apps\web
npm run build
cd ..\..
```

Expected:

- PASS.

**Step 5: Commit**

Run only if inside a Git repository:

```powershell
git add apps/web/src/api.ts apps/web/src/App.tsx apps/web/src/strategyConstraints.ts
git commit -m "feat: validate strategy params from schema constraints"
```

---

## Task 9: Split Configuration UI into Workbench Sections

**Files:**

- Create: `apps/web/src/features/configure/StrategyConfigSection.tsx`
- Create: `apps/web/src/features/configure/DataConfigSection.tsx`
- Create: `apps/web/src/features/configure/ExecutionConfigSection.tsx`
- Create: `apps/web/src/features/configure/PortfolioConfigSection.tsx`
- Modify: `apps/web/src/App.tsx:208-358`
- Modify: `apps/web/src/styles.css`

**Step 1: Create section components**

Create `StrategyConfigSection.tsx`:

```tsx
import type { StrategyDefinition, StrategyParamDefinition, StrategyParams } from "../../api";

export function StrategyConfigSection({
  strategies,
  selectedStrategy,
  strategyId,
  strategyParams,
  onStrategyChange,
  onParamChange
}: {
  strategies: StrategyDefinition[];
  selectedStrategy: StrategyDefinition | null;
  strategyId: string;
  strategyParams: StrategyParams;
  onStrategyChange: (strategyId: string) => void;
  onParamChange: (param: StrategyParamDefinition, value: number) => void;
}) {
  return (
    <section className="form-section">
      <h2>策略配置</h2>
      <label>
        策略模板
        <select value={strategyId} onChange={(event) => onStrategyChange(event.target.value)} disabled={strategies.length === 0}>
          {strategies.length === 0 ? <option value={strategyId}>加载策略中</option> : null}
          {strategies.map((strategy) => (
            <option value={strategy.id} key={strategy.id}>
              {strategy.name}
            </option>
          ))}
        </select>
      </label>
      {selectedStrategy ? (
        <div className="strategy-summary">
          <div>
            <strong>{selectedStrategy.category}</strong>
            <span>{selectedStrategy.name}</span>
          </div>
          <p>{selectedStrategy.description}</p>
        </div>
      ) : (
        <div className="strategy-summary muted">正在从后端读取策略模板</div>
      )}
      {selectedStrategy ? (
        <div className="field-grid">
          {selectedStrategy.params.map((param) => (
            <label key={param.key}>
              {param.label}
              <input
                type="number"
                min={param.min}
                max={param.max}
                step={param.step}
                value={strategyParams[param.key] ?? param.default}
                onChange={(event) => onParamChange(param, Number(event.target.value))}
              />
              <span className="param-help">
                {param.helpText}
                {param.unit ? `（单位：${param.unit}）` : ""}
              </span>
            </label>
          ))}
        </div>
      ) : null}
    </section>
  );
}
```

Create `DataConfigSection.tsx` with symbol, start, end, adjust fields.

Create `ExecutionConfigSection.tsx` with `commissionRate`.

Create `PortfolioConfigSection.tsx` with `cash`.

Keep current fields only; do not add backend unsupported fields yet.

**Step 2: Replace sidebar form blocks in App**

In `App.tsx`, replace inline sections with:

```tsx
<StrategyConfigSection
  strategies={strategies}
  selectedStrategy={selectedStrategy}
  strategyId={form.strategyId}
  strategyParams={form.strategyParams}
  onStrategyChange={handleStrategyChange}
  onParamChange={updateStrategyParam}
/>
<DataConfigSection form={form} setForm={setForm} />
<PortfolioConfigSection form={form} setForm={setForm} />
<ExecutionConfigSection form={form} setForm={setForm} />
```

If TypeScript complains about `setForm` type, define:

```ts
type BacktestFormSetter = React.Dispatch<React.SetStateAction<BacktestRequest>>;
```

and export/use it in section props.

**Step 3: Add section labels**

Keep the existing `.form-section` styling. Add small section hints only if needed; do not add explanatory marketing text.

**Step 4: Build**

Run:

```powershell
cd apps\web
npm run build
cd ..\..
```

Expected:

- PASS.

**Step 5: Commit**

Run only if inside a Git repository:

```powershell
git add apps/web/src/App.tsx apps/web/src/styles.css apps/web/src/features/configure
git commit -m "refactor: split backtest configuration sections"
```

---

## Task 10: Document Phase 1-2 Behavior and Run Full Verification

**Files:**

- Modify: `docs/plans/2026-05-21-quant-workbench-upgrade-design.md`
- Modify: `README.md` if API fields or run detail endpoint should be user-facing.
- Modify: `docs/architecture.md`

**Step 1: Update architecture notes**

Add a short section to `docs/architecture.md`:

```markdown
## Workbench result and configuration model

The web workbench separates backtest configuration from strategy parameters. Strategy metadata now includes frontend-visible constraints, so both API and UI validate the same parameter relationships. Backtest runs persist enriched metrics and can be reopened by run id through `/api/backtests/{runId}`.
```

**Step 2: Update design status**

In `docs/plans/2026-05-21-quant-workbench-upgrade-design.md`, mark Phase 1-2 as implementation-planned and link this plan.

**Step 3: Run full backend tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected:

- PASS.

**Step 4: Run frontend build**

Run:

```powershell
cd apps\web
npm run build
cd ..\..
```

Expected:

- PASS.

**Step 5: Run lint if available**

Run:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
```

Expected:

- PASS or document existing unrelated lint failures.

**Step 6: Commit**

Run only if inside a Git repository:

```powershell
git add README.md docs/architecture.md docs/plans/2026-05-21-quant-workbench-upgrade-design.md
git commit -m "docs: describe workbench phase one and two"
```

---

## Final Verification Checklist

Before reporting completion, run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
cd apps\web
npm run build
cd ..\..
```

Expected:

- Python tests pass.
- Ruff passes.
- Frontend build passes.

Also manually inspect:

- `/api/strategies` includes `constraints`.
- `/api/backtests/run` returns enriched `metrics`.
- `/api/backtests/{runId}` returns persisted summary/artifacts.
- Frontend result area shows tabs.
- Recent runs are clickable.
- Invalid strategy parameter relations show the backend-provided message.

## Execution Notes

- This plan assumes the executor works in a Git repository or dedicated worktree. The current `E:\lh` directory previously reported `fatal: not a git repository`; if that is still true, skip commit steps and include that fact in the final report.
- Use `@verification-before-completion` before claiming work is complete.
- Keep Phase 3 factor work out of this implementation unless explicitly requested after Phase 1-2 is verified.
