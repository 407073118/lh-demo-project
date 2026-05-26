# Market Data Provider Selection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add selectable market data providers, normalize all provider outputs into one platform K-line contract, and persist data-source lineage for future accuracy analysis.

**Architecture:** The frontend sends a stable `dataProvider` enum with each backtest request. The backend uses a provider registry and provider chain to select cache/download sources, wraps each provider response in a shared `MarketDataResult`, validates normalized bars once, stores actual provider lineage, and returns requested/actual provider details in the backtest response.

**Tech Stack:** FastAPI, Pydantic, pandas, SQLAlchemy, pytest, React, TypeScript, Vite, Node test runner.

---

## Execution Constraint

This plan intentionally follows the user's requested code-first flow: implement code and test files first, then run one unified verification phase at the end.

Do not run `pytest`, `npm test`, `npm run build`, or other test/build commands during Tasks 1-7. Use file reads, `rg`, `git diff`, and static inspection only. If the final verification fails, fix the affected code and rerun the full final verification command set.

Do not create intermediate commits before final verification. Commit only after the final verification passes.

## Task 1: Extend Provider Data Contracts

**Files:**
- Modify: `src/lh_quant/data/providers.py`
- Modify: `src/lh_quant/data/tushare_provider.py`
- Modify: `src/lh_quant/data/__init__.py`

**Step 1: Expand `MarketDataResult`**

In `src/lh_quant/data/providers.py`, replace the current result shape with a lineage-aware contract:

```python
@dataclass(frozen=True)
class ProviderAttempt:
    provider: str
    status: str
    reason: str | None = None
    source_detail: str | None = None

    def to_json(self) -> dict[str, str]:
        payload = {"provider": self.provider, "status": self.status}
        if self.reason:
            payload["reason"] = self.reason
        if self.source_detail:
            payload["sourceDetail"] = self.source_detail
        return payload


@dataclass(frozen=True)
class MarketDataResult:
    bars: pd.DataFrame
    requested_provider: str
    actual_provider: str
    source_detail: str
    raw_symbol: str
    normalized_symbol: str
    frequency: str
    adjust: str
    data_version: str
    fetched_at: str
    fallback_chain: list[dict[str, str]]
```

Keep a short compatibility property if existing callers still read `result.provider` or `result.version`:

```python
@property
def provider(self) -> str:
    return self.actual_provider

@property
def version(self) -> str:
    return self.data_version
```

**Step 2: Add provider ID constants and display names**

Add stable backend IDs:

```python
ProviderId = Literal["auto", "tushare", "akshare", "yahoo"]

PROVIDER_DISPLAY_NAMES = {
    "tushare": "Tushare",
    "akshare": "AKShare",
    "yahoo": "Yahoo Finance",
}
```

Add `normalize_provider_id(value: str | None) -> ProviderId` that returns `"auto"` for empty input and raises `ValueError` for unknown IDs.

**Step 3: Add Tushare daily normalization**

In `src/lh_quant/data/tushare_provider.py`, add:

```python
def fetch_daily_bars(self, symbol: str, start: str, end: str) -> pd.DataFrame:
    payload = {
        "api_name": "daily",
        "token": self.token,
        "params": {
            "ts_code": _to_tushare_symbol(symbol),
            "start_date": _to_tushare_date(start),
            "end_date": _to_tushare_date(end),
        },
        "fields": "ts_code,trade_date,open,high,low,close,vol,amount",
    }
    response = self._request(payload)
    return normalize_tushare_daily(_rows(response), symbol=symbol)
```

Add helper behavior:

- `000001` -> `000001.SZ`
- `600519` -> `600519.SH`
- Already suffixed `000001.SZ` passes through uppercase.
- `vol` from Tushare is in lots, so platform `volume = vol * 100`.
- `trade_date` becomes `datetime`.
- Validate with `validate_bars`.

**Step 4: Add provider adapters**

In `src/lh_quant/data/providers.py`, keep `AkShareMarketDataProvider` and add:

```python
class TushareMarketDataProvider:
    provider_id = "tushare"
    display_name = "Tushare"

    def __init__(self, tushare_provider: TushareProvider | None = None) -> None:
        self._provider = tushare_provider

    def download_bars(self, symbol: str, start: str, end: str, adjust: str) -> MarketDataResult:
        if adjust:
            raise MarketDataProviderError("第一版暂不支持 Tushare 复权，请选择不复权或切换 AKShare")
        provider = self._provider or TushareProvider()
        bars = provider.fetch_daily_bars(symbol=symbol, start=start, end=end)
        raw_symbol = _to_tushare_symbol(symbol)
        return MarketDataResult(...)
```

Add `YahooMarketDataProvider` that wraps `download_yahoo_bars()` in the same `MarketDataResult` contract.

**Step 5: Export new provider objects**

Update `src/lh_quant/data/__init__.py` only if public imports are needed by tests or API. Keep exports small.

Do not run tests.

## Task 2: Add Provider Registry and Chain Logic

**Files:**
- Modify: `src/lh_quant/data/providers.py`

**Step 1: Add provider registry helpers**

Add:

```python
def provider_chain_for(requested_provider: str, adjust: str) -> list[str]:
    provider_id = normalize_provider_id(requested_provider)
    if provider_id != "auto":
        return [provider_id]
    if adjust:
        return ["akshare", "yahoo"]
    return ["tushare", "akshare", "yahoo"]
```

**Step 2: Add provider builder**

Add:

```python
def build_market_data_provider(provider_id: str) -> MarketDataProvider:
    normalized = normalize_provider_id(provider_id)
    if normalized == "akshare":
        return AkShareMarketDataProvider()
    if normalized == "tushare":
        return TushareMarketDataProvider()
    if normalized == "yahoo":
        return YahooMarketDataProvider()
    raise ValueError("auto cannot be built directly")
```

**Step 3: Add error type**

Add:

```python
class MarketDataProviderError(RuntimeError):
    pass
```

Adapters should wrap provider-specific errors in `MarketDataProviderError` where useful, while preserving clear messages.

Do not run tests.

## Task 3: Persist Source Lineage in Storage

**Files:**
- Modify: `src/lh_quant/storage/schema.py`
- Modify: `src/lh_quant/storage/repository.py`
- Modify: `src/lh_quant/storage/database.py` only if nullable-column migration needs adjustment

**Step 1: Extend ingestion schema with nullable lineage fields**

In `market_data_ingestions`, add nullable columns:

```python
Column("requested_provider", String(64), nullable=True),
Column("source_detail", String(256), nullable=True),
Column("raw_symbol", String(64), nullable=True),
Column("normalized_symbol", String(32), nullable=True),
Column("data_version", String(128), nullable=True),
Column("fetched_at", DateTime, nullable=True),
Column("fallback_chain", JSON, nullable=True),
```

Keep `provider` as the actual provider for cache identity.

**Step 2: Extend backtest run schema**

In `backtest_runs`, add:

```python
Column("requested_provider", String(64), nullable=True),
Column("fallback_chain", JSON, nullable=True),
```

Keep `provider` as the actual provider.

**Step 3: Extend `save_market_bars`**

Add optional keyword parameters:

```python
requested_provider: str | None = None
source_detail: str | None = None
raw_symbol: str | None = None
normalized_symbol: str | None = None
data_version: str | None = None
fetched_at: str | datetime | None = None
fallback_chain: list[dict[str, Any]] | None = None
```

Persist them into `market_data_ingestions`. Convert ISO text `fetched_at` to `datetime` before insert.

**Step 4: Extend `save_backtest_run`**

Add optional keyword parameters:

```python
requested_provider: str | None = None
fallback_chain: list[dict[str, Any]] | None = None
```

Persist them into `backtest_runs`.

**Step 5: Include lineage in run readers**

Update `list_backtest_runs()` and `load_backtest_run_detail()` summary mapping:

```python
"requestedProvider": row.get("requested_provider"),
"actualProvider": row.get("provider"),
"fallbackChain": row.get("fallback_chain") or [],
```

Do not run tests.

## Task 4: Refactor API to Use Provider Selection

**Files:**
- Modify: `src/lh_quant/api/app.py`

**Step 1: Add request field**

In both request models:

```python
dataProvider: str = Field(default="auto", description="行情数据来源：auto/tushare/akshare/yahoo")
```

When converting `MovingAverageBacktestRequest` to `BacktestRunRequest`, pass `dataProvider=request.dataProvider`.

**Step 2: Replace `_get_a_share_bars` with provider-aware helper**

Rename or replace with:

```python
def _get_market_bars(
    engine: Any,
    db_status: DatabaseStatus,
    requested_provider: str,
    symbol: str,
    start: str,
    end: str,
    adjust: str,
) -> tuple[pd.DataFrame, str, bool, list[str], dict[str, Any]]:
```

Inside:

1. Normalize requested provider.
2. Build `provider_chain_for(requested_provider, adjust)`.
3. For each provider in chain, first call `load_market_bars()` using that provider's display name.
4. If cache hits, return cached bars with `cached=True`, `actualProvider` set to that provider, and fallback chain containing a cache-hit attempt.
5. If no cache, call the provider adapter.
6. On success, call `save_market_bars()` with all lineage fields and return.
7. On failure in `auto`, append failed attempt and continue.
8. On failure in explicit mode, raise `ValueError` or `HTTPException` with the provider-specific message.

**Step 3: Update `_run_strategy_backtest`**

Replace the current `_get_a_share_bars(...)` call with `_get_market_bars(..., requested_provider=request.dataProvider, ...)`.

Pass provider lineage into:

- `_build_backtest_payload`
- `save_backtest_run`

**Step 4: Update response dataSource**

Keep existing `provider` field for compatibility. Add:

```python
"requestedProvider": data_lineage["requestedProvider"],
"actualProvider": data_lineage["actualProvider"],
"fallbackChain": data_lineage["fallbackChain"],
```

**Step 5: Update persisted-run restoration**

In persisted detail response builders, default old runs safely:

```python
requested = summary.get("requestedProvider") or summary["provider"]
actual = summary.get("actualProvider") or summary["provider"]
```

Also include `dataProvider` in `_request_from_run_summary`, defaulting to `requestedProvider` or `"auto"` if absent.

Do not run tests.

## Task 5: Update Frontend Request and UI

**Files:**
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/features/config/WorkbenchConfigSections.tsx`
- Modify: `apps/web/src/features/results/DataLineagePanel.tsx`

**Step 1: Extend API types**

In `api.ts` add:

```ts
export type DataProviderId = "auto" | "tushare" | "akshare" | "yahoo";

export type ProviderAttempt = {
  provider: string;
  status: string;
  reason?: string;
  sourceDetail?: string;
};
```

Add `dataProvider: DataProviderId` to `BacktestRequest`.

Add these fields to `BacktestResponse["dataSource"]`:

```ts
requestedProvider?: string;
actualProvider?: string;
fallbackChain?: ProviderAttempt[];
```

Add matching optional fields to `RunSummary`.

**Step 2: Add initial request default**

In `App.tsx`:

```ts
dataProvider: "auto",
```

Ensure `requestFromRunSummary()` restores old runs with:

```ts
dataProvider: typeof raw?.dataProvider === "string" ? raw.dataProvider : "auto",
```

**Step 3: Add data-source select**

In `UniverseDataSection`, add a label after adjust or near symbol:

```tsx
<label>
  数据来源
  <select
    value={form.dataProvider}
    onChange={(event) =>
      setForm((current) => ({
        ...current,
        dataProvider: event.target.value as BacktestRequest["dataProvider"]
      }))
    }
  >
    <option value="auto">自动</option>
    <option value="tushare">Tushare</option>
    <option value="akshare">AKShare</option>
    <option value="yahoo">Yahoo</option>
  </select>
</label>
```

**Step 4: Show lineage in results**

In `DataLineagePanel`, add rows:

```ts
["请求来源", result.dataSource.requestedProvider ?? result.strategy.params.dataProvider ?? "auto"],
["实际来源", result.dataSource.actualProvider ?? result.dataSource.provider],
["Fallback", formatFallbackChain(result.dataSource.fallbackChain ?? [])],
```

Add `formatFallbackChain()` that returns `"无"` for an empty chain and otherwise joins provider/status/reason snippets.

Do not run tests.

## Task 6: Author Backend Test Updates Without Running Them

**Files:**
- Modify: `tests/test_tushare_provider.py`
- Modify: `tests/test_data_providers.py`
- Modify: `tests/test_storage_database.py`
- Modify: `tests/test_api_app.py`

**Step 1: Add Tushare daily tests**

In `tests/test_tushare_provider.py`, add tests for:

- `daily` payload uses `ts_code=000001.SZ`.
- `trade_date` maps to `datetime`.
- `vol` is multiplied by `100`.
- permission errors remain explicit.

**Step 2: Update provider tests**

In `tests/test_data_providers.py`, update existing assertions from:

```python
assert result.provider == "AKShare"
assert result.version.startswith("akshare:")
```

to:

```python
assert result.actual_provider == "AKShare"
assert result.requested_provider == "akshare"
assert result.data_version.startswith("akshare:")
```

Add tests for:

- `provider_chain_for("auto", "") == ["tushare", "akshare", "yahoo"]`
- `provider_chain_for("auto", "qfq") == ["akshare", "yahoo"]`
- explicit provider returns only itself.

**Step 3: Add storage lineage tests**

In `tests/test_storage_database.py`, add direct SQLAlchemy queries against `market_data_ingestions` and `backtest_runs` to verify lineage columns persist.

Example expectation:

```python
assert row["requested_provider"] == "auto"
assert row["provider"] == "AKShare"
assert row["source_detail"] == "AKShare 东方财富日线接口"
assert row["fallback_chain"][0]["provider"] == "AKShare"
```

Also extend the existing nullable-column migration test to expect:

```python
"requested_provider",
"fallback_chain",
```

for `backtest_runs`.

**Step 4: Add API behavior tests**

In `tests/test_api_app.py`, add or update tests for:

- missing `dataProvider` defaults to `auto`.
- explicit `akshare` returns `requestedProvider=akshare` and `actualProvider=AKShare`.
- explicit `tushare` with `adjust=qfq` returns 400 with the unsupported复权 message.
- `auto` with `adjust=qfq` skips Tushare and uses AKShare.
- response `dataSource.provider` remains actual provider for backward compatibility.

Use monkeypatches for provider adapters so tests do not hit real external APIs.

Do not run tests.

## Task 7: Author Frontend Test Updates Without Running Them

**Files:**
- Modify: `apps/web/tests/ui-regressions.test.mjs`
- Modify: `apps/web/tests/e2e-smoke.test.mjs`

**Step 1: Update mock request/response payloads**

Add `dataProvider: "auto"` to test request fixtures.

Add response data source fields:

```js
requestedProvider: "auto",
actualProvider: "AKShare",
fallbackChain: []
```

**Step 2: Add UI assertions**

Add coverage that the form renders a `数据来源` select and that the default visible value is `自动`.

If existing text fixtures are mojibake due to encoding, match stable option values or form control behavior instead of brittle display text.

**Step 3: Keep smoke payloads backward compatible**

Ensure tests still accept old persisted run payloads without `requestedProvider` or `fallbackChain`.

Do not run tests.

## Task 8: Final Unified Verification

**Files:**
- Read only unless failures require fixes.

**Step 1: Inspect changed files**

Run:

```powershell
git status --short
git diff --stat
```

Expected:

- Only files from this implementation are modified.
- No unrelated `design.md/` changes are staged or altered.

**Step 2: Run backend focused tests**

Run:

```powershell
pytest tests/test_tushare_provider.py tests/test_data_providers.py tests/test_storage_database.py tests/test_api_app.py -q
```

Expected: all selected backend tests pass.

**Step 3: Run full backend test suite**

Run:

```powershell
pytest -q
```

Expected: full Python test suite passes.

**Step 4: Run frontend tests and build**

Run:

```powershell
npm test
npm run build
```

Workdir:

```text
apps/web
```

Expected:

- Node UI regression tests pass.
- TypeScript compilation succeeds.
- Vite build succeeds.

**Step 5: If verification fails**

Fix the failing implementation or test fixtures. Then rerun the full final verification set:

```powershell
pytest tests/test_tushare_provider.py tests/test_data_providers.py tests/test_storage_database.py tests/test_api_app.py -q
pytest -q
```

Then from `apps/web`:

```powershell
npm test
npm run build
```

Do not switch into per-task test loops. Keep verification consolidated.

## Task 9: Final Commit

**Files:**
- Stage only implementation files and test files touched by this plan.

**Step 1: Review final diff**

Run:

```powershell
git diff --stat
git diff
```

Expected: changes match this plan.

**Step 2: Stage changes**

Run:

```powershell
git add src/lh_quant/data/providers.py src/lh_quant/data/tushare_provider.py src/lh_quant/data/__init__.py src/lh_quant/storage/schema.py src/lh_quant/storage/repository.py src/lh_quant/storage/database.py src/lh_quant/api/app.py apps/web/src/api.ts apps/web/src/App.tsx apps/web/src/features/config/WorkbenchConfigSections.tsx apps/web/src/features/results/DataLineagePanel.tsx tests/test_tushare_provider.py tests/test_data_providers.py tests/test_storage_database.py tests/test_api_app.py apps/web/tests/ui-regressions.test.mjs apps/web/tests/e2e-smoke.test.mjs
```

If `storage/database.py` or a frontend test file was not actually modified, omit it from `git add`.

**Step 3: Commit**

Run:

```powershell
git commit -m "feat: add selectable market data providers"
```

Expected: one implementation commit after final verification passes.
