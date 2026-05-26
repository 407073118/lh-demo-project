import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { test } from "node:test";

const root = dirname(dirname(fileURLToPath(import.meta.url)));

function read(relativePath) {
  return readFileSync(join(root, relativePath), "utf8");
}

test("results use a dashboard-first layout instead of hiding core analysis behind top-level tabs", () => {
  const app = read("src/App.tsx");

  assert.match(app, /ResultDashboard/);
  assert.doesNotMatch(app, /ResultTabs/);
});

test("persisted run details restore full chart-ready result state", () => {
  const app = read("src/App.tsx");
  const api = read("src/api.ts");

  assert.match(app, /buildResultFromPersistedDetail/);
  assert.match(app, /const restoredResult = buildResultFromPersistedDetail\(detail\)/);
  assert.match(app, /setResult\(restoredResult\)/);
  assert.match(app, /bars:\s*detail\.bars/);
  assert.match(app, /indicatorLines:\s*detail\.indicatorLines/);
  assert.match(app, /movingAverages:\s*detail\.movingAverages/);
  assert.match(api, /bars:\s*BarRecord\[\]/);
  assert.match(api, /indicatorLines:\s*IndicatorLine\[\]/);
  assert.match(api, /movingAverages:\s*MovingAverageRecord\[\]/);
});

test("recent run history is de-duplicated before rendering", () => {
  const app = read("src/App.tsx");

  assert.match(app, /function dedupeRecentRuns\(runs:\s*RunSummary\[\]\):\s*RunSummary\[\]/);
  assert.match(app, /const visibleRecentRuns = useMemo\(\(\) => dedupeRecentRuns\(recentRuns\), \[recentRuns\]\)/);
  assert.match(app, /runs=\{visibleRecentRuns\}/);
});

test("design styles expose tokens, keyboard focus, and mobile touch target rules", () => {
  const styles = read("src/styles.css");

  assert.match(styles, /--color-market-up/);
  assert.match(styles, /--color-market-down/);
  assert.match(styles, /:focus-visible/);
  assert.match(styles, /@media \(pointer: coarse\)/);
  assert.match(styles, /min-height:\s*44px/);
});

test("frontend has a documented institutional quant console design system", () => {
  const design = read("DESIGN.md");
  const styles = read("src/styles.css");

  assert.match(design, /name:\s*Institutional Quant Console/);
  assert.match(design, /--color-platform-nav/);
  assert.match(design, /high-density research IDE/i);
  assert.match(styles, /--color-gridline/);
  assert.match(styles, /--color-buy/);
  assert.match(styles, /--color-sell/);
  assert.match(styles, /--shadow-panel/);
  assert.match(styles, /--font-mono/);
  assert.match(styles, /\.workspace::before/);
});

test("charts are accessible and lazy-load the charting library", () => {
  const chart = read("src/EChart.tsx");

  assert.match(chart, /ariaLabel/);
  assert.match(chart, /role="img"/);
  assert.match(chart, /await import\("echarts\/core"\)/);
  assert.doesNotMatch(chart, /^import \* as echarts from "echarts\/core";/m);
});

test("large trade lists have filter, paging, and csv export controls", () => {
  const panel = read("src/features/results/OrdersTradesPanel.tsx");

  assert.match(panel, /const PAGE_SIZE/);
  assert.match(panel, /tradeFilter/);
  assert.match(panel, /visibleTrades\.map/);
  assert.match(panel, /exportTradesToCsv/);
  assert.doesNotMatch(panel, /result\.trades\.map/);
});

test("chart source data is available as a table fallback", () => {
  const dashboard = read("src/features/results/ResultDashboard.tsx");

  assert.match(dashboard, /ChartDataPanel/);
  assert.match(dashboard, /chartData/);
  assert.match(dashboard, /data-testid="chart-data-toggle"/);
  assert.match(dashboard, /data-testid="chart-data-table"/);
});

test("result panels use shared UI primitives for consistent structure", () => {
  const primitives = read("src/features/results/uiPrimitives.tsx");
  const orders = read("src/features/results/OrdersTradesPanel.tsx");
  const dashboard = read("src/features/results/ResultDashboard.tsx");

  assert.match(primitives, /export function Panel/);
  assert.match(primitives, /export function PanelTitle/);
  assert.match(orders, /from "\.\/uiPrimitives"/);
  assert.match(dashboard, /from "\.\/uiPrimitives"/);
});

test("a real browser smoke test is wired into the web package", () => {
  const packageJson = read("package.json");
  const smoke = read("tests/e2e-smoke.test.mjs");

  assert.match(packageJson, /"smoke:e2e":\s*"node --test tests\/e2e-smoke\.test\.mjs"/);
  assert.match(smoke, /from "playwright"/);
  assert.match(smoke, /data-testid="result-dashboard"/);
});

test("platform shell exposes JoinQuant-style data, research, backtest, and simulation modules", () => {
  const app = read("src/App.tsx");
  const api = read("src/api.ts");
  const styles = read("src/styles.css");

  assert.match(api, /fetchPlatformCapabilities/);
  assert.match(api, /fetchDataCatalog/);
  assert.match(api, /runBacktestJob/);
  assert.match(app, /PlatformOverview/);
  assert.match(app, /JobStatusPanel/);
  assert.match(app, /DataCatalogPanel/);
  assert.match(app, /data-testid="platform-overview"/);
  assert.match(app, /data-testid="job-status-panel"/);
  assert.match(styles, /\.platform-nav/);
});

test("platform console has a quant IDE navigation, resource tree, editor, and run panel", () => {
  const app = read("src/App.tsx");
  const styles = read("src/styles.css");

  assert.match(app, /PlatformHeader/);
  assert.match(app, /QuantIdeResourceSidebar/);
  assert.match(app, /RunSetupPanel/);
  assert.match(app, /RunOutputPanel/);
  assert.match(app, /ResearchWorkbench/);
  assert.match(app, /QueueSimulationPanel/);
  assert.match(app, /data-testid="global-product-nav"/);
  assert.match(app, /data-testid="ide-resource-sidebar"/);
  assert.match(app, /data-testid="ide-run-setup"/);
  assert.match(app, /data-testid="run-output-panel"/);
  assert.match(app, /data-testid="research-workbench"/);
  assert.match(app, /data-testid="queue-simulation-panel"/);
  assert.match(styles, /\.workspace-shell/);
  assert.match(styles, /\.global-product-nav/);
  assert.match(styles, /\.quant-ide/);
  assert.match(styles, /\.ide-resource-sidebar/);
  assert.match(styles, /\.ide-parameter-panel/);
  assert.match(styles, /\.research-terminal/);
  assert.match(styles, /\.simulation-ledger/);
  assert.doesNotMatch(app, /<LifecycleRail/);
});

test("data assets and strategy library workspaces are wired to real APIs", () => {
  const app = read("src/App.tsx");
  const api = read("src/api.ts");
  const dataPage = read("src/features/data/DataAssetsPage.tsx");
  const strategyPage = read("src/features/strategies/StrategyLibraryPage.tsx");

  assert.match(api, /fetchDataAssets/);
  assert.match(api, /fetchFactors/);
  assert.match(app, /DataAssetsPage/);
  assert.match(app, /StrategyLibraryPage/);
  assert.match(dataPage, /data-testid="data-assets-page"/);
  assert.match(dataPage, /配置数据库/);
  assert.match(dataPage, /使用示例数据/);
  assert.match(dataPage, /重试连接/);
  assert.match(strategyPage, /data-testid="strategy-library-page"/);
  assert.match(strategyPage, /搜索策略/);
});

test("platform console prioritizes analysis density over marketing cards", () => {
  const app = read("src/App.tsx");
  const styles = read("src/styles.css");

  assert.match(app, /data-testid="platform-status-strip"/);
  assert.doesNotMatch(app, /platform-module-card/);
  assert.match(styles, /\.platform-status-strip/);
  assert.match(styles, /\.capability-pill/);
  assert.match(styles, /grid-template-columns:\s*240px minmax\(0,\s*1fr\) 320px/);
  assert.doesNotMatch(styles, /\.platform-module-card/);
});

test("backtest workspace has an explicit result-focused mode with drawers", () => {
  const app = read("src/App.tsx");
  const styles = read("src/styles.css");

  assert.match(app, /type WorkspaceMode = "editing" \| "running" \| "result"/);
  assert.match(app, /const workspaceMode: WorkspaceMode/);
  assert.match(app, /configDrawerOpen/);
  assert.match(app, /inspectorDrawer/);
  assert.match(styles, /\.workspace\.workspace-result/);
  assert.match(styles, /grid-template-columns:\s*minmax\(0,\s*1fr\)/);
  assert.match(styles, /\.config-drawer/);
  assert.match(styles, /\.inspector-drawer/);
  assert.match(styles, /@media \(min-width:\s*1920px\)/);
  assert.doesNotMatch(styles, /\.workspace\.workspace-result\s*\{[\s\S]*280px minmax\(0,\s*1fr\) 260px/);
});

test("result dashboard exposes a compact run context before charts", () => {
  const dashboard = read("src/features/results/ResultDashboard.tsx");
  const overview = read("src/features/results/ResultOverview.tsx");

  assert.match(dashboard, /RunContextBar/);
  assert.match(dashboard, /className="run-context-bar"/);
  assert.match(dashboard, /onOpenConfig/);
  assert.match(dashboard, /onOpenInspector/);
  assert.match(overview, /metric-detail-disclosure/);
  assert.match(overview, /<summary/);
});

test("design contract defines result-mode layout guardrails", () => {
  const design = read("DESIGN.md");

  assert.match(design, /result-focused/i);
  assert.match(design, /Config Drawer/);
  assert.match(design, /Inspector Drawer/);
  assert.match(design, /chart-panel/);
  assert.match(design, /1180px-1919px/);
  assert.match(design, /1920px/);
});

test("editing workspace keeps dense columns while result mode prioritizes results", () => {
  const app = read("src/App.tsx");
  const styles = read("src/styles.css");

  assert.match(styles, /grid-template-columns:\s*240px minmax\(0,\s*1fr\) 320px/);
  assert.match(styles, /\.main-panel\s*\{[\s\S]*overflow-x:\s*hidden/);
  assert.match(styles, /\.panel\s*\{[\s\S]*overflow:\s*hidden/);
  assert.doesNotMatch(styles, /grid-template-columns:\s*292px minmax\(680px,\s*1fr\) 276px/);
  assert.doesNotMatch(styles, /\.dashboard-chart-grid\s*\{[\s\S]*minmax\(360px/);
  assert.match(app, /result \? \(\s*<>\s*<ResultDashboard/);
  assert.match(app, /: \(\s*<>\s*<ResearchWorkbench/);
});

test("editing workspace uses IDE output tabs instead of a fake pre-run chart preview", () => {
  const app = read("src/App.tsx");
  const styles = read("src/styles.css");

  assert.match(app, /RunOutputPanel/);
  assert.match(app, /data-testid="run-output-panel"/);
  assert.match(styles, /\.run-output-panel/);
  assert.match(styles, /\.output-tab-strip/);
  assert.match(styles, /\.output-empty-state/);
  assert.doesNotMatch(app, /PreRunAnalysisPreview/);
  assert.doesNotMatch(app, /data-testid="pre-run-preview"/);
  assert.doesNotMatch(app, /<div className="empty-state">/);
});

test("quant IDE chrome is visually aligned and prioritizes the editor on narrow screens", () => {
  const app = read("src/App.tsx");
  const styles = read("src/styles.css");

  assert.match(app, /运行设置/);
  assert.match(app, /控制台/);
  assert.match(app, /回测队列/);
  assert.match(styles, /\.ide-file-list span\s*\{[\s\S]*font-size:\s*13px/);
  assert.match(styles, /@media \(max-width: 1180px\)[\s\S]*grid-template-areas:\s*"main"\s*"inspector"\s*"sidebar"/);
});

test("backtest workspace does not show the platform overview strip", () => {
  const app = read("src/App.tsx");

  assert.match(app, /const showPlatformOverview = activeView === "data" \|\| activeView === "strategies"/);
  assert.doesNotMatch(app, /isResultWorkspace \? null : <PlatformOverview/);
});

test("backtest requests expose an explicit market data provider selector", () => {
  const app = read("src/App.tsx");
  const api = read("src/api.ts");
  const config = read("src/features/config/WorkbenchConfigSections.tsx");
  const lineage = read("src/features/results/DataLineagePanel.tsx");

  assert.match(api, /export type DataProviderId = "auto" \| "tushare" \| "akshare" \| "yahoo"/);
  assert.match(app, /dataProvider:\s*"auto"/);
  assert.match(config, /数据来源/);
  assert.match(config, /<option value="auto">自动<\/option>/);
  assert.match(config, /<option value="tushare">Tushare<\/option>/);
  assert.match(lineage, /请求来源/);
  assert.match(lineage, /实际来源/);
  assert.match(lineage, /formatFallbackChain/);
});

test("desktop dashboard keeps primary metrics scannable in one row", () => {
  const styles = read("src/styles.css");

  assert.match(styles, /\.metric-strip\s*\{[\s\S]*grid-template-columns:\s*repeat\(5,\s*minmax\(118px,\s*1fr\)\)/);
  assert.match(styles, /@media \(max-width: 640px\)[\s\S]*\.metric-strip\s*\{[\s\S]*grid-template-columns:\s*1fr/);
});

test("cards avoid colored left-rail accents", () => {
  const styles = read("src/styles.css");
  const cardSelectors = [
    "platform-nav-label",
    "capability-pill",
    "strategy-summary",
    "dataset-item",
    "ledger-grid",
    "metric-item",
    "panel",
    "strategy-library-item",
    "asset-detail-panel",
    "database-empty-state"
  ];

  assert.doesNotMatch(styles, /\.platform-nav-label\s*\{[^}]*border-left:/);
  assert.doesNotMatch(styles, /\.capability-pill\s*\{[^}]*border-left-width:/);
  assert.doesNotMatch(styles, /\.capability-pill\.(available|preview|planned)\s*\{[^}]*border-left-color:/);
  assert.doesNotMatch(styles, /\.metric-item(?:\.[\w-]+)?\s*\{[^}]*box-shadow:\s*inset\s+3px\s+0/);
  for (const selector of cardSelectors) {
    assert.doesNotMatch(styles, new RegExp(`\\.${selector}(?:[\\w .:-]+)?\\s*\\{[^}]*border-left\\s*:`));
  }
  assert.doesNotMatch(styles, /box-shadow:\s*inset\s+\d+px\s+0/);
});

test("module status surfaces use neutral hierarchy instead of semantic color blocks", () => {
  const styles = read("src/styles.css");

  assert.doesNotMatch(styles, /\.capability-pill\.(available|preview|planned)\s+em\s*\{/);
  assert.doesNotMatch(styles, /\.module-status\.(available|preview|planned)\s*\{[^}]*var\(--color-(success|info)/);
  assert.doesNotMatch(styles, /\.status-badge\.(online|checking|offline)\s*\{[^}]*var\(--color-(success|info|danger)/);
  assert.doesNotMatch(styles, /\.lifecycle-item\.(active|done)\s*\{[^}]*rgba\((78|67|2),/);
  assert.match(styles, /\.capability-pill em\s*\{[\s\S]*color:\s*var\(--color-text-muted\)/);
  assert.match(styles, /\.module-status\s*\{[\s\S]*color:\s*var\(--color-text-muted\)/);
});

test("configuration headings avoid decorative leading color bars", () => {
  const styles = read("src/styles.css");

  assert.doesNotMatch(styles, /\.form-section h2::before/);
});

test("ci runs frontend regression and browser smoke checks", () => {
  const ci = read("../../.github/workflows/ci.yml");

  assert.match(ci, /npm run test/);
  assert.match(ci, /npm run smoke:e2e/);
});
