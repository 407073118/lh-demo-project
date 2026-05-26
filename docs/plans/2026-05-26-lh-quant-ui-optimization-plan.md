# LH Quant UI Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rework the current LH Quant web UI into a RiceQuant / JoinQuant-inspired research workbench where the result page answers "what happened, can I trust it, and what should I do next" in the first viewport.

**Architecture:** Keep the existing React/Vite/ECharts app and the current backend API. Refactor the result workspace around a compact run context, a first-screen analysis grid, a data-confidence panel, compact decision metrics, and a report navigation structure. Keep editing mode as an IDE-style workspace, but only add accurate run actions in this phase; defer a true fast-backtest backend until a separate engine task exists.

**Tech Stack:** React 19, TypeScript, Vite, ECharts, Node test runner, Playwright, CSS modules via global `styles.css`.

---

## Source Material

- Reverse-engineering research: `docs/research/2026-05-26-ricequant-joinquant-ui-ux-reverse-engineering.md`
- Current design contract: `apps/web/DESIGN.md`
- Current result dashboard: `apps/web/src/features/results/ResultDashboard.tsx`
- Current metric overview: `apps/web/src/features/results/ResultOverview.tsx`
- Current result panels: `apps/web/src/features/results/PriceSignalPanel.tsx`, `RiskReturnPanel.tsx`, `OrdersTradesPanel.tsx`, `DataLineagePanel.tsx`
- Current app shell and run setup: `apps/web/src/App.tsx`
- Current regression tests: `apps/web/tests/ui-regressions.test.mjs`
- Current browser smoke test: `apps/web/tests/e2e-smoke.test.mjs`

## Product Constraints

- Do not build a landing page or marketing surface. The first screen remains the workbench.
- Do not hide core analysis behind top-level tabs. Use report navigation for structure while keeping the primary chart visible.
- Do not fake unsupported backend behavior. Phase 1 may add "校验配置" and rename the primary run action, but a true "快速回测" is out of scope until the backend supports a distinct fast run.
- Keep A-share market semantics: red means buy/up, green means sell/down.
- Split market semantics from risk semantics: drawdown, missing data, failed jobs, and coverage gaps use risk or neutral colors, not market green.
- Keep panels dense, aligned to the existing 8px grid, with radius <= 8px.
- Preserve the existing browser smoke screenshot flow and update it to verify the new first viewport.

## Phase 0: Preflight

**Files:**

- Read: `apps/web/package.json`
- Read: `apps/web/tests/ui-regressions.test.mjs`
- Read: `apps/web/tests/e2e-smoke.test.mjs`

**Step 1: Confirm workspace state**

Run:

```powershell
Get-Location
git status --short --branch
```

Expected:

- Current directory is `E:\lh`.
- Record any unrelated dirty files. Do not revert them.

**Step 2: Run current frontend checks**

Run:

```powershell
cd apps\web
npm run test
npm run build
npm run smoke:e2e
cd ..\..
```

Expected:

- Frontend regression tests pass.
- TypeScript/Vite build passes.
- Browser smoke test passes and writes screenshots to `.codex-artifacts`.

**Step 3: Inspect the baseline screenshot**

Open:

- `E:\lh\.codex-artifacts\web-dashboard-smoke.png`
- `E:\lh\.codex-artifacts\web-dashboard-1600-smoke.png`
- `E:\lh\.codex-artifacts\web-dashboard-1920-smoke.png`
- `E:\lh\.codex-artifacts\web-dashboard-mobile-smoke.png`

Expected:

- Confirm the current dashboard-first layout before refactoring.
- Record visible issues in implementation notes: oversized metric cards, empty indicator detail row, weak data-confidence priority, and mobile run-context truncation.

---

## Task 1: Update Design Contract for the New Workbench Direction

**Files:**

- Modify: `apps/web/DESIGN.md`
- Modify: `apps/web/tests/ui-regressions.test.mjs`

**Step 1: Write failing design-contract tests**

Append tests to `apps/web/tests/ui-regressions.test.mjs`:

```js
test("design contract captures RiceQuant and JoinQuant inspired workbench rules", () => {
  const design = read("DESIGN.md");

  assert.match(design, /RiceQuant/i);
  assert.match(design, /JoinQuant/i);
  assert.match(design, /result report/i);
  assert.match(design, /RunConfidencePanel/);
  assert.match(design, /market semantics/i);
  assert.match(design, /risk semantics/i);
  assert.match(design, /do not fake fast backtest/i);
});
```

**Step 2: Run the failing test**

Run:

```powershell
cd apps\web
npm run test -- --test-name-pattern "design contract captures RiceQuant"
```

Expected:

- FAIL because `DESIGN.md` does not yet contain the new contract language.

**Step 3: Update `apps/web/DESIGN.md`**

Add sections after `## Layout`:

```markdown
## Competitive Model

The workbench borrows JoinQuant's IDE-first editing flow and RiceQuant's report-first result flow. Editing mode should feel like a compact strategy IDE: resource tree, code or strategy surface, run setup, and output logs. Result mode should feel like a backtest report: run identity, primary chart, data confidence, risk/return diagnostics, orders/trades, lineage, and logs.

## Result Report

Result mode starts with a compact run-context bar, a compact metric strip, then a first-screen grid: primary chart on the left and `RunConfidencePanel` on the right. The report navigation should expose Overview, Returns/Risk, Price/Signals, Orders/Trades, Data Lineage, and Logs without hiding the primary chart behind a top-level tab.

## Color Semantics

Market semantics and risk semantics are separate. Market red/green is reserved for A-share price movement and buy/sell markers. Risk semantics cover drawdown, missing data, failed jobs, stale configs, and coverage gaps, and should use risk or neutral colors rather than market green.

## Run Actions

Do not fake a fast backtest. Until the backend exposes a distinct lightweight run endpoint, the run panel may provide configuration validation and one accurate full-run action only.
```

Also update the frontmatter tokens with `risk`, `risk-muted`, and `confidence` colors.

**Step 4: Run the design-contract test**

Run:

```powershell
cd apps\web
npm run test -- --test-name-pattern "design contract captures RiceQuant"
```

Expected:

- PASS.

**Step 5: Commit**

```powershell
git add apps/web/DESIGN.md apps/web/tests/ui-regressions.test.mjs
git commit -m "docs: update quant workbench ui contract"
```

---

## Task 2: Lock the New Result Workspace Structure with Regression Tests

**Files:**

- Modify: `apps/web/tests/ui-regressions.test.mjs`
- Modify: `apps/web/tests/e2e-smoke.test.mjs`

**Step 1: Add static regression tests**

Update or replace the current test named `result dashboard exposes a compact run context before charts` with:

```js
test("result dashboard uses report-first layout with confidence panel and compact metrics", () => {
  const dashboard = read("src/features/results/ResultDashboard.tsx");
  const overview = read("src/features/results/ResultOverview.tsx");
  const styles = read("src/styles.css");

  assert.match(dashboard, /RunContextBar/);
  assert.match(dashboard, /RunConfidencePanel/);
  assert.match(dashboard, /ResultReportNav/);
  assert.match(dashboard, /className="result-first-grid"/);
  assert.match(overview, /compact-metric-strip/);
  assert.doesNotMatch(overview, /metric-detail-disclosure/);
  assert.match(styles, /\.result-first-grid/);
  assert.match(styles, /\.run-confidence-panel/);
  assert.match(styles, /\.result-report-nav/);
});
```

Add a color semantics test:

```js
test("market and risk color semantics are separated", () => {
  const styles = read("src/styles.css");

  assert.match(styles, /--color-market-up/);
  assert.match(styles, /--color-market-down/);
  assert.match(styles, /--color-risk/);
  assert.match(styles, /--color-risk-muted/);
  assert.match(styles, /\.risk-text/);
});
```

**Step 2: Add browser smoke assertions**

In `apps/web/tests/e2e-smoke.test.mjs`, after waiting for `result-dashboard`, add:

```js
await page.locator('[data-testid="result-report-nav"]').waitFor({ state: "visible" });
await page.locator('[data-testid="run-confidence-panel"]').waitFor({ state: "visible" });
assert.equal(await page.locator(".metric-detail-disclosure").count(), 0);
```

In `assertResultLayout`, add:

```js
const confidence = document.querySelector('[data-testid="run-confidence-panel"]')?.getBoundingClientRect();
const reportNav = document.querySelector('[data-testid="result-report-nav"]')?.getBoundingClientRect();
```

Return `confidenceTop`, `confidenceWidth`, and `reportNavTop`, then assert:

```js
assert.ok(layout.reportNavTop < 220, `expected report navigation near first viewport at ${width}px`);
if (width >= 1366) {
  assert.ok(layout.confidenceWidth >= 260, `expected useful confidence panel at ${width}px`);
}
```

**Step 3: Run tests to confirm failure**

Run:

```powershell
cd apps\web
npm run test
```

Expected:

- FAIL because new components/classes do not exist yet.

**Step 4: Commit failing tests only if your workflow allows test-first commits**

If following strict TDD commits:

```powershell
git add apps/web/tests/ui-regressions.test.mjs apps/web/tests/e2e-smoke.test.mjs
git commit -m "test: define result workbench ui contract"
```

If not committing red tests, keep changes unstaged and continue to Task 3.

---

## Task 3: Add `RunConfidencePanel`

**Files:**

- Create: `apps/web/src/features/results/RunConfidencePanel.tsx`
- Modify: `apps/web/src/features/results/ResultDashboard.tsx`
- Modify: `apps/web/src/styles.css`

**Step 1: Create the component**

Create `apps/web/src/features/results/RunConfidencePanel.tsx`:

```tsx
import type { BacktestResponse } from "../../api";

type ConfidenceDrawer = "job" | "history" | "lineage" | "trade";

type RunConfidencePanelProps = {
  result: BacktestResponse;
  onOpenConfig?: () => void;
  onOpenInspector?: (drawer: ConfidenceDrawer) => void;
};

export function RunConfidencePanel({
  result,
  onOpenConfig,
  onOpenInspector
}: RunConfidencePanelProps) {
  const coverage = result.dataSource.coverage;
  const coverageStatus = coverage?.status ?? "unknown";
  const actualProvider = result.dataSource.actualProvider ?? result.dataSource.provider;
  const requestedProvider = result.dataSource.requestedProvider ?? "auto";
  const fallbackCount = result.dataSource.fallbackChain?.length ?? 0;
  const missingCount = coverage?.missingDates.length ?? 0;

  return (
    <aside className={`run-confidence-panel ${coverageStatus}`} data-testid="run-confidence-panel">
      <div className="confidence-header">
        <span>可信度</span>
        <strong>{confidenceLabel(coverageStatus, missingCount)}</strong>
      </div>
      <dl className="confidence-grid">
        <div>
          <dt>实际来源</dt>
          <dd>{actualProvider}</dd>
        </div>
        <div>
          <dt>请求来源</dt>
          <dd>{requestedProvider}</dd>
        </div>
        <div>
          <dt>复权</dt>
          <dd>{result.dataSource.adjust || "不复权"}</dd>
        </div>
        <div>
          <dt>数据版本</dt>
          <dd>{result.dataSource.dataVersion ?? "unknown"}</dd>
        </div>
        <div>
          <dt>K线数量</dt>
          <dd>{coverage?.actualRows ?? result.bars.length}</dd>
        </div>
        <div>
          <dt>缺失日期</dt>
          <dd className={missingCount > 0 ? "risk-text" : undefined}>{missingCount}</dd>
        </div>
        <div>
          <dt>引擎</dt>
          <dd>{result.dataSource.engineVersion ?? "signal-close-v1"}</dd>
        </div>
        <div>
          <dt>回退链</dt>
          <dd>{fallbackCount}</dd>
        </div>
      </dl>
      <div className="confidence-actions" aria-label="可信度操作">
        <button type="button" onClick={onOpenConfig}>参数</button>
        <button type="button" onClick={() => onOpenInspector?.("lineage")}>血缘</button>
        <button type="button" onClick={() => onOpenInspector?.("job")}>任务</button>
      </div>
    </aside>
  );
}

function confidenceLabel(status: string, missingCount: number): string {
  if (status === "complete" && missingCount === 0) {
    return "数据完整";
  }
  if (status === "missing" || missingCount > 0) {
    return "存在缺口";
  }
  return "待确认";
}
```

**Step 2: Import component in `ResultDashboard.tsx`**

Add:

```tsx
import { RunConfidencePanel } from "./RunConfidencePanel";
```

Do not render it yet; Task 5 owns layout integration.

**Step 3: Add base styles**

In `apps/web/src/styles.css`, add tokens:

```css
:root {
  --color-risk: #b54708;
  --color-risk-muted: #fff7ed;
  --color-confidence: #155eef;
}
```

Add component styles:

```css
.run-confidence-panel {
  min-width: 0;
  display: grid;
  gap: 12px;
  align-content: start;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 12px;
  background: linear-gradient(180deg, #ffffff 0%, var(--color-surface-data) 100%);
  box-shadow: var(--shadow-panel);
}

.confidence-header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}

.confidence-header span {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 800;
}

.confidence-header strong {
  color: var(--color-text);
  font-size: 14px;
}

.confidence-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
}

.confidence-grid div {
  min-width: 0;
  display: grid;
  gap: 3px;
  border-bottom: 1px solid var(--color-border-subtle);
  padding-bottom: 7px;
}

.confidence-grid dt {
  color: var(--color-text-muted);
  font-size: 11px;
}

.confidence-grid dd {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--color-text);
  font-size: 12px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.risk-text {
  color: var(--color-risk) !important;
}

.confidence-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.confidence-actions button {
  min-height: 30px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 0 10px;
  color: var(--color-text);
  background: #ffffff;
  cursor: pointer;
  font-size: 12px;
  font-weight: 800;
}
```

**Step 4: Run static test**

Run:

```powershell
cd apps\web
npm run test -- --test-name-pattern "market and risk color semantics"
```

Expected:

- PASS for color semantics.
- Structural test may still fail until Task 5.

**Step 5: Commit**

```powershell
git add apps/web/src/features/results/RunConfidencePanel.tsx apps/web/src/features/results/ResultDashboard.tsx apps/web/src/styles.css
git commit -m "feat: add run confidence panel"
```

---

## Task 4: Convert Large KPI Cards into a Compact Metric Strip

**Files:**

- Modify: `apps/web/src/features/results/ResultOverview.tsx`
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/tests/ui-regressions.test.mjs`

**Step 1: Replace `ResultOverview` content**

Replace the current large-card/disclosure implementation with a compact metric strip:

```tsx
import type { BacktestResponse } from "../../api";
import { formatCurrency, formatNumber, formatPercent } from "../../format";

type MetricTone = "positive" | "negative" | "risk" | "neutral";

type MetricItem = {
  label: string;
  value: string;
  tone: MetricTone;
};

export function ResultOverview({ result }: { result: BacktestResponse }) {
  const metrics: MetricItem[] = [
    {
      label: "累计收益",
      value: formatPercent(result.metrics.totalReturn),
      tone: result.metrics.totalReturn >= 0 ? "positive" : "negative"
    },
    {
      label: "最大回撤",
      value: formatPercent(result.metrics.maxDrawdown),
      tone: "risk"
    },
    {
      label: "最终权益",
      value: formatCurrency(result.metrics.finalEquity),
      tone: "neutral"
    },
    {
      label: "夏普比率",
      value: formatNumber(result.metrics.sharpeRatio),
      tone: "neutral"
    },
    {
      label: "交易次数",
      value: formatNumber(result.metrics.tradeCount, 0),
      tone: "neutral"
    },
    {
      label: "胜率",
      value: formatPercent(result.metrics.winRate),
      tone: "neutral"
    }
  ];

  return (
    <section className="compact-metric-strip" aria-label="核心指标">
      {metrics.map((metric) => (
        <div className={`compact-result-metric ${metric.tone}`} key={metric.label}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
        </div>
      ))}
    </section>
  );
}
```

If `formatCurrency` does not exist, use the existing formatter style from the current file or add a small local helper:

```tsx
function formatMoney(value: number): string {
  return value.toLocaleString("zh-CN", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2
  });
}
```

**Step 2: Add compact metric styles**

Add:

```css
.compact-metric-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(110px, 1fr));
  gap: 0;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: #ffffff;
  box-shadow: var(--shadow-panel);
}

.compact-result-metric {
  min-width: 0;
  min-height: 58px;
  display: grid;
  align-content: center;
  gap: 5px;
  padding: 9px 12px;
  border-right: 1px solid var(--color-border-subtle);
}

.compact-result-metric:last-child {
  border-right: 0;
}

.compact-result-metric span {
  color: var(--color-text-muted);
  font-size: 12px;
}

.compact-result-metric strong {
  color: var(--color-text);
  font-size: 18px;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
  overflow-wrap: anywhere;
}

.compact-result-metric.positive strong {
  color: var(--color-market-up);
}

.compact-result-metric.negative strong,
.compact-result-metric.risk strong {
  color: var(--color-risk);
}
```

In the mobile media query:

```css
.compact-metric-strip {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
```

**Step 3: Remove old metric styles only after confirming they are unused**

Search:

```powershell
rg -n "metric-strip|metric-item|metric-detail-disclosure" apps/web/src
```

If only stale selectors remain, remove or leave them if other tests still reference them. Prefer removal if no component uses them.

**Step 4: Run tests**

Run:

```powershell
cd apps\web
npm run test -- --test-name-pattern "result dashboard uses report-first layout"
```

Expected:

- The `compact-metric-strip` portion passes.
- The full test may still fail until Task 5.

**Step 5: Commit**

```powershell
git add apps/web/src/features/results/ResultOverview.tsx apps/web/src/styles.css apps/web/tests/ui-regressions.test.mjs
git commit -m "feat: compact result metric strip"
```

---

## Task 5: Refactor Result Dashboard into Report-First Layout

**Files:**

- Modify: `apps/web/src/features/results/ResultDashboard.tsx`
- Modify: `apps/web/src/styles.css`
- Test: `apps/web/tests/ui-regressions.test.mjs`
- Test: `apps/web/tests/e2e-smoke.test.mjs`

**Step 1: Add `ResultReportNav` inside `ResultDashboard.tsx`**

Add near the bottom of the file:

```tsx
const REPORT_LINKS = [
  { href: "#overview", label: "概览" },
  { href: "#price-signals", label: "价格信号" },
  { href: "#returns-risk", label: "收益风险" },
  { href: "#run-details", label: "运行明细" }
];

function ResultReportNav() {
  return (
    <nav className="result-report-nav" data-testid="result-report-nav" aria-label="结果报告导航">
      {REPORT_LINKS.map((link) => (
        <a href={link.href} key={link.href}>{link.label}</a>
      ))}
    </nav>
  );
}
```

**Step 2: Reorder `ResultDashboard`**

Change the render order to:

```tsx
return (
  <div className="result-dashboard" data-testid="result-dashboard">
    <RunContextBar
      result={result}
      runTimestamp={runTimestamp}
      runStatus={runStatus}
      onOpenConfig={onOpenConfig}
      onOpenInspector={onOpenInspector}
    />
    <ResultReportNav />
    <section id="overview" className="result-overview-block">
      <ResultOverview result={result} />
    </section>
    <div className="result-first-grid">
      <section id="price-signals" className="primary-result-chart">
        <PriceSignalPanel candlestickOption={candlestickOption} volumeOption={volumeOption} />
      </section>
      <RunConfidencePanel
        result={result}
        onOpenConfig={onOpenConfig}
        onOpenInspector={onOpenInspector}
      />
    </div>
    <section id="returns-risk">
      <RiskReturnPanel result={result} equityOption={equityOption} />
    </section>
    <section id="run-details">
      <RunDetailsPanel result={result} />
    </section>
  </div>
);
```

This keeps the primary chart visible and makes the confidence panel first-screen material.

**Step 3: Add layout styles**

Add:

```css
.result-report-nav {
  min-height: 36px;
  display: flex;
  align-items: center;
  gap: 4px;
  overflow-x: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 3px;
  background: #ffffff;
  box-shadow: var(--shadow-panel);
}

.result-report-nav a {
  min-height: 28px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
  padding: 0 10px;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 800;
  text-decoration: none;
  white-space: nowrap;
}

.result-report-nav a:hover,
.result-report-nav a:focus-visible {
  color: var(--color-accent);
  background: var(--color-surface-muted);
}

.result-first-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 320px);
  gap: 12px;
  align-items: start;
}

.primary-result-chart {
  min-width: 0;
}
```

At `max-width: 1180px`:

```css
.result-first-grid {
  grid-template-columns: 1fr;
}
```

**Step 4: Remove or retire stale `dashboard-chart-grid` usage**

Search:

```powershell
rg -n "dashboard-chart-grid" apps/web/src
```

If no component uses it after the refactor, remove stale CSS blocks to avoid confusion. If tests still assert it, update tests to assert `result-first-grid`.

**Step 5: Run tests**

Run:

```powershell
cd apps\web
npm run test
```

Expected:

- Static tests pass, except any browser-only expectations pending Task 8.

**Step 6: Commit**

```powershell
git add apps/web/src/features/results/ResultDashboard.tsx apps/web/src/styles.css apps/web/tests/ui-regressions.test.mjs apps/web/tests/e2e-smoke.test.mjs
git commit -m "feat: refactor result dashboard into report layout"
```

---

## Task 6: Strengthen Run Context Metadata and Wrapping

**Files:**

- Modify: `apps/web/src/features/results/ResultDashboard.tsx`
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/tests/ui-regressions.test.mjs`

**Step 1: Add static regression test**

Add:

```js
test("run context exposes audit metadata without one-line truncation", () => {
  const dashboard = read("src/features/results/ResultDashboard.tsx");
  const styles = read("src/styles.css");

  assert.match(dashboard, /actualProvider/);
  assert.match(dashboard, /engineVersion/);
  assert.match(dashboard, /dataVersion/);
  assert.match(dashboard, /基准/);
  assert.match(styles, /\.run-context-meta-grid/);
  assert.match(styles, /overflow-wrap:\s*anywhere/);
});
```

**Step 2: Update `RunContextBar`**

Inside `RunContextBar`, derive:

```tsx
const actualProvider = result.dataSource.actualProvider ?? result.dataSource.provider;
const engineVersion = result.dataSource.engineVersion ?? "signal-close-v1";
const dataVersion = result.dataSource.dataVersion ?? "unknown";
```

Replace the current flex meta row with:

```tsx
<div className="run-context-meta-grid">
  <span>{result.dataSource.start} 至 {result.dataSource.end}</span>
  <span>基准：未设置</span>
  <span>{actualProvider} · {result.dataSource.adjust || "不复权"}</span>
  <span>引擎：{engineVersion}</span>
  <span>数据：{dataVersion}</span>
  <span title={result.runId ?? "未落库"}>{result.runId ?? "未落库"}</span>
  <span>{runTimestamp}</span>
  <strong>{runStatus}</strong>
</div>
```

**Step 3: Update styles**

Add:

```css
.run-context-meta-grid {
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, auto));
  gap: 4px 10px;
  align-items: center;
  color: var(--color-text-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.run-context-meta-grid span,
.run-context-meta-grid strong {
  min-width: 0;
  overflow-wrap: anywhere;
}

.run-context-meta-grid strong {
  justify-self: start;
  border: 1px solid var(--color-border-subtle);
  border-radius: 999px;
  padding: 2px 7px;
  color: var(--color-text);
  background: var(--color-surface-muted);
  font-size: 11px;
}
```

At `max-width: 1180px`:

```css
.run-context-meta-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
```

At `max-width: 640px`:

```css
.run-context-meta-grid {
  grid-template-columns: 1fr;
}
```

**Step 4: Run tests**

Run:

```powershell
cd apps\web
npm run test -- --test-name-pattern "run context exposes audit metadata"
```

Expected:

- PASS.

**Step 5: Commit**

```powershell
git add apps/web/src/features/results/ResultDashboard.tsx apps/web/src/styles.css apps/web/tests/ui-regressions.test.mjs
git commit -m "feat: expose run audit metadata"
```

---

## Task 7: Add Accurate Run-Setup Action Hierarchy

**Files:**

- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/tests/ui-regressions.test.mjs`

**Step 1: Add static regression test**

Add:

```js
test("run setup uses accurate validation and full-run actions", () => {
  const app = read("src/App.tsx");
  const styles = read("src/styles.css");

  assert.match(app, /onValidateConfig/);
  assert.match(app, /校验配置/);
  assert.match(app, /运行完整回测/);
  assert.doesNotMatch(app, /快速回测/);
  assert.match(styles, /\.run-action-row/);
});
```

**Step 2: Add validation handler in `App`**

Add:

```tsx
function handleValidateConfig() {
  setError(null);
  setNotice(null);
  if (validationError) {
    setError(validationError);
    return;
  }
  if (blockingMessage) {
    setError(blockingMessage);
    return;
  }
  setNotice("配置校验通过，可以运行完整回测。");
}
```

Pass `onValidateConfig={handleValidateConfig}` to `RunSetupPanel`.

**Step 3: Update `RunSetupPanel` props**

Add to the props type:

```tsx
onValidateConfig: () => void;
```

Destructure it in the component.

**Step 4: Replace single run button area**

Replace:

```tsx
<button className="run-button" disabled={!canRun}>
```

with:

```tsx
<div className="run-action-row">
  <button className="secondary-run-button" type="button" onClick={onValidateConfig}>
    校验配置
  </button>
  <button className="run-button" disabled={!canRun}>
    {isRunning
      ? "回测运行中..."
      : strategies.length === 0
        ? "加载策略"
        : !databaseReady
          ? "等待数据库"
          : "运行完整回测"}
  </button>
</div>
```

Do not add "快速回测" in this phase. That avoids a fake RiceQuant/JoinQuant affordance.

**Step 5: Add styles**

Add:

```css
.run-action-row {
  display: grid;
  grid-template-columns: minmax(90px, 0.7fr) minmax(140px, 1.3fr);
  gap: 8px;
}

.secondary-run-button {
  min-height: 40px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  background: #ffffff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 800;
}

.secondary-run-button:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}
```

At `max-width: 640px`:

```css
.run-action-row {
  grid-template-columns: 1fr;
}
```

**Step 6: Run tests**

Run:

```powershell
cd apps\web
npm run test -- --test-name-pattern "run setup uses accurate validation"
```

Expected:

- PASS.

**Step 7: Commit**

```powershell
git add apps/web/src/App.tsx apps/web/src/styles.css apps/web/tests/ui-regressions.test.mjs
git commit -m "feat: clarify run setup actions"
```

---

## Task 8: Update Browser Smoke Layout Checks and Screenshots

**Files:**

- Modify: `apps/web/tests/e2e-smoke.test.mjs`
- Generated: `.codex-artifacts/web-dashboard-smoke.png`
- Generated: `.codex-artifacts/web-dashboard-1600-smoke.png`
- Generated: `.codex-artifacts/web-dashboard-1920-smoke.png`
- Generated: `.codex-artifacts/web-dashboard-mobile-smoke.png`

**Step 1: Update layout selectors**

In `assertResultLayout`, replace `.dashboard-chart-grid` with `.result-first-grid`:

```js
const firstGrid = document.querySelector(".result-first-grid")?.getBoundingClientRect();
```

Return:

```js
firstGridWidth: firstGrid?.width ?? 0,
```

Assert:

```js
assert.ok(layout.firstGridWidth >= Math.min(360, layout.mainWidth - 24), `expected first result grid to render at ${width}px`);
```

Update overflow checks:

```js
[".workspace", ".main-panel", ".result-dashboard", ".run-context-bar", ".result-first-grid"]
```

**Step 2: Run browser smoke**

Run:

```powershell
cd apps\web
npm run smoke:e2e
```

Expected:

- PASS.
- New screenshots are written.

**Step 3: Inspect screenshots**

Open generated screenshots and verify:

- At 1366px, the first viewport shows run context, report nav, compact metrics, primary chart, and confidence panel.
- At 1600px, the confidence panel does not squeeze the K-line chart below readable width.
- At 1920px, the chart remains dominant and the right confidence panel reads as supporting information.
- At 390px, run context wraps without horizontal overflow, and confidence panel appears below the chart.

**Step 4: Commit**

Do not commit generated `.codex-artifacts` unless the repo already tracks them. Commit only test changes:

```powershell
git add apps/web/tests/e2e-smoke.test.mjs
git commit -m "test: update result workspace smoke assertions"
```

---

## Task 9: Full Verification

**Files:**

- Verify all touched files.

**Step 1: Run frontend regression suite**

Run:

```powershell
cd apps\web
npm run test
```

Expected:

- All node tests pass.

**Step 2: Run build**

Run:

```powershell
cd apps\web
npm run build
```

Expected:

- TypeScript check and Vite build pass.

**Step 3: Run browser smoke**

Run:

```powershell
cd apps\web
npm run smoke:e2e
```

Expected:

- Playwright smoke test passes.
- Screenshots are regenerated.

**Step 4: Optional full Python verification**

Only run this if backend files were touched or if the implementation changed API assumptions:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected:

- Python test suite passes.

**Step 5: Inspect git diff**

Run:

```powershell
git status --short
git diff --stat
```

Expected:

- Only planned files are modified.
- Existing unrelated files, such as `design.md/`, remain untouched.

---

## Final Acceptance Criteria

- Result mode first viewport is report-first: run context, report nav, compact metrics, primary chart, and `RunConfidencePanel`.
- Empty "指标明细" placeholder is gone.
- Data confidence is visible without opening a drawer.
- Run context exposes actual provider, data version, engine version, run id, range, and benchmark placeholder.
- Risk color is not tied to market green.
- Run setup offers accurate actions only: configuration validation and full backtest.
- Existing result detail capabilities remain available: chart data table, trades filter/paging/export, lineage panel, and logs.
- Desktop viewports at 1366, 1600, and 1920 have no horizontal overflow.
- Mobile viewport has no horizontal overflow and wraps long run metadata.
- `npm run test`, `npm run build`, and `npm run smoke:e2e` pass after implementation.

## Out of Scope

- True fast backtest or compile-run backend.
- Notebook editor.
- Factor shopping-cart strategy builder.
- Simulation trading state machine.
- Benchmark data API and alpha/beta calculations.
- Multi-symbol portfolio accounting.

## Execution Options

Plan complete and saved to `docs/plans/2026-05-26-lh-quant-ui-optimization-plan.md`. Two execution options:

1. **Subagent-Driven (this session)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Parallel Session (separate)** - Open a new session with `executing-plans`, batch execution with checkpoints.

Recommended: Subagent-Driven for Tasks 1-8 because the work is visually coupled and benefits from frequent screenshot review.
