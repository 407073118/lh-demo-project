# Quant Platform Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the current single-symbol backtest MVP into a credible JoinQuant-like quant research foundation with trustworthy data assets, factor infrastructure, strategy metadata, data lineage, and an extensible provider layer.

**Architecture:** Keep the current FastAPI + SQLAlchemy + React/Vite stack. Add a provider abstraction around market data, persist data quality and lineage in new storage tables, expose real data assets and factor metadata through APIs, then upgrade the frontend from static catalog panels to usable data/strategy workspaces. External sources are integrated through authorized connectors; strategy code is never scraped or executed without explicit license and review metadata.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy Core, pandas, pytest, React, TypeScript, Vite, npm tests.

---

## Product Decision

Build this in three waves:

- **P0 Foundation:** Data model, provider abstraction, data quality, local factor registry, strategy metadata, frontend data asset page, lineage in backtest results.
- **P1 Research Workflow:** Tushare connector, sync jobs, factor computation pipeline, strategy library page, parameter presets/scans, richer history comparison.
- **P2 Platform Depth:** JoinQuant/RiceQuant factor adapters, factor analysis, multi-symbol portfolio engine, paper trading, strategy import review workflow.

The first implementation pass should complete P0 and leave clean seams for P1. This avoids spending another round on visual polish while the underlying platform still cannot explain where its data came from.

## External Source Policy

Use only authorized APIs and licensed assets:

- Tushare is suitable as the first formal A-share provider because its official docs expose both Python SDK and HTTP JSON access, including token-based calls and `trade_cal`.
- JoinQuant/jqdatasdk is suitable for licensed local data and factor access, but not for scraping platform strategy code.
- RiceQuant/RQFactor is suitable as a later professional factor research adapter.
- External strategy code enters the system only as user-owned code, open-source licensed code, official authorized templates, or locally reimplemented public formulas.

Reference links:

- Tushare Pro API docs: https://tushare.pro/document/1?doc_id=40
- JoinQuant jqdatasdk: https://github.com/JoinQuant/jqdatasdk
- RiceQuant RQFactor docs: https://www.ricequant.com/doc/rqfactor/manual/index-rqfactor

---

## Phase 0 Acceptance Criteria

- `/api/data/assets` returns real persisted data asset status, not a hard-coded static catalog.
- Market bar cache validation can use `trading_calendar` to detect missing trading days.
- Backtest responses and persisted runs include `dataVersion`, `sourceDetail`, `strategyVersion`, and engine assumptions.
- `/api/factors` returns local factor definitions and their status.
- Strategy definitions support richer metadata: version, source, license, tags, value types beyond only numeric.
- Frontend has real Data and Strategy Library views; unavailable modules are visibly disabled with reasons.
- No card uses the left colored border treatment the user rejected.
- Existing backend tests pass, and frontend regression tests pass.

---

## Task 1: Storage Schema Foundation

**Files:**
- Modify: `src/lh_quant/storage/schema.py`
- Test: `tests/test_storage_database.py`
- Test: `tests/test_data_contracts.py`

**Step 1: Write failing schema tests**

Add assertions that `metadata.tables` contains:

```python
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
```

Also assert key uniqueness:

```python
assert "uq_trading_calendar_identity" in {
    constraint.name for constraint in trading_calendar.constraints
}
assert "uq_factor_values_identity" in {
    constraint.name for constraint in factor_values.constraints
}
```

**Step 2: Run test to verify failure**

Run:

```powershell
pytest tests/test_storage_database.py tests/test_data_contracts.py -q
```

Expected: FAIL because the tables do not exist.

**Step 3: Add tables**

In `src/lh_quant/storage/schema.py`, add:

```python
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
```

Add similar tables:

- `trading_calendar`: `exchange`, `trade_date`, `is_open`, `pretrade_date`, `source`, unique by `exchange/trade_date`.
- `corporate_actions`: `symbol`, `event_date`, `action_type`, `value`, `source`, unique by `symbol/event_date/action_type/source`.
- `sync_jobs`: `job_id`, `job_type`, `provider`, `status`, `progress`, `started_at`, `completed_at`, `params`, `message`, `error`.
- `factor_definitions`: `factor_id`, `name`, `category`, `frequency`, `direction`, `formula`, `source`, `license`, `status`, `description`.
- `factor_values`: `factor_id`, `symbol`, `trade_date`, `value`, `source`, `version`, unique by those identity fields.
- `factor_runs`: `run_id`, `factor_id`, `provider`, `status`, `start_date`, `end_date`, `row_count`, `message`.
- `strategy_sources`: `source_id`, `name`, `source_type`, `url`, `license`, `sync_policy`, `executable`, `review_status`.

Add indexes for query paths:

```python
Index("ix_factor_values_query", factor_values.c.factor_id, factor_values.c.symbol, factor_values.c.trade_date)
Index("ix_sync_jobs_status", sync_jobs.c.status, sync_jobs.c.started_at)
```

**Step 4: Run schema tests**

Run:

```powershell
pytest tests/test_storage_database.py tests/test_data_contracts.py -q
```

Expected: PASS.

**Step 5: Commit**

```powershell
git add src/lh_quant/storage/schema.py tests/test_storage_database.py tests/test_data_contracts.py
git commit -m "feat: add quant data foundation schema"
```

---

## Task 2: Repository Functions for Data Assets and Quality

**Files:**
- Create: `src/lh_quant/storage/data_repository.py`
- Modify: `src/lh_quant/storage/__init__.py`
- Test: `tests/test_data_repository.py`

**Step 1: Write failing repository tests**

Create tests for:

- Upserting trading calendar rows.
- Listing expected open trading dates.
- Reporting market bar coverage as `complete`, `missing`, or `unknown`.
- Creating and completing sync jobs.
- Upserting factor definitions.

Example:

```python
def test_market_bar_coverage_detects_missing_trading_day(sqlite_engine):
    upsert_trading_calendar(
        sqlite_engine,
        [
            {"exchange": "SSE", "trade_date": "2024-01-02", "is_open": True, "source": "test"},
            {"exchange": "SSE", "trade_date": "2024-01-03", "is_open": True, "source": "test"},
        ],
    )
    coverage = inspect_market_bar_coverage(
        sqlite_engine,
        provider="AKShare",
        symbol="600519",
        exchange="SSE",
        frequency="1d",
        adjust="qfq",
        start="2024-01-02",
        end="2024-01-03",
    )
    assert coverage.status == "missing"
    assert coverage.expected_rows == 2
```

**Step 2: Run test to verify failure**

```powershell
pytest tests/test_data_repository.py -q
```

Expected: FAIL because module/functions do not exist.

**Step 3: Implement data repository**

Create dataclasses:

```python
@dataclass(frozen=True)
class CoverageReport:
    status: Literal["complete", "missing", "unknown"]
    expected_rows: int | None
    actual_rows: int
    missing_dates: list[str]
    last_trade_date: str | None
```

Implement functions:

- `upsert_instruments(engine, records) -> int`
- `upsert_trading_calendar(engine, records) -> int`
- `get_open_trade_dates(engine, exchange, start, end) -> list[date]`
- `inspect_market_bar_coverage(...) -> CoverageReport`
- `create_sync_job(engine, job_type, provider, params) -> str`
- `update_sync_job(engine, job_id, status, progress, message=None, error=None) -> None`
- `upsert_factor_definitions(engine, definitions) -> int`
- `list_factor_definitions(engine) -> list[dict]`

Use SQLAlchemy Core only, matching the current repository style.

**Step 4: Run repository tests**

```powershell
pytest tests/test_data_repository.py -q
```

Expected: PASS.

**Step 5: Commit**

```powershell
git add src/lh_quant/storage/data_repository.py src/lh_quant/storage/__init__.py tests/test_data_repository.py
git commit -m "feat: add data asset repository"
```

---

## Task 3: Provider Abstraction

**Files:**
- Create: `src/lh_quant/data/providers.py`
- Modify: `src/lh_quant/data/akshare_provider.py`
- Modify: `src/lh_quant/api/app.py`
- Test: `tests/test_data_providers.py`
- Test: `tests/test_akshare_provider.py`

**Step 1: Write failing provider tests**

Test that:

- Provider result includes `provider`, `source_detail`, `version`, `bars`.
- Empty Eastmoney response falls back to Tencent instead of immediately failing.
- `_get_a_share_bars()` uses provider metadata in logs and payload.

**Step 2: Add provider types**

Create:

```python
@dataclass(frozen=True)
class MarketDataResult:
    bars: pd.DataFrame
    provider: str
    source_detail: str
    version: str

class MarketDataProvider(Protocol):
    provider_id: str
    def download_bars(self, symbol: str, start: str, end: str, adjust: str) -> MarketDataResult:
        ...
```

**Step 3: Wrap AKShare**

Add `AkShareMarketDataProvider` that calls existing normalization functions and returns `MarketDataResult`.

Fix empty response behavior:

```python
if raw.empty:
    eastmoney_error = AkShareDataError(...)
else:
    ...
```

Then continue to Tencent fallback.

**Step 4: Update API data fetch**

In `src/lh_quant/api/app.py`, change `_get_a_share_bars()` to use a provider instance, but keep the current public API stable.

Add `dataVersion` and `sourceDetail` to `dataSource` JSON.

**Step 5: Run tests**

```powershell
pytest tests/test_akshare_provider.py tests/test_data_providers.py tests/test_api_app.py -q
```

Expected: PASS.

**Step 6: Commit**

```powershell
git add src/lh_quant/data/providers.py src/lh_quant/data/akshare_provider.py src/lh_quant/api/app.py tests/test_data_providers.py tests/test_akshare_provider.py tests/test_api_app.py
git commit -m "feat: introduce market data provider abstraction"
```

---

## Task 4: Calendar-Aware Cache Completeness

**Files:**
- Modify: `src/lh_quant/storage/repository.py`
- Modify: `src/lh_quant/storage/data_repository.py`
- Modify: `src/lh_quant/api/app.py`
- Test: `tests/test_storage_database.py`
- Test: `tests/test_api_app.py`

**Step 1: Write failing tests**

Add cases:

- Cache is not used when a trading day is missing.
- Cache can still be used when no calendar exists, but payload marks quality as `unknown`.
- Cache result contains `coverage.status`, `expectedRows`, `actualRows`, `missingDates`.

**Step 2: Implement coverage-aware loading**

Add optional `coverage_report` support:

```python
def load_market_bars(..., require_calendar_complete: bool = False) -> pd.DataFrame | None:
    ...
```

Prefer a separate helper if return type churn gets too large:

```python
def load_market_bars_with_coverage(...) -> tuple[pd.DataFrame | None, CoverageReport]:
```

**Step 3: Update `_get_a_share_bars()` logs**

When cached:

- Complete: `"已从数据库读取完整行情缓存"`
- Unknown: `"已从数据库读取行情缓存；未配置交易日历，完整性未知"`
- Missing: download fresh data.

**Step 4: Run tests**

```powershell
pytest tests/test_storage_database.py tests/test_api_app.py -q
```

Expected: PASS.

**Step 5: Commit**

```powershell
git add src/lh_quant/storage/repository.py src/lh_quant/storage/data_repository.py src/lh_quant/api/app.py tests/test_storage_database.py tests/test_api_app.py
git commit -m "feat: validate market cache against trading calendar"
```

---

## Task 5: Backtest Data Lineage

**Files:**
- Modify: `src/lh_quant/storage/schema.py`
- Modify: `src/lh_quant/storage/repository.py`
- Modify: `src/lh_quant/api/app.py`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/features/results/DataLineagePanel.tsx`
- Test: `tests/test_api_app.py`
- Test: `apps/web/tests/ui-regressions.test.mjs`

**Step 1: Write failing backend test**

Assert backtest response includes:

```python
lineage = payload["dataSource"]
assert set(lineage) >= {
    "provider",
    "sourceDetail",
    "dataVersion",
    "coverage",
    "engineAssumptions",
}
```

Assert persisted run detail returns the same fields.

**Step 2: Add persisted columns**

Add to `backtest_runs`:

- `data_source_detail` String
- `data_version` String
- `strategy_version` String
- `engine_version` String
- `engine_assumptions` JSON
- `run_inputs` JSON

SQLite tests use `metadata.create_all`, so no migration is needed yet. If production MySQL already has tables, add a follow-up migration task before deployment.

**Step 3: Update save/load repository**

Extend `save_backtest_run()` parameters with lineage fields. Extend list/detail serializers.

**Step 4: Update frontend types and panel**

In `apps/web/src/api.ts`, extend `BacktestResponse["dataSource"]`.

In `DataLineagePanel.tsx`, show:

- Provider
- Source detail
- Data version
- Cache status
- Coverage status
- Engine assumptions

**Step 5: Run tests**

```powershell
pytest tests/test_api_app.py -q
cd apps/web; npm test
```

Expected: PASS.

**Step 6: Commit**

```powershell
git add src/lh_quant/storage/schema.py src/lh_quant/storage/repository.py src/lh_quant/api/app.py apps/web/src/api.ts apps/web/src/features/results/DataLineagePanel.tsx tests/test_api_app.py apps/web/tests/ui-regressions.test.mjs
git commit -m "feat: persist backtest data lineage"
```

---

## Task 6: Local Factor Registry

**Files:**
- Create: `src/lh_quant/factors/__init__.py`
- Create: `src/lh_quant/factors/registry.py`
- Create: `src/lh_quant/factors/basic.py`
- Modify: `src/lh_quant/api/app.py`
- Test: `tests/test_factor_registry.py`
- Test: `tests/test_api_app.py`

**Step 1: Write failing tests**

Test factor specs:

```python
specs = get_factor_specs()
assert {factor["id"] for factor in specs} >= {
    "return_20d",
    "volatility_20d",
    "ma_20d",
    "rsi_14d",
}
```

Test calculation shape:

```python
values = calculate_factor("return_20d", bars)
assert len(values) == len(bars)
assert values.name == "return_20d"
```

**Step 2: Implement definitions**

Create dataclass:

```python
@dataclass(frozen=True)
class FactorDefinition:
    id: str
    name: str
    category: str
    frequency: str
    direction: Literal["positive", "negative", "neutral"]
    description: str
    source: str
    license: str
    calculator: Callable[[pd.DataFrame], pd.Series]
```

Add basic factors:

- `return_5d`
- `return_20d`
- `volatility_20d`
- `ma_20d`
- `ema_20d`
- `rsi_14d`
- `volume_ma_20d`

**Step 3: Add API**

In `create_app()`:

```python
@application.get("/api/factors")
def list_factors() -> dict[str, Any]:
    return {"factors": get_factor_specs()}
```

**Step 4: Run tests**

```powershell
pytest tests/test_factor_registry.py tests/test_api_app.py -q
```

Expected: PASS.

**Step 5: Commit**

```powershell
git add src/lh_quant/factors src/lh_quant/api/app.py tests/test_factor_registry.py tests/test_api_app.py
git commit -m "feat: add local factor registry"
```

---

## Task 7: Strategy Metadata Upgrade

**Files:**
- Modify: `src/lh_quant/strategies/registry.py`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/strategyConstraints.ts`
- Test: `tests/test_strategy_registry.py`
- Test: `apps/web/tests/ui-regressions.test.mjs`

**Step 1: Write failing tests**

Backend:

```python
strategy = get_strategy_specs()[0]
assert set(strategy) >= {"version", "source", "license", "tags", "supportedFrequencies"}
assert {param["valueType"] for param in strategy["params"]} <= {
    "int", "float", "bool", "enum", "factor", "universe"
}
```

Frontend:

```js
assert.match(apiSource, /valueType: "int" \| "float" \| "bool" \| "enum"/)
```

**Step 2: Extend dataclasses**

Add fields to `StrategyDefinition`:

- `version`
- `source`
- `license`
- `tags`
- `supported_frequencies`
- `risk_level`

Add param value types:

- `bool`
- `enum`
- `factor`
- `universe`

Do not add behavior for portfolio strategy yet; this is metadata and validation only.

**Step 3: Update API and frontend types**

Update `StrategyParamDefinition` in `apps/web/src/api.ts`.

Update validation logic in `strategyConstraints.ts` so unknown future constraints fail gracefully with a user-facing message instead of crashing.

**Step 4: Run tests**

```powershell
pytest tests/test_strategy_registry.py -q
cd apps/web; npm test
```

Expected: PASS.

**Step 5: Commit**

```powershell
git add src/lh_quant/strategies/registry.py apps/web/src/api.ts apps/web/src/strategyConstraints.ts tests/test_strategy_registry.py apps/web/tests/ui-regressions.test.mjs
git commit -m "feat: enrich strategy metadata schema"
```

---

## Task 8: Data Assets API

**Files:**
- Modify: `src/lh_quant/api/app.py`
- Modify: `src/lh_quant/storage/data_repository.py`
- Test: `tests/test_api_app.py`

**Step 1: Write failing API tests**

Test:

```python
response = client.get("/api/data/assets")
assert response.status_code == 200
asset = response.json()["assets"][0]
assert set(asset) >= {
    "id",
    "name",
    "provider",
    "status",
    "coverage",
    "lastSync",
    "quality",
    "rowCount",
}
```

Test detail:

```python
response = client.get("/api/data/assets/a_share_daily_bars")
assert response.status_code == 200
assert "fields" in response.json()["asset"]
assert "syncJobs" in response.json()["asset"]
```

**Step 2: Implement endpoints**

Add:

- `GET /api/data/assets`
- `GET /api/data/assets/{asset_id}`
- `GET /api/data/sync-jobs`

These can initially summarize persisted `market_bars`, `market_data_ingestions`, `factor_definitions`, and `sync_jobs`.

**Step 3: Keep old catalog endpoint**

Keep `/api/data/catalog` as a compatibility wrapper, but make it call the new data asset service instead of returning only static planned datasets.

**Step 4: Run tests**

```powershell
pytest tests/test_api_app.py -q
```

Expected: PASS.

**Step 5: Commit**

```powershell
git add src/lh_quant/api/app.py src/lh_quant/storage/data_repository.py tests/test_api_app.py
git commit -m "feat: expose real data asset APIs"
```

---

## Task 9: Frontend Data Workspace

**Files:**
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/styles.css`
- Create: `apps/web/src/features/data/DataAssetsPage.tsx`
- Create: `apps/web/src/features/data/DataAssetDetail.tsx`
- Test: `apps/web/tests/ui-regressions.test.mjs`
- Test: `apps/web/tests/e2e-smoke.test.mjs`

**Step 1: Write failing frontend tests**

Assert:

- The app contains a Data workspace label.
- Data asset UI does not contain the old left-border card class/pattern.
- Empty/disconnected state contains actions for configure database, use sample data, retry.

**Step 2: Add API types**

Add:

```ts
export type DataAsset = {
  id: string;
  name: string;
  provider: string;
  status: "available" | "preview" | "planned" | "degraded";
  coverage: string;
  lastSync: string | null;
  quality: {
    status: "complete" | "missing" | "unknown";
    score: number | null;
    message: string;
  };
  rowCount: number;
};
```

Add `fetchDataAssets()` and `fetchDataAssetDetail()`.

**Step 3: Implement page**

Use a table/list hybrid, not decorative cards:

- Asset name
- Provider
- Status pill
- Coverage
- Last sync
- Quality score
- Row count
- Detail button

Use 8px radius or less.

**Step 4: Wire navigation**

In `App.tsx`, replace fake top nav behavior with local view state:

- `data`
- `research`
- `backtest`
- `strategies`
- `history`

For unavailable modules, render disabled buttons with clear tooltip/title.

**Step 5: Run tests**

```powershell
cd apps/web
npm test
```

Expected: PASS.

**Step 6: Commit**

```powershell
git add apps/web/src/api.ts apps/web/src/App.tsx apps/web/src/styles.css apps/web/src/features/data apps/web/tests
git commit -m "feat: add data asset workspace"
```

---

## Task 10: Frontend Strategy Library

**Files:**
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/styles.css`
- Create: `apps/web/src/features/strategies/StrategyLibraryPage.tsx`
- Test: `apps/web/tests/ui-regressions.test.mjs`

**Step 1: Write failing tests**

Assert:

- Strategy library renders search input and category filter.
- Strategy items show version, source, license, tags, risk level.
- Numeric params still render in the backtest form.

**Step 2: Implement library**

Features:

- Search by name/description/tag.
- Filter by category.
- Sort by built-in first, then external/reviewed later.
- Select strategy button updates existing backtest strategy selection.

**Step 3: Update backtest config rendering**

Render controls by `valueType`:

- `int`/`float`: number input.
- `bool`: checkbox/toggle.
- `enum`: select.
- `factor`: select from `/api/factors`.
- `universe`: select or disabled placeholder until universe API exists.

**Step 4: Run tests**

```powershell
cd apps/web
npm test
```

Expected: PASS.

**Step 5: Commit**

```powershell
git add apps/web/src/api.ts apps/web/src/App.tsx apps/web/src/styles.css apps/web/src/features/strategies apps/web/tests/ui-regressions.test.mjs
git commit -m "feat: add strategy library workspace"
```

---

## Task 11: Tushare Connector Design Stub

**Files:**
- Create: `src/lh_quant/data/tushare_provider.py`
- Modify: `src/lh_quant/data/providers.py`
- Modify: `.env.example`
- Test: `tests/test_tushare_provider.py`

**Step 1: Write failing tests with fake HTTP client**

Do not call the real network in tests.

Test:

- Missing token raises a clear error.
- `fetch_trade_calendar()` maps Tushare `trade_cal` payload into `trading_calendar` records.
- HTTP response code `2002` raises permission error.

**Step 2: Implement minimal HTTP client**

Use the official HTTP JSON shape:

```python
{
    "api_name": "trade_cal",
    "token": token,
    "params": {"exchange": "", "start_date": "20240101", "end_date": "20240131"},
    "fields": "exchange,cal_date,is_open,pretrade_date"
}
```

Use dependency injection for the HTTP caller so tests can pass a fake client.

**Step 3: Add env docs**

In `.env.example`:

```env
TUSHARE_TOKEN=
LH_QUANT_PRIMARY_PROVIDER=AKShare
```

Do not make Tushare mandatory.

**Step 4: Run tests**

```powershell
pytest tests/test_tushare_provider.py -q
```

Expected: PASS.

**Step 5: Commit**

```powershell
git add src/lh_quant/data/tushare_provider.py src/lh_quant/data/providers.py .env.example tests/test_tushare_provider.py
git commit -m "feat: add Tushare connector stub"
```

---

## Task 12: Verification Pass

**Files:**
- No new production files unless tests expose a bug.

**Step 1: Run backend tests**

```powershell
pytest -q
```

Expected: PASS.

**Step 2: Run frontend tests**

```powershell
cd apps/web
npm test
```

Expected: PASS.

**Step 3: Run lint if configured**

```powershell
ruff check .
```

Expected: PASS, or only pre-existing unrelated warnings documented.

**Step 4: Manual UI check**

Start backend and frontend:

```powershell
uvicorn lh_quant.api.app:create_app --factory --reload
```

In another terminal:

```powershell
cd apps/web
npm run dev
```

Open the Vite URL and verify:

- Data page is useful and not decorative.
- Strategy Library page is searchable.
- Backtest still runs.
- Result lineage panel shows provider/source/version/assumptions.
- No left colored border cards remain.

**Step 5: Commit final fixes**

```powershell
git status --short
git add .
git commit -m "test: verify quant platform foundation"
```

---

## Phase 1 Backlog After P0

- Implement real Tushare sync job endpoint: `POST /api/data/sync-jobs`.
- Add `GET /api/factors/{factor_id}/values`.
- Persist locally computed factor values.
- Add factor analysis: IC, IR, quantile return, turnover.
- Add parameter scan jobs and compare page.
- Add benchmark returns and yearly/monthly return tables.
- Add multi-symbol portfolio backtest engine.

## Phase 2 Backlog After P1

- JoinQuant/jqdatasdk adapter for licensed factor/data access.
- RiceQuant/RQFactor adapter for professional factor research.
- Strategy import review workflow with source/license/security status.
- Paper trading model with portfolio, orders, fills, positions, risk logs.
- Optional advanced engine evaluation: LEAN or a stricter internal engine.

## Execution Options

1. **Subagent-Driven in this session:** Split by task, dispatch workers for backend schema/repository, provider/factors, and frontend data/strategy pages, with review after each task.
2. **Sequential in this session:** Implement P0 task by task locally, slower but easier to keep architecture tight.
3. **Separate implementation session:** Open a new session on this plan and execute with `executing-plans`.

Recommended: option 1 for speed, with backend schema/repository done first because every other slice depends on it.
