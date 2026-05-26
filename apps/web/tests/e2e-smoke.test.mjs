import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { chromium } from "playwright";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const port = 5197;
const baseUrl = `http://127.0.0.1:${port}`;

test("dashboard renders with mocked API data in a real browser", { timeout: 90000 }, async () => {
  const server = startViteServer();
  let browser;
  try {
    await waitForServer(`${baseUrl}/`);
    browser = await chromium.launch({ headless: true, executablePath: chromium.executablePath() });
    const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
    await mockApi(page);

    await page.goto(baseUrl);
    await page.locator('[data-testid="global-product-nav"]').waitFor({ state: "visible" });
    await page.locator('[data-testid="ide-resource-sidebar"]').waitFor({ state: "visible" });
    await page.locator('[data-testid="ide-run-setup"]').waitFor({ state: "visible" });
    await page.locator('[data-testid="research-workbench"]').waitFor({ state: "visible" });
    await page.locator('[data-testid="queue-simulation-panel"]').waitFor({ state: "visible" });
    await page.locator('[data-testid="run-output-panel"]').waitFor({ state: "visible" });
    assert.equal(await page.locator('[data-testid="pre-run-preview"]').count(), 0);
    assert.equal(await page.locator('[data-testid="platform-overview"]').count(), 0);
    await page.locator(".run-button").waitFor({ state: "visible" });
    await page.locator(".run-button").click();
    await page.locator('[data-testid="job-status-panel"]').waitFor({ state: "visible" });
    await page.locator('[data-testid="result-dashboard"]').waitFor({ state: "visible" });

    await page.locator('[data-testid="trade-filter"]').waitFor({ state: "visible" });
    await page.locator('[data-testid="chart-data-toggle"]').click();
    await page.locator('[data-testid="chart-data-table"]').waitFor({ state: "visible" });

    await page.waitForFunction(() => document.querySelectorAll(".chart canvas").length > 0, undefined, { timeout: 15000 });
    const chartCanvasCount = await page.locator(".chart canvas").count();
    assert.ok(chartCanvasCount > 0, "expected ECharts to render at least one canvas");
    await assertResultLayout(page, 1366);
    const overflowingContainers = await page.evaluate(() =>
      [".workspace", ".main-panel", ".result-dashboard", ".run-context-bar", ".dashboard-chart-grid"]
        .flatMap((selector) => {
          const element = document.querySelector(selector);
          if (!element) {
            return [];
          }
          const overflow = element.scrollWidth - element.clientWidth;
          return overflow > 1 ? [`${selector}:${overflow}`] : [];
        })
    );
    assert.deepEqual(overflowingContainers, [], "expected primary workspace containers not to overflow horizontally");

    const outputDir = join(root, "..", "..", ".codex-artifacts");
    mkdirSync(outputDir, { recursive: true });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: join(outputDir, "web-dashboard-smoke.png") });

    await page.locator(".run-context-actions button").nth(1).click();
    await page.locator(".right-inspector.open").waitFor({ state: "visible" });
    await assertDrawerVisible(page, ".right-inspector.open");
    await page.locator(".right-inspector .drawer-close").click();
    await page.locator(".run-context-actions button").first().click();
    await page.locator(".config-drawer.open").waitFor({ state: "visible" });
    await assertDrawerVisible(page, ".config-drawer.open");
    await page.locator(".config-drawer .drawer-close").click();

    await page.setViewportSize({ width: 1600, height: 1000 });
    await page.waitForTimeout(250);
    await assertResultLayout(page, 1600);
    await page.screenshot({ path: join(outputDir, "web-dashboard-1600-smoke.png") });

    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.waitForTimeout(250);
    await assertResultLayout(page, 1920);
    await page.screenshot({ path: join(outputDir, "web-dashboard-1920-smoke.png") });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(250);
    const mobileOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    assert.ok(mobileOverflow <= 1, `expected no mobile horizontal overflow, got ${mobileOverflow}px`);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: join(outputDir, "web-dashboard-mobile-smoke.png") });
  } finally {
    if (browser) {
      await browser.close();
    }
    await stopViteServer(server);
  }
});

async function assertResultLayout(page, width) {
  const layout = await page.evaluate(() => {
    const main = document.querySelector(".main-panel")?.getBoundingClientRect();
    const inspectorElement = document.querySelector(".right-inspector");
    const inspector = inspectorElement?.getBoundingClientRect();
    const chart = document.querySelector(".chart-large")?.getBoundingClientRect();
    const contextBar = document.querySelector(".run-context-bar")?.getBoundingClientRect();
    const inspectorStyle = inspectorElement ? window.getComputedStyle(inspectorElement) : null;
    return {
      chartHeight: chart?.height ?? 0,
      contextTop: contextBar?.top ?? 0,
      horizontalOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      inspectorDisplay: inspectorStyle?.display ?? "missing",
      inspectorLeft: inspector?.left ?? 0,
      mainWidth: main?.width ?? 0,
      viewportWidth: window.innerWidth
    };
  });

  assert.ok(layout.horizontalOverflow <= 1, `expected no horizontal page overflow at ${width}px, got ${layout.horizontalOverflow}px`);
  assert.ok(layout.contextTop < 130, `expected run context near the first viewport at ${width}px, got top ${layout.contextTop}px`);
  assert.ok(layout.chartHeight >= 430, `expected readable primary chart at ${width}px, got ${layout.chartHeight}px`);
  if (width < 1920) {
    assert.ok(layout.mainWidth >= layout.viewportWidth - 90, `expected result main panel to use available width at ${width}px, got ${layout.mainWidth}px`);
    assert.equal(layout.inspectorDisplay, "none", `expected result inspector to be closed at ${width}px`);
  }
}

async function assertDrawerVisible(page, selector) {
  const rect = await page.locator(selector).evaluate((element) => {
    const box = element.getBoundingClientRect();
    return { left: box.left, right: box.right, viewportWidth: window.innerWidth, width: box.width };
  });

  assert.ok(rect.width > 250, `expected drawer ${selector} to have useful width, got ${rect.width}px`);
  assert.ok(rect.left < rect.viewportWidth && rect.right > 0, `expected drawer ${selector} in viewport, got ${JSON.stringify(rect)}`);
}

function startViteServer() {
  const command = `npm run dev -- --host 127.0.0.1 --port ${port} --strictPort`;
  return spawn(command, {
    cwd: root,
    env: { ...process.env },
    shell: true,
    stdio: "ignore"
  });
}

async function stopViteServer(server) {
  server.kill();
  if (process.platform !== "win32") {
    return;
  }
  const command = [
    "powershell",
    "-NoProfile",
    "-Command",
    `"Get-NetTCPConnection -LocalPort ${port} -ErrorAction SilentlyContinue | Select-Object -First 1 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"`
  ].join(" ");
  await runShell(command);
}

function runShell(command) {
  return new Promise((resolve) => {
    const child = spawn(command, { shell: true, stdio: "ignore" });
    child.on("exit", resolve);
    child.on("error", resolve);
  });
}

async function waitForServer(url) {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function mockApi(page) {
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/health") {
      await route.fulfill({ json: healthPayload() });
      return;
    }
    if (url.pathname === "/api/strategies") {
      await route.fulfill({ json: strategiesPayload() });
      return;
    }
    if (url.pathname === "/api/platform/capabilities") {
      await route.fulfill({ json: platformPayload() });
      return;
    }
    if (url.pathname === "/api/data/catalog") {
      await route.fulfill({ json: dataCatalogPayload() });
      return;
    }
    if (url.pathname === "/api/data/assets") {
      await route.fulfill({ json: dataAssetsPayload() });
      return;
    }
    if (url.pathname === "/api/factors") {
      await route.fulfill({ json: factorsPayload() });
      return;
    }
    if (url.pathname === "/api/backtests/runs") {
      await route.fulfill({ json: { database: healthPayload().database, runs: [] } });
      return;
    }
    if (url.pathname === "/api/backtests/jobs") {
      const result = backtestPayload();
      await route.fulfill({ json: { job: jobPayload(result), result } });
      return;
    }
    if (url.pathname === "/api/backtests/run") {
      await route.fulfill({ json: backtestPayload() });
      return;
    }
    await route.abort();
  });
}

function dataAssetsPayload() {
  return {
    database: healthPayload().database,
    assets: [
      {
        id: "a_share_daily_bars",
        name: "A-share daily bars",
        provider: "AKShare",
        status: "available",
        coverage: "2024-01-01 to 2024-01-24",
        lastSync: "2024-01-24 10:00:00",
        quality: { status: "unknown", score: null, message: "Calendar not synced" },
        rowCount: 24,
        fields: ["open", "high", "low", "close", "volume"]
      }
    ]
  };
}

function factorsPayload() {
  return {
    factors: [
      {
        id: "return_20d",
        name: "20 day return",
        category: "return",
        frequency: "1d",
        direction: "positive",
        description: "Trailing return",
        source: "local",
        license: "internal",
        formula: "close / close.shift(20) - 1",
        status: "available"
      }
    ]
  };
}

function healthPayload() {
  return {
    status: "ok",
    name: "LH Quant",
    dataSource: "AKShare",
    database: { connected: true, url: "hidden", message: "ok" }
  };
}

function platformPayload() {
  return {
    apiVersion: "v1",
    modules: [
      { id: "data", name: "数据服务", status: "available", description: "日线行情与缓存血缘", features: ["行情", "缓存", "血缘"] },
      { id: "research", name: "研究环境", status: "preview", description: "策略模板与参数约束", features: ["模板", "校验", "指标"] },
      { id: "backtest", name: "回测分析", status: "available", description: "任务化回测与结果恢复", features: ["任务", "详情"] },
      { id: "simulation", name: "模拟交易", status: "planned", description: "组合持仓与订单队列", features: ["组合", "订单", "监控"] }
    ]
  };
}

function dataCatalogPayload() {
  return {
    database: healthPayload().database,
    datasets: [
      {
        id: "a_share_daily_bars",
        name: "A股日线行情",
        status: "available",
        provider: "AKShare",
        frequency: "1d",
        coverage: "请求区间已缓存入库",
        fields: ["open", "high", "low", "close", "volume"]
      },
      {
        id: "fundamentals",
        name: "财务与估值",
        status: "planned",
        provider: "待接入",
        frequency: "quarterly",
        coverage: "财报与估值字段",
        fields: ["revenue", "net_profit", "pe_ratio", "market_cap"]
      }
    ]
  };
}

function jobPayload(result) {
  return {
    runId: result.runId,
    status: "succeeded",
    progress: 1,
    engine: "sync-local",
    submittedAt: "2024-01-24T10:00:00Z",
    completedAt: "2024-01-24T10:00:01Z",
    symbol: result.symbol,
    strategyName: result.strategy.name,
    message: "回测任务已完成"
  };
}

function strategiesPayload() {
  return {
    strategies: [
      {
        id: "moving_average",
        name: "双均线策略",
        description: "趋势跟随",
        category: "趋势",
        params: [
          { key: "fastWindow", label: "快线", valueType: "int", default: 5, min: 2, max: 60, step: 1, unit: "d", helpText: "短周期均线" },
          { key: "slowWindow", label: "慢线", valueType: "int", default: 20, min: 3, max: 120, step: 1, unit: "d", helpText: "长周期均线" }
        ],
        constraints: [{ type: "lt", left: "fastWindow", right: "slowWindow", message: "Fast must be below slow" }]
      }
    ]
  };
}

function backtestPayload() {
  const bars = Array.from({ length: 24 }, (_, index) => {
    const day = String(index + 1).padStart(2, "0");
    const open = 10 + index * 0.12;
    const close = open + (index % 4 === 0 ? -0.08 : 0.16);
    return {
      datetime: `2024-01-${day}`,
      open,
      high: Math.max(open, close) + 0.22,
      low: Math.min(open, close) - 0.18,
      close,
      volume: 800000 + index * 17000
    };
  });
  const equityCurve = bars.map((bar, index) => ({
    datetime: bar.datetime,
    cash: 100000 - index * 450,
    position: index > 2 ? 800 : 0,
    price: bar.close,
    equity: 100000 + index * 520,
    drawdown: index % 7 === 0 ? -0.01 : 0
  }));
  return {
    runId: "bt_smoke",
    symbol: "000001",
    strategy: {
      id: "moving_average",
      name: "双均线策略",
      params: {
        symbol: "000001",
        start: "2024-01-01",
        end: "2024-01-24",
        strategyId: "moving_average",
        strategyParams: { fastWindow: 5, slowWindow: 20 },
        cash: 100000,
        commissionRate: 0.001,
        adjust: "qfq",
        dataProvider: "auto"
      }
    },
    dataSource: {
      provider: "AKShare",
      requestedProvider: "auto",
      actualProvider: "AKShare",
      frequency: "1d",
      adjust: "qfq",
      start: "2024-01-01",
      end: "2024-01-24",
      cached: false,
      fallbackChain: []
    },
    database: healthPayload().database,
    metrics: {
      startingCash: 100000,
      finalEquity: 112480,
      totalReturn: 0.1248,
      annualizedReturn: 0.61,
      annualizedVolatility: 0.18,
      sharpeRatio: 2.1,
      sortinoRatio: 2.7,
      calmarRatio: 4.4,
      maxDrawdown: -0.032,
      tradeCount: 16,
      closedTradeCount: 8,
      winRate: 0.62,
      profitFactor: 1.9,
      expectancy: 320,
      averageWin: 680,
      averageLoss: -210,
      totalCommission: 138,
      exposure: 0.76,
      averagePositionWeight: 0.52,
      maxPositionWeight: 0.88,
      turnover: 1.34,
      barCount: bars.length,
      signalCount: 4
    },
    bars,
    indicatorLines: [
      { name: "快线", color: "#1F6FEB", points: bars.map((bar) => ({ datetime: bar.datetime, value: bar.close - 0.12 })) },
      { name: "慢线", color: "#8A5CF6", points: bars.map((bar) => ({ datetime: bar.datetime, value: bar.close - 0.28 })) }
    ],
    movingAverages: bars.map((bar) => ({ datetime: bar.datetime, fast: bar.close - 0.12, slow: bar.close - 0.28 })),
    signals: [
      { datetime: "2024-01-04", signal: 1, label: "Buy", price: bars[3].close },
      { datetime: "2024-01-13", signal: -1, label: "Sell", price: bars[12].close }
    ],
    equityCurve,
    trades: Array.from({ length: 16 }, (_, index) => {
      const bar = bars[index + 3];
      const side = index % 2 === 0 ? "buy" : "sell";
      return {
        datetime: bar.datetime,
        side,
        sideText: side === "buy" ? "Buy" : "Sell",
        price: bar.close,
        quantity: 100 + index,
        amount: bar.close * (100 + index),
        commission: 1.2 + index * 0.1
      };
    }),
    logs: ["Loaded mocked smoke data", "Saved run"]
  };
}
