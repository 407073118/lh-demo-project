# Quant Workbench Upgrade Design

**Status:** Phase 1-2 implemented; Phase 3+ factor and portfolio work remains planned
**Date:** 2026-05-21
**Scope:** Product and architecture design for upgrading LH Quant from a single-run demo workbench into a more credible quant research workbench.

**Implementation link:** Phase 1-2 execution plan: `docs/plans/2026-05-21-workbench-phase1-2-implementation.md`.

## Goal

Turn the current LH Quant app from "single symbol, single strategy, single backtest result" into a local-first quant research workbench with richer backtest configuration, factor-driven strategy construction, reproducible data lineage, and research-grade result analysis.

The current project already has a useful spine:

- Data providers normalize OHLCV into a shared bar contract.
- The database acts as the source of truth.
- The strategy registry exposes parameter metadata to the frontend.
- FastAPI runs backtests and persists runs.
- React/ECharts visualizes price, signals, equity, drawdown, trades, and logs.

The missing layer is the research workflow: benchmark comparison, factor configuration, parameter constraints, experiment comparison, data quality visibility, execution assumptions, positions, orders, and richer metrics.

## External References Worth Copying

These are product patterns to learn from, not dependencies to clone blindly.

- JoinQuant: strategy list, online editor, backtest parameter panel, quick backtest, full backtest, simulation flow. Source: https://www.joinquant.com/guide
- RiceQuant backtest: base settings, benchmark, commission, matching mode, slippage, volume limit, custom parameters, result pages for positions, PnL, trades, risk. Source: https://rqopen.ricequant.com/doc/quant/backtest.html
- RiceQuant factor research: factor library, formula factors, factor tests, publish/track factors, correlation analysis. Source: https://www.ricequant.com/doc/quant/factor-system.html
- BigQuant: data, factor library, expression engine, and trade engine as composable modules. Source: https://bigquant.com/doc/data_features.html
- QuantConnect: result pages include equity, drawdown, benchmark, exposure, turnover, orders, trades, logs, code snapshot, and optimization heatmaps/scatter plots. Sources: https://www.quantconnect.com/docs/v2/local-platform/backtesting/results and https://www.quantconnect.com/docs/v2/cloud-platform/optimization/results

## Current Gaps

### Frontend Result Data

Current frontend display is enough for a demo:

- Metric strip: total return, annualized return, max drawdown, volatility, Sharpe, final equity, trade count.
- Charts: K-line, volume, strategy overlays, buy/sell markers, equity, drawdown.
- Tables/logs: simplified trades and run logs.
- Recent runs: compact list.

It is not enough for quant research. Missing:

- Benchmark and excess return: benchmark curve, excess curve, alpha, beta, information ratio, tracking error.
- Positions and exposure: daily cash, market value, weight, net exposure, gross exposure, leverage, turnover.
- Order/fill model: orders, fills, rejected orders, partial fills, slippage, taxes, minimum commission.
- Trade quality: win rate, average win/loss, profit factor, expectancy, holding days, MAE/MFE, exit reason.
- Return diagnostics: daily returns, monthly returns, rolling return, rolling Sharpe, drawdown duration.
- Experiment workflow: open run by `runId`, clone config, compare runs, parameter grid, heatmap, report export.
- Data quality: coverage, missing trading days, provider, adjust mode, ingestion range, factor version, code/config hash.

### Strategy Configuration

Current strategy configuration is flat and too narrow:

- `StrategyParamDefinition` supports numeric params only.
- Cross-field constraints are duplicated in Python validators and frontend `if strategyId === ...` blocks.
- Factors are embedded inside strategy functions.
- Indicator overlays are only price-panel lines.
- Backtest configuration is mixed with strategy form fields.

This will not scale once there are more strategies, factor filters, multi-factor scoring, parameter scans, or non-price indicators.

### Quant Research Credibility

Current backtest engine is intentionally simple: single symbol, long-only, all-in/all-out, same-bar close execution, fixed commission. That makes the learning path clear, but it creates professional gaps:

- Same close can generate a signal and fill a trade, which risks optimistic bias unless explicitly modeled as market-on-close.
- No trading calendar validation, so cached coverage is not the same as complete trading-day coverage.
- No suspensions, limit up/down, ST status, delisting, lot size, or liquidity constraints.
- No benchmark, no portfolio accounting, no target weights, no rebalancing, no realistic execution layer.
- Core metrics are not saved with the richer API-level risk metrics.

## Recommended Product Direction

Use approach B: build a research workbench, not a full platform yet.

Avoid jumping directly to notebook, online editor, live simulation, or a complete event-driven engine. First, make the current local app feel like a serious backtest and factor research workbench:

1. Refactor configuration into schema-driven sections.
2. Add a factor registry and one minimal factor-enabled strategy path.
3. Expand result pages into tabs.
4. Persist richer run artifacts.
5. Add experiment comparison and parameter scan after single-run result quality improves.

## Information Architecture

Replace the current single left sidebar plus long result panel with a workbench shell:

```text
Top bar
  Connection, database, active run, data source, last run

Left rail
  Research
  Backtests
  Factors
  Data
  Reports

Main workspace
  Configure tab
  Results tab
  Compare tab
  Data lineage tab
```

For the first implementation, this can remain a single React page with internal tabs. No router is required yet.

### Configure Tab

Split configuration into cards or sections:

1. Universe
   - Single symbol for MVP.
   - Later: symbol search, index constituents, industry filters, stock pool.
2. Data
   - Provider, adjust mode, frequency, calendar, missing data policy, warmup window.
3. Strategy
   - Strategy template and schema-driven parameters.
   - Factor slots for supported strategies.
4. Execution
   - Fill price, commission, stamp duty, slippage, minimum commission, lot size.
5. Portfolio and Risk
   - Initial cash, target sizing, max position, stop loss, rebalance schedule.
6. Experiment
   - Run name, tags, notes, save snapshot, parameter scan toggle.

### Results Tab

Use tabs inspired by RiceQuant and QuantConnect:

1. Overview
   - Strategy return, benchmark return, excess return, max drawdown, Sharpe, Calmar, win rate, turnover, exposure.
2. Price and Signals
   - K-line, volume, overlays, buy/sell markers, signal explanations.
3. Returns and Risk
   - Equity, benchmark, excess return, drawdown, daily/monthly returns, rolling Sharpe.
4. Positions
   - Daily position, cash, market value, weight, exposure.
5. Orders and Trades
   - Orders, fills, trades, commissions, tax, slippage, realized PnL.
6. Data Lineage
   - Provider, adjust mode, requested range, actual coverage, missing days, factor versions, config hash.
7. Logs
   - Data logs, validation logs, execution logs.

## Configuration Model

The current `BacktestRunRequest` should evolve from flat fields into a structured config. Preserve backward compatibility during migration.

```json
{
  "universe": {
    "mode": "single_symbol",
    "symbols": ["000001"],
    "benchmarkSymbol": "000300"
  },
  "data": {
    "provider": "AKShare",
    "frequency": "1d",
    "adjust": "qfq",
    "calendar": "XSHG_XSHE",
    "missingPolicy": "fail",
    "warmupBars": 120
  },
  "strategy": {
    "strategyId": "moving_average",
    "params": {
      "fastWindow": 5,
      "slowWindow": 20
    },
    "factors": []
  },
  "execution": {
    "fillPrice": "next_open",
    "commissionRate": 0.001,
    "stampDutyRate": 0.001,
    "slippageBps": 5,
    "minCommission": 5,
    "lotSize": 100,
    "volumeLimitPct": 0.1
  },
  "portfolio": {
    "initialCash": 100000,
    "sizingMode": "all_in",
    "maxPositionWeight": 1.0,
    "rebalance": "signal"
  },
  "risk": {
    "stopLossPct": null,
    "takeProfitPct": null,
    "maxDrawdownStopPct": null
  },
  "experiment": {
    "name": "双均线基线",
    "tags": ["baseline"],
    "notes": ""
  }
}
```

## Parameter Schema and Constraints

Move all control and constraint metadata into the backend registry so the frontend can render and validate generically.

```json
{
  "key": "fastWindow",
  "label": "短均线",
  "valueType": "int",
  "controlType": "number",
  "group": "均线参数",
  "default": 5,
  "min": 2,
  "max": 120,
  "step": 1,
  "unit": "日",
  "helpText": "短周期越小，信号越敏感。",
  "dependsOn": []
}
```

Strategy-level constraints:

```json
[
  {
    "type": "lt",
    "left": "fastWindow",
    "right": "slowWindow",
    "message": "短均线周期必须小于长均线周期"
  },
  {
    "type": "ordered",
    "fields": ["oversold", "overbought"],
    "min": 0,
    "max": 100,
    "message": "超卖阈值必须小于过热阈值"
  }
]
```

Factor-level constraints:

```json
[
  {
    "type": "gte",
    "left": "normalization.window",
    "right": "factor.window",
    "message": "标准化窗口不应小于因子计算窗口"
  },
  {
    "type": "sum",
    "fields": "factors[*].weight",
    "op": "eq",
    "value": 1,
    "message": "因子权重之和必须等于 1"
  }
]
```

## Factor Architecture

Add a pure factor layer under `src/lh_quant/factors/`.

```text
src/lh_quant/factors/
  __init__.py
  registry.py
  technical.py
  transforms.py
  schema.py
```

### Factor Definition

```python
@dataclass(frozen=True)
class FactorDefinition:
    id: str
    name: str
    category: str
    description: str
    params: tuple[FactorParamDefinition, ...]
    inputs: tuple[str, ...]
    lookback: int
    lag_policy: str
    output_kind: Literal["series", "dataframe"]
    compute: FactorCompute
```

Initial factors can be technical only:

- `ma`: moving average.
- `rsi`: RSI.
- `momentum`: N-day return.
- `breakout_high`: rolling high channel.
- `breakout_low`: rolling low channel.
- `volatility`: rolling volatility.
- `volume_ratio`: current volume versus rolling average.

Do not start with financial statements or industry neutralization in the first pass. The data layer is not ready yet.

### Factor Transforms

Support transforms as a pipeline:

- `lag`: shift factor by one bar to avoid lookahead.
- `zscore`: rolling or cross-sectional later.
- `rank`: percentile rank later.
- `winsorize`: cap outliers later.
- `fill`: forward fill, zero fill, or fail.

For the MVP, support `lag` and simple rolling `zscore` only.

### Strategy Uses Factors

Strategies should not recompute technical indicators privately. They should request factors:

```text
bars -> factor registry -> factor values -> strategy rule -> signal or target weight -> backtest
```

Near-term example:

- Strategy: `ma_with_rsi_filter`
- Entry: fast MA crosses above slow MA and RSI is below `maxEntryRsi`.
- Exit: fast MA crosses below slow MA or RSI is above `exitRsi`.
- Output: still `-1/0/1` so the current backtest engine can remain.

Later example:

- Strategy: `multi_factor_score`
- Inputs: momentum, volatility, volume ratio.
- Transform: lag and zscore.
- Combine: weighted score.
- Output: target weight, not discrete buy/sell signal.

## Backtest Engine Evolution

Do not rewrite the engine all at once. Evolve in three steps.

### Step 1: Make Current Assumptions Honest

- Add `execution.fillPrice`.
- Default to `next_open` instead of same-bar close, or explicitly label current behavior as `same_close_moc`.
- Save execution assumptions in run params.
- Add tests for no lookahead behavior.

### Step 2: Add Accounting Artifacts

Add orders, fills, positions, and returns while still supporting one symbol:

- `orders`: requested action.
- `fills`: simulated execution.
- `positions`: end-of-day position snapshot.
- `returns`: daily strategy return, benchmark return, excess return.

### Step 3: Move from Signals to Target Weights

Eventually strategies should output target weights:

```text
date, symbol, target_weight, reason
```

The portfolio layer converts target weights into orders, applies risk constraints, then the execution layer produces fills.

## API Changes

Keep these existing endpoints:

- `GET /api/health`
- `GET /api/strategies`
- `POST /api/backtests/run`
- `GET /api/backtests/runs`

Add:

- `GET /api/factors`
- `GET /api/instruments/search?q=`
- `GET /api/backtests/{runId}`
- `POST /api/backtests/compare`
- `POST /api/backtests/optimize`

### Extended Backtest Response

```json
{
  "runId": "bt_...",
  "config": {},
  "effectiveConfig": {},
  "dataSource": {},
  "dataLineage": {},
  "metrics": {},
  "bars": [],
  "benchmark": [],
  "returns": [],
  "indicatorPanels": [],
  "signals": [],
  "orders": [],
  "fills": [],
  "trades": [],
  "positions": [],
  "equityCurve": [],
  "logs": []
}
```

### Metrics to Add

Core:

- `benchmarkReturn`
- `excessReturn`
- `alpha`
- `beta`
- `informationRatio`
- `trackingError`
- `sortino`
- `calmar`
- `winRate`
- `profitFactor`
- `expectancy`
- `turnover`
- `exposure`
- `maxDrawdownStart`
- `maxDrawdownEnd`
- `maxDrawdownDuration`

Keep the first implementation simple and deterministic. Add formulas in tests.

## Storage Changes

Current JSON fields in `backtest_runs` are useful. Keep them for flexibility, but add versioning:

- `config_version`
- `config_hash`
- `engine_version`
- `data_snapshot_hash`

Add tables after the result model is stable:

- `backtest_orders`
- `backtest_fills`
- `backtest_positions`
- `backtest_returns`
- `backtest_factor_values`
- `instruments`
- `trading_calendar`
- `benchmark_bars`

For MVP, it is acceptable to persist richer artifacts in JSON under `backtest_runs.params/logs/metrics` and keep the existing detail tables. Add new tables when UI needs drill-down and comparison.

## Frontend Component Plan

Refactor from one large `App.tsx` into:

```text
apps/web/src/
  App.tsx
  api.ts
  types.ts
  components/
    EChart.tsx
    MetricStrip.tsx
    WorkbenchTabs.tsx
  features/
    configure/
      BacktestConfigForm.tsx
      StrategyParamForm.tsx
      FactorBuilder.tsx
      ExecutionConfigForm.tsx
    results/
      ResultOverview.tsx
      PriceSignalPanel.tsx
      RiskReturnPanel.tsx
      PositionPanel.tsx
      OrdersTradesPanel.tsx
      DataLineagePanel.tsx
    runs/
      RecentRunsPanel.tsx
      RunComparePanel.tsx
```

First refactor only where it pays off. Avoid moving everything before the schema changes exist.

## Error Handling and Validation

Backend remains the source of truth:

- Validate config shape.
- Validate strategy constraints.
- Validate factor constraints.
- Validate data coverage against trading calendar.
- Reject missing data when policy is `fail`.
- Reject same-bar execution unless explicitly requested.

Frontend gives immediate feedback:

- Render controls from schema.
- Evaluate simple constraints locally.
- Show dependency hints, such as "成交百分比只有启用限制成交量后生效".
- Show warnings for risky assumptions, such as same-bar close fill.

## Testing Strategy

Backend tests:

- Strategy constraint schema serialization.
- Frontend-compatible validation errors.
- Factor registry and factor outputs.
- Lag behavior to prevent lookahead.
- Execution fill price behavior.
- Metrics formulas with known equity curves.
- Run artifact persistence.

Frontend tests:

- Config form renders schema-driven controls.
- Constraint errors appear without hard-coded strategy IDs.
- Result tabs render empty and populated states.
- Recent run can be opened by `runId`.
- Compare view renders multiple metric rows.

End-to-end tests:

- Database disconnected locks run action.
- Successful backtest shows overview, price/signals, trades, and logs.
- Parameter change marks result stale.
- Open recent run restores previous config.

## Phased Roadmap

### Phase 0: Honest Baseline

- Fix documentation/API mismatch around Yahoo fallback.
- Label or change same-close execution.
- Add README commands for API and Web.
- Add result payload docs.

### Phase 1: Workbench Result Upgrade

- Add richer metrics.
- Persist enriched metrics.
- Add result tabs.
- Add run detail endpoint.
- Make recent runs clickable.

### Phase 2: Schema-Driven Configuration

- Extend strategy param metadata.
- Add constraints to `/api/strategies`.
- Replace frontend hard-coded strategy validation.
- Split config into Universe/Data/Strategy/Execution/Portfolio sections.

### Phase 3: Minimal Factor System

- Add `src/lh_quant/factors`.
- Extract MA/RSI/momentum calculations.
- Add `/api/factors`.
- Add one factor-enabled strategy.
- Add factor overlay and secondary indicator panel.

### Phase 4: Research Workflow

- Add benchmark curve and excess return.
- Add parameter scan endpoint.
- Add scan result table and heatmap.
- Add run compare.
- Add run notes/tags.

### Phase 5: Realistic Execution and Portfolio

- Add orders/fills/positions.
- Add next-open execution.
- Add slippage, tax, lot size, volume limit.
- Move toward target weights and multi-symbol support.

## MVP Recommendation

Build the next milestone as:

1. Result tabs and richer metrics.
2. Schema-driven strategy constraints.
3. Minimal factor registry with MA/RSI/momentum extraction.
4. One factor-enabled strategy: MA trend with RSI filter.
5. Data lineage panel showing provider, adjust, cache status, requested range, actual rows.

This is the best balance: it makes the product feel materially more like a quant workbench without forcing a full engine rewrite.

## Open Decisions

1. Should same-bar close execution be kept as an explicit option, or should `next_open` become the default immediately?
2. Should factor values be persisted from day one, or recomputed from run config until factor comparison exists?
3. Should the first benchmark be hard-coded to 沪深300, or user-selectable from the first version?
4. Should parameter scan run synchronously in the API process for MVP, or use a job table from the start?
5. Should the first UI step be result tabs or configuration refactor?

## Recommended Next Step

Create an implementation plan for Phase 1 and Phase 2 together:

- Phase 1 gives users better result interpretation immediately.
- Phase 2 prevents strategy/factor growth from turning the UI into hard-coded conditionals.

Do not start Phase 3 factor work until the config schema can express factor controls and constraints cleanly.
