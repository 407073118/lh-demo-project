import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import type { EChartsCoreOption } from "echarts/core";
import type {
  BacktestJob,
  BacktestRequest,
  BacktestResponse,
  DataAsset,
  DataAssetDetailResponse,
  DataCatalogResponse,
  DatabaseStatus,
  FactorDefinition,
  PersistedRunDetail,
  PlatformCapabilitiesResponse,
  RunSummary,
  StrategyDefinition,
  StrategyParamDefinition,
  StrategyParams
} from "./api";
import {
  fetchDataAssetDetail,
  fetchDataAssets,
  fetchDataCatalog,
  fetchFactors,
  fetchHealth,
  fetchPlatformCapabilities,
  fetchRecentRuns,
  fetchRunDetail,
  fetchStrategies,
  runBacktestJob
} from "./api";
import { DataAssetsPage } from "./features/data/DataAssetsPage";
import {
  RiskExecutionSection,
  StrategyConfigSection,
  UniverseDataSection
} from "./features/config/WorkbenchConfigSections";
import { ResultDashboard } from "./features/results/ResultDashboard";
import { StrategyLibraryPage } from "./features/strategies/StrategyLibraryPage";
import { formatPercent } from "./format";
import { evaluateStrategyConstraints } from "./strategyConstraints";

const today = new Date().toISOString().slice(0, 10);
const defaultStrategyId = "moving_average";
const defaultStrategyParams: StrategyParams = {
  fastWindow: 5,
  slowWindow: 20
};

const CHART_COLORS = {
  axis: "#8A95A6",
  splitLine: "#E6EDF5",
  equity: "#1F6FEB",
  marketUp: "#C92A1F",
  marketDown: "#027A48"
};

const initialRequest: BacktestRequest = {
  symbol: "000001",
  start: "2024-01-01",
  end: today,
  strategyId: defaultStrategyId,
  strategyParams: defaultStrategyParams,
  cash: 100000,
  commissionRate: 0.001,
  adjust: "qfq"
};

type ConnectionState = "checking" | "online" | "offline";
type WorkspaceView = "data" | "research" | "backtest" | "strategies" | "history";

export default function App() {
  const [connectionState, setConnectionState] = useState<ConnectionState>("checking");
  const [strategies, setStrategies] = useState<StrategyDefinition[]>([]);
  const [activeView, setActiveView] = useState<WorkspaceView>("backtest");
  const [form, setForm] = useState<BacktestRequest>(initialRequest);
  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [databaseStatus, setDatabaseStatus] = useState<DatabaseStatus | null>(null);
  const [platformCapabilities, setPlatformCapabilities] = useState<PlatformCapabilitiesResponse | null>(null);
  const [dataCatalog, setDataCatalog] = useState<DataCatalogResponse | null>(null);
  const [dataAssets, setDataAssets] = useState<DataAsset[]>([]);
  const [selectedDataAsset, setSelectedDataAsset] = useState<DataAssetDetailResponse["asset"] | null>(null);
  const [factors, setFactors] = useState<FactorDefinition[]>([]);
  const [currentJob, setCurrentJob] = useState<BacktestJob | null>(null);
  const [recentRuns, setRecentRuns] = useState<RunSummary[]>([]);
  const [recentRunsError, setRecentRunsError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [isLoadingRunDetail, setIsLoadingRunDetail] = useState(false);
  const [lastRunAt, setLastRunAt] = useState<string>("尚未运行");

  const selectedStrategy = useMemo(
    () => strategies.find((strategy) => strategy.id === form.strategyId) ?? null,
    [form.strategyId, strategies]
  );
  const hasDirtyParams = result ? JSON.stringify(form) !== JSON.stringify(result.strategy.params) : false;
  const databaseReady = databaseStatus?.connected === true;
  const visibleRecentRuns = useMemo(() => dedupeRecentRuns(recentRuns), [recentRuns]);

  useEffect(() => {
    async function loadInitialState() {
      try {
        const [health, strategyPayload, capabilities, catalog, assets, factorPayload] = await Promise.all([
          fetchHealth(),
          fetchStrategies(),
          fetchPlatformCapabilities(),
          fetchDataCatalog(),
          fetchDataAssets(),
          fetchFactors()
        ]);
        setConnectionState(health.status === "ok" ? "online" : "offline");
        setDatabaseStatus(health.database);
        setStrategies(strategyPayload.strategies);
        setPlatformCapabilities(capabilities);
        setDataCatalog(catalog);
        setDataAssets(assets.assets);
        setFactors(factorPayload.factors);
        setSelectedDataAsset(assets.assets[0] ? { ...assets.assets[0], description: "", syncJobs: [] } : null);
        await refreshRecentRuns();
      } catch {
        setConnectionState("offline");
        setDatabaseStatus(null);
      }
    }

    void loadInitialState();
  }, []);

  async function refreshRecentRuns() {
    try {
      const payload = await fetchRecentRuns();
      setRecentRuns(payload.runs);
      setDatabaseStatus(payload.database);
      setRecentRunsError(null);
    } catch {
      setRecentRuns([]);
      setRecentRunsError("读取近期回测失败");
    }
  }

  async function refreshDataAssets() {
    try {
      const [assets, factorPayload] = await Promise.all([fetchDataAssets(), fetchFactors()]);
      setDataAssets(assets.assets);
      setFactors(factorPayload.factors);
      setDatabaseStatus(assets.database);
    } catch {
      setDataAssets([]);
    }
  }

  async function openDataAsset(assetId: string) {
    try {
      const payload = await fetchDataAssetDetail(assetId);
      setSelectedDataAsset(payload.asset);
      setDatabaseStatus(payload.database);
    } catch {
      const fallback = dataAssets.find((asset) => asset.id === assetId);
      setSelectedDataAsset(fallback ? { ...fallback, description: "", syncJobs: [] } : null);
    }
  }

  const validationError = useMemo(() => {
    if (strategies.length === 0) {
      return "策略列表加载中";
    }
    if (!selectedStrategy) {
      return "当前策略不存在，请重新选择";
    }
    if (form.start >= form.end) {
      return "结束日期必须晚于开始日期";
    }
    if (!/^\d{6}$/.test(form.symbol)) {
      return "股票代码请输入 6 位 A股代码，例如 000001";
    }
    for (const param of selectedStrategy.params) {
      const value = form.strategyParams[param.key];
      if (param.valueType !== "int" && param.valueType !== "float") {
        continue;
      }
      if (typeof value !== "number" || !Number.isFinite(value)) {
        return `${param.label}必须填写数字`;
      }
      const min = param.min ?? Number.NEGATIVE_INFINITY;
      const max = param.max ?? Number.POSITIVE_INFINITY;
      if (value < min || value > max) {
        return `${param.label}必须在 ${min} 到 ${max} 之间`;
      }
    }
    const constraintError = evaluateStrategyConstraints(
      form.strategyParams,
      selectedStrategy.constraints ?? []
    );
    if (constraintError) {
      return constraintError;
    }
    return null;
  }, [form, selectedStrategy, strategies.length]);
  const blockingMessage =
    connectionState === "offline"
      ? "后端服务未连接，请先启动 API 服务。"
      : databaseStatus && !databaseStatus.connected
        ? "数据库未连接，回测已锁定；请先确认 MySQL 或数据库连接地址。"
        : null;
  const canRun = connectionState === "online" && databaseReady && !isRunning && !validationError;
  const candlestickOption = useMemo(
    () => (result && result.bars.length > 0 ? buildCandlestickOption(result) : null),
    [result]
  );
  const volumeOption = useMemo(
    () => (result && result.bars.length > 0 ? buildVolumeOption(result) : null),
    [result]
  );
  const equityOption = useMemo(
    () => (result && result.equityCurve.length > 0 ? buildEquityOption(result) : null),
    [result]
  );

  function handleStrategyChange(strategyId: string) {
    const strategy = strategies.find((item) => item.id === strategyId);
    setForm((current) => ({
      ...current,
      strategyId,
      strategyParams: strategy ? buildDefaultStrategyParams(strategy) : {}
    }));
    setError(null);
    setNotice(null);
  }

  function updateStrategyParam(param: StrategyParamDefinition, value: number) {
    setForm((current) => ({
      ...current,
      strategyParams: {
        ...current.strategyParams,
        [param.key]: param.valueType === "int" ? Math.trunc(value) : value
      }
    }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (validationError) {
      setError(validationError);
      return;
    }
    if (blockingMessage) {
      setError(blockingMessage);
      return;
    }

    setIsRunning(true);
    setError(null);
    setNotice(null);
    setCurrentJob({
      runId: "pending",
      status: "running",
      progress: 0.35,
      engine: "sync-local",
      submittedAt: new Date().toISOString(),
      symbol: form.symbol,
      strategyName: selectedStrategy?.name ?? form.strategyId,
      message: "正在提交本地回测任务"
    });
    try {
      const payload = await runBacktestJob(form);
      setCurrentJob(payload.job);
      setResult(payload.result);
      setDatabaseStatus(payload.result.database);
      setSelectedRunId(payload.result.runId ?? null);
      setLastRunAt(new Date().toLocaleString("zh-CN", { hour12: false }));
      await refreshRecentRuns();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "回测运行失败");
      setCurrentJob((job) =>
        job
          ? {
              ...job,
              status: "failed",
              progress: 1,
              completedAt: new Date().toISOString(),
              message: caught instanceof Error ? caught.message : "回测运行失败"
            }
          : null
      );
    } finally {
      setIsRunning(false);
    }
  }

  async function openRunDetail(runId: string) {
    setIsLoadingRunDetail(true);
    setError(null);
    setNotice(null);
    try {
      const detail = await fetchRunDetail(runId);
      const restoredResult = buildResultFromPersistedDetail(detail);
      setSelectedRunId(runId);
      setDatabaseStatus(detail.database);
      setResult(restoredResult);
      setForm(restoredResult.strategy.params);
      setLastRunAt(detail.summary.createdAt);
      setCurrentJob(jobFromRunSummary(detail.summary));
      setNotice("已加载历史运行；行情、指标和交易明细已恢复。");
    } catch (caught) {
      setError(normalizeHistoryRunError(caught));
    } finally {
      setIsLoadingRunDetail(false);
    }
  }

  return (
    <div className="app-shell platform-console">
      <PlatformHeader
        connectionState={connectionState}
        databaseStatus={databaseStatus}
        currentJob={currentJob}
        activeView={activeView}
        onNavigate={setActiveView}
      />

      <div className="workspace-shell">
        <LifecycleRail
          currentJob={currentJob}
          databaseStatus={databaseStatus}
          hasResult={result != null}
        />

        <div className="workspace-body">
          <PlatformOverview capabilities={platformCapabilities} />

          {activeView === "data" ? (
            <DataAssetsPage
              assets={dataAssets}
              selectedAsset={selectedDataAsset}
              databaseStatus={databaseStatus}
              onSelectAsset={openDataAsset}
              onRetry={refreshDataAssets}
            />
          ) : activeView === "strategies" ? (
            <StrategyLibraryPage
              strategies={strategies}
              factors={factors}
              selectedStrategyId={form.strategyId}
              onSelectStrategy={(strategyId) => {
                handleStrategyChange(strategyId);
                setActiveView("backtest");
              }}
            />
          ) : (
          <main className={result ? "workspace has-result" : "workspace"}>
            <aside className="sidebar control-sidebar">
              <form onSubmit={handleSubmit}>
                <UniverseDataSection form={form} setForm={setForm} />
                <StrategyConfigSection
                  strategies={strategies}
                  selectedStrategy={selectedStrategy}
                  strategyId={form.strategyId}
                  strategyParams={form.strategyParams}
                  onStrategyChange={handleStrategyChange}
                  onParamChange={updateStrategyParam}
                />
                <RiskExecutionSection form={form} setForm={setForm} />

                {validationError ? <div className="form-error" role="alert">{validationError}</div> : null}
                {error ? <div className="form-error" role="alert">{error}</div> : null}
                {notice ? <div className="form-info" role="status">{notice}</div> : null}
                {blockingMessage ? <div className="form-warning" role="status">{blockingMessage}</div> : null}
                {hasDirtyParams ? <div className="form-warning" role="status">参数已修改，请重新运行回测</div> : null}

                <button className="run-button" disabled={!canRun}>
                  {isRunning
                    ? "回测中..."
                    : strategies.length === 0
                      ? "加载策略"
                      : !databaseReady
                        ? "等待数据库"
                        : "运行回测"}
                </button>

                <p className="risk-note">回测结果基于历史数据，不构成投资建议。</p>
              </form>

              <DataSourcePanel status={databaseStatus} />
            </aside>

            <section className="main-panel">
              {result ? (
                <>
                  <ResultDashboard
                    result={result}
                    candlestickOption={candlestickOption}
                    volumeOption={volumeOption}
                    equityOption={equityOption}
                    runTimestamp={lastRunAt}
                  />
                </>
              ) : (
                <>
                  <ResearchWorkbench
                    form={form}
                    selectedStrategy={selectedStrategy}
                    result={result}
                    currentJob={currentJob}
                  />
                  <div className="empty-state">
                    <h2>选择策略后运行回测</h2>
                    <p>左侧选择策略模板、填写 A股代码和参数，主区域会展示 K线、策略指标、权益曲线和交易明细。</p>
                  </div>
                </>
              )}
            </section>

            <aside className="right-inspector">
              <QueueSimulationPanel
                currentJob={currentJob}
                dataCatalog={dataCatalog}
                isRunning={isRunning}
                recentRuns={visibleRecentRuns}
                result={result}
              />
              <DataCatalogPanel catalog={dataCatalog} />
              <RecentRunsPanel
                status={databaseStatus}
                runs={visibleRecentRuns}
                error={recentRunsError}
                selectedRunId={selectedRunId}
                isLoading={isLoadingRunDetail}
                onOpenRun={openRunDetail}
              />
            </aside>
          </main>
          )}
        </div>
      </div>
    </div>
  );
}

function buildDefaultStrategyParams(strategy: StrategyDefinition): StrategyParams {
  return Object.fromEntries(strategy.params.map((param) => [param.key, param.default]));
}

function buildResultFromPersistedDetail(detail: PersistedRunDetail): BacktestResponse {
  const request = requestFromRunSummary(detail.summary);
  const equityCurve = withDrawdown(detail.equityCurve);
  return {
    runId: detail.runId,
    symbol: detail.summary.symbol,
    strategy: {
      id: detail.summary.strategyId,
      name: detail.summary.strategyName,
      params: request
    },
    dataSource: {
      provider: detail.summary.provider,
      frequency: "1d",
      adjust: request.adjust,
      start: detail.summary.start,
      end: detail.summary.end,
      cached: true,
      sourceDetail: detail.summary.dataSourceDetail ?? "persisted run",
      dataVersion: detail.summary.dataVersion ?? "unknown",
      coverage: {
        status: "unknown",
        expectedRows: null,
        actualRows: detail.bars.length,
        missingDates: [],
        lastTradeDate: detail.bars.at(-1)?.datetime ?? null
      },
      engineVersion: detail.summary.engineVersion ?? "signal-close-v1",
      engineAssumptions: detail.summary.engineAssumptions ?? {}
    },
    database: detail.database,
    metrics: metricsFromRunSummary(detail, request),
    bars: detail.bars,
    indicatorLines: detail.indicatorLines,
    movingAverages: detail.movingAverages,
    signals: detail.signals,
    equityCurve,
    trades: detail.trades,
    logs: ["历史运行摘要已加载", ...detail.summary.logs]
  };
}

function requestFromRunSummary(summary: RunSummary): BacktestRequest {
  const raw = summary.params as Partial<BacktestRequest> | undefined;
  return {
    symbol: typeof raw?.symbol === "string" ? raw.symbol : summary.symbol,
    start: typeof raw?.start === "string" ? raw.start : summary.start,
    end: typeof raw?.end === "string" ? raw.end : summary.end,
    strategyId: typeof raw?.strategyId === "string" ? raw.strategyId : summary.strategyId,
    strategyParams: isStrategyParams(raw?.strategyParams)
      ? raw.strategyParams
      : strategyParamsFromRecord(summary.params),
    cash: typeof raw?.cash === "number" ? raw.cash : summary.metrics.starting_cash ?? 100000,
    commissionRate: typeof raw?.commissionRate === "number" ? raw.commissionRate : 0.001,
    adjust: typeof raw?.adjust === "string" ? raw.adjust : "qfq"
  };
}

function isStrategyParams(value: unknown): value is StrategyParams {
  return (
    value != null &&
    typeof value === "object" &&
    Object.values(value).every((item) => typeof item === "number")
  );
}

function strategyParamsFromRecord(record: Record<string, unknown>): StrategyParams {
  return Object.fromEntries(
    Object.entries(record).filter((entry): entry is [string, number] => typeof entry[1] === "number")
  );
}

function metricsFromRunSummary(detail: PersistedRunDetail, request: BacktestRequest): BacktestResponse["metrics"] {
  const metrics = detail.summary.metrics;
  return {
    startingCash: metrics.starting_cash ?? request.cash,
    finalEquity: metrics.final_equity ?? request.cash,
    totalReturn: metrics.total_return ?? 0,
    annualizedReturn: metrics.annualized_return ?? null,
    annualizedVolatility: metrics.annualized_volatility ?? null,
    sharpeRatio: metrics.sharpe_ratio ?? null,
    sortinoRatio: metrics.sortino_ratio ?? null,
    calmarRatio: metrics.calmar_ratio ?? null,
    maxDrawdown: metrics.max_drawdown ?? 0,
    tradeCount: metrics.trade_count ?? 0,
    closedTradeCount: metrics.closed_trade_count ?? null,
    winRate: metrics.win_rate ?? null,
    profitFactor: metrics.profit_factor ?? null,
    expectancy: metrics.expectancy ?? null,
    averageWin: metrics.average_win ?? null,
    averageLoss: metrics.average_loss ?? null,
    totalCommission: metrics.total_commission ?? null,
    exposure: metrics.exposure ?? null,
    averagePositionWeight: metrics.average_position_weight ?? null,
    maxPositionWeight: metrics.max_position_weight ?? null,
    turnover: metrics.turnover ?? null,
    barCount: detail.bars.length || detail.equityCurve.length,
    signalCount: detail.signals.length
  };
}

function dedupeRecentRuns(runs: RunSummary[]): RunSummary[] {
  const seen = new Set<string>();
  return runs.filter((run) => {
    const key = [
      run.symbol,
      run.strategyId,
      run.provider,
      run.start,
      run.end,
      stableStringify(run.params)
    ].join("|");
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }
  if (value != null && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${key}:${stableStringify(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function withDrawdown(
  equityCurve: PersistedRunDetail["equityCurve"]
): BacktestResponse["equityCurve"] {
  let peak = 0;
  return equityCurve.map((point) => {
    peak = Math.max(peak, point.equity);
    return {
      ...point,
      drawdown: peak > 0 ? point.equity / peak - 1 : 0
    };
  });
}

function normalizeHistoryRunError(caught: unknown): string {
  if (!(caught instanceof Error)) {
    return "读取历史运行失败";
  }
  if (caught.message === "Not Found" || caught.message.includes("404")) {
    return "这条历史运行不可用，可能来自旧数据或已被清理；请重新运行当前参数。";
  }
  return caught.message;
}

function jobFromRunSummary(summary: RunSummary): BacktestJob {
  return {
    runId: summary.runId,
    status: "succeeded",
    progress: 1,
    engine: "sync-local",
    submittedAt: summary.createdAt,
    completedAt: summary.createdAt,
    symbol: summary.symbol,
    strategyName: summary.strategyName,
    message: "历史回测任务已恢复"
  };
}

function PlatformHeader({
  connectionState,
  databaseStatus,
  currentJob,
  activeView,
  onNavigate
}: {
  connectionState: ConnectionState;
  databaseStatus: DatabaseStatus | null;
  currentJob: BacktestJob | null;
  activeView: WorkspaceView;
  onNavigate: (view: WorkspaceView) => void;
}) {
  const navItems: Array<{ label: string; view?: WorkspaceView; disabled?: boolean; reason?: string }> = [
    { label: "数据", view: "data" },
    { label: "研究", view: "research" },
    { label: "回测", view: "backtest" },
    { label: "模拟交易", disabled: true, reason: "模拟交易将在组合和订单模型完成后开放" },
    { label: "策略库", view: "strategies" },
    { label: "社区", disabled: true, reason: "外部策略需要授权和审核后才能导入" }
  ];
  return (
    <header className="app-header platform-header">
      <div className="brand-lockup">
        <div className="product-name">LH Quant</div>
        <div className="product-subtitle">量化投研平台</div>
      </div>
      <nav className="global-product-nav" data-testid="global-product-nav" aria-label="平台导航">
        {navItems.map((item) => (
          <button
            className={item.view === activeView ? "active" : ""}
            disabled={item.disabled}
            key={item.label}
            title={item.reason}
            type="button"
            onClick={() => item.view && onNavigate(item.view)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <div className="header-status">
        <span className="header-job-code" title={currentJob?.runId ?? "暂无任务"}>
          {currentJob?.runId ?? "无任务"}
        </span>
        <StatusBadge state={connectionState} />
        <DatabaseBadge status={databaseStatus} />
      </div>
    </header>
  );
}

function LifecycleRail({
  currentJob,
  databaseStatus,
  hasResult
}: {
  currentJob: BacktestJob | null;
  databaseStatus: DatabaseStatus | null;
  hasResult: boolean;
}) {
  const items = [
    { key: "data", label: "数据", detail: databaseStatus?.connected ? "已接入" : "待连接", state: databaseStatus?.connected ? "done" : "locked" },
    { key: "research", label: "研究", detail: "笔记本", state: "active" },
    { key: "backtest", label: "回测", detail: currentJob?.status === "succeeded" ? "已完成" : "任务", state: hasResult ? "done" : "active" },
    { key: "simulate", label: "模拟", detail: "队列", state: currentJob ? "active" : "locked" },
    { key: "live", label: "实盘", detail: "未启用", state: "locked" }
  ];
  return (
    <aside className="lifecycle-rail" data-testid="lifecycle-rail" aria-label="量化流程">
      <div className="rail-logo">LQ</div>
      {items.map((item) => (
        <button className={`lifecycle-item ${item.state}`} key={item.key} type="button">
          <span>{item.label}</span>
          <strong>{item.detail}</strong>
        </button>
      ))}
    </aside>
  );
}

function ResearchWorkbench({
  form,
  selectedStrategy,
  result,
  currentJob
}: {
  form: BacktestRequest;
  selectedStrategy: StrategyDefinition | null;
  result: BacktestResponse | null;
  currentJob: BacktestJob | null;
}) {
  const strategyName = selectedStrategy?.name ?? form.strategyId;
  const codeLines = [
    "from jqdata import *",
    `set_benchmark('${form.symbol}')`,
    `run_strategy('${form.strategyId}', symbol='${form.symbol}')`,
    `set_cash(${Math.round(form.cash)})`,
    `set_commission(${form.commissionRate})`
  ];
  return (
    <section className="research-workbench" data-testid="research-workbench">
      <div className="workbench-toolbar">
        <div>
          <span>研究</span>
          <strong>{strategyName}</strong>
        </div>
        <div className="workbench-actions" aria-label="研究动作">
          <button type="button">保存</button>
          <button type="button">回测</button>
          <button type="button">模拟</button>
        </div>
      </div>
      <div className="research-workbench-grid">
        <div className="research-terminal">
          <div className="terminal-tabs">
            <span className="active">strategy.py</span>
            <span>research.ipynb</span>
            <span>factor.py</span>
          </div>
          <pre aria-label="策略代码预览">
            {codeLines.map((line, index) => `${String(index + 1).padStart(2, "0")}  ${line}`).join("\n")}
          </pre>
        </div>
        <div className="research-snapshot">
          <div>
            <span>标的</span>
            <strong>{form.symbol}</strong>
          </div>
          <div>
            <span>区间</span>
            <strong>{form.start} 至 {form.end}</strong>
          </div>
          <div>
            <span>任务</span>
            <strong>{currentJob?.status ? jobStatusText(currentJob.status, false) : "待提交"}</strong>
          </div>
          <div>
            <span>累计收益</span>
            <strong>{result ? formatPercent(result.metrics.totalReturn) : "--"}</strong>
          </div>
        </div>
      </div>
    </section>
  );
}

function QueueSimulationPanel({
  currentJob,
  dataCatalog,
  isRunning,
  recentRuns,
  result
}: {
  currentJob: BacktestJob | null;
  dataCatalog: DataCatalogResponse | null;
  isRunning: boolean;
  recentRuns: RunSummary[];
  result: BacktestResponse | null;
}) {
  const availableDatasets = dataCatalog?.datasets.filter((dataset) => dataset.status === "available").length ?? 0;
  return (
    <section className="queue-simulation-panel" data-testid="queue-simulation-panel">
      <JobStatusPanel job={currentJob} isRunning={isRunning} />
      <div className="simulation-ledger">
        <div className="ledger-heading">
          <span>模拟盘</span>
          <strong>{currentJob?.status === "succeeded" ? "可接力" : "待回测"}</strong>
        </div>
        <div className="ledger-grid">
          <span>初始资金</span>
          <strong>{result ? result.metrics.startingCash.toLocaleString("zh-CN") : "100,000"}</strong>
          <span>最近净值</span>
          <strong>{result ? result.metrics.finalEquity.toLocaleString("zh-CN") : "--"}</strong>
          <span>历史任务</span>
          <strong>{recentRuns.length}</strong>
          <span>可用数据</span>
          <strong>{availableDatasets}</strong>
        </div>
      </div>
    </section>
  );
}

function StatusBadge({ state }: { state: ConnectionState }) {
  const text = state === "checking" ? "连接中" : state === "online" ? "已连接" : "连接失败";
  return <span className={`status-badge ${state}`}>{text}</span>;
}

function DatabaseBadge({ status }: { status: DatabaseStatus | null }) {
  if (!status) {
    return <span className="status-badge checking">数据库检查中</span>;
  }
  return (
    <span className={`status-badge ${status.connected ? "online" : "offline"}`} title={status.message}>
      {status.connected ? "数据库已连接" : "数据库未连接"}
    </span>
  );
}

function PlatformOverview({ capabilities }: { capabilities: PlatformCapabilitiesResponse | null }) {
  const modules =
    capabilities?.modules ?? [
      {
        id: "loading",
        name: "平台模块",
        status: "preview" as const,
        description: "正在读取平台能力。",
        features: ["数据", "研究", "回测", "交易"]
      }
    ];
  return (
    <nav
      className="platform-nav platform-status-strip"
      data-testid="platform-overview"
      aria-label="平台能力"
    >
      <div className="platform-nav-label">
        <span>平台能力</span>
        <strong>{capabilities?.apiVersion ?? "loading"}</strong>
      </div>
      <div className="capability-strip" data-testid="platform-status-strip">
        {modules.map((module) => (
          <div className={`capability-pill ${module.status}`} key={module.id}>
            <strong>{module.name}</strong>
            <span>{module.features.slice(0, 2).join(" / ")}</span>
            <em>{moduleStatusText(module.status)}</em>
          </div>
        ))}
      </div>
    </nav>
  );
}

function moduleStatusText(status: "available" | "preview" | "planned"): string {
  if (status === "available") {
    return "可用";
  }
  if (status === "preview") {
    return "预览";
  }
  return "规划";
}

function DataSourcePanel({ status }: { status: DatabaseStatus | null }) {
  return (
    <section className="sidebar-info">
      <h2>数据闭环</h2>
      <div className="info-line">
        <span>数据库</span>
        <strong>{status?.connected ? "已连接" : "未连接"}</strong>
      </div>
      <div className="info-line">
        <span>行情策略</span>
        <strong>行情库优先</strong>
      </div>
      <div className="info-line">
        <span>主数据源</span>
        <strong>AKShare 入库</strong>
      </div>
      {!status?.connected ? (
        <p className="status-note" title={status?.message}>
          数据库未连接时回测会被锁定，避免产生无法审计和复现的临时结果。
        </p>
      ) : null}
    </section>
  );
}

function JobStatusPanel({ job, isRunning }: { job: BacktestJob | null; isRunning: boolean }) {
  const progress = Math.round((job?.progress ?? 0) * 100);
  return (
    <section className="sidebar-info" data-testid="job-status-panel">
      <h2>任务状态</h2>
      {job ? (
        <div className="job-status-card">
          <div className="job-status-heading">
            <strong>{job.symbol}</strong>
            <span className={`module-status ${job.status === "succeeded" ? "available" : job.status === "failed" ? "failed" : "preview"}`}>
              {jobStatusText(job.status, isRunning)}
            </span>
          </div>
          <div className="job-progress" aria-label="任务进度">
            <span style={{ width: `${progress}%` }} />
          </div>
          <div className="job-status-grid">
            <span>策略</span>
            <strong>{job.strategyName}</strong>
            <span>引擎</span>
            <strong>{job.engine}</strong>
            <span>任务号</span>
            <strong title={job.runId}>{job.runId}</strong>
          </div>
          <p className="status-note">{job.message}</p>
        </div>
      ) : (
        <p className="status-note">提交回测后会显示任务编号、执行引擎和进度。</p>
      )}
    </section>
  );
}

function jobStatusText(status: BacktestJob["status"], isRunning: boolean): string {
  if (isRunning || status === "running") {
    return "运行中";
  }
  if (status === "succeeded") {
    return "完成";
  }
  if (status === "failed") {
    return "失败";
  }
  if (status === "queued") {
    return "排队";
  }
  return "已取消";
}

function DataCatalogPanel({ catalog }: { catalog: DataCatalogResponse | null }) {
  return (
    <section className="sidebar-info">
      <h2>数据目录</h2>
      {catalog ? (
        <div className="dataset-list">
          {catalog.datasets.map((dataset) => (
            <div className={`dataset-item ${dataset.status}`} key={dataset.id}>
              <div>
                <strong>{dataset.name}</strong>
                <span>{dataset.provider} · {dataset.frequency}</span>
              </div>
              <span className={`module-status ${dataset.status}`}>{moduleStatusText(dataset.status)}</span>
              <p>{dataset.coverage}</p>
              <div className="dataset-fields">
                {dataset.fields.slice(0, 5).map((field) => (
                  <span key={field}>{field}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="status-note">正在读取数据目录。</p>
      )}
    </section>
  );
}

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
  return (
    <section className="sidebar-info">
      <h2>近期回测</h2>
      {!status?.connected ? (
        <p className="status-note">数据库连上后会展示最近运行记录。</p>
      ) : error ? (
        <p className="status-note">{error}</p>
      ) : runs.length === 0 ? (
        <p className="status-note">暂无回测记录。</p>
      ) : (
        <div className="run-list">
          {runs.map((run) => (
            <button
              className={run.runId === selectedRunId ? "run-list-item active" : "run-list-item"}
              disabled={isLoading}
              key={run.runId}
              onClick={() => onOpenRun(run.runId)}
              title={run.runId}
              type="button"
            >
              <div>
                <strong>{run.symbol}</strong>
                <span>{run.strategyName}</span>
              </div>
              <div className="run-list-metrics">
                <span>{run.metrics.total_return != null ? formatPercent(run.metrics.total_return) : "--"}</span>
                <span>{run.provider}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function buildCandlestickOption(result: BacktestResponse): EChartsCoreOption {
  const dates = result.bars.map((bar) => bar.datetime);
  const kline = result.bars.map((bar) => [bar.open, bar.close, bar.low, bar.high]);
  const buys = result.signals
    .filter((item) => item.signal === 1)
    .map((item) => [item.datetime, item.price]);
  const sells = result.signals
    .filter((item) => item.signal === -1)
    .map((item) => [item.datetime, item.price]);
  const indicatorSeries = result.indicatorLines.map((line) => ({
    name: line.name,
    type: "line",
    data: line.points.map((point) => point.value),
    smooth: true,
    showSymbol: false,
    lineStyle: { width: 1.5, color: line.color }
  }));

  return {
    animation: false,
    aria: { enabled: true },
    tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
    legend: { top: 0, data: ["K线", ...result.indicatorLines.map((line) => line.name), "买入", "卖出"] },
    grid: { left: 56, right: 24, top: 36, bottom: 52 },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 22, bottom: 14 }],
    xAxis: { type: "category", data: dates, boundaryGap: true, axisLine: { lineStyle: { color: CHART_COLORS.axis } } },
    yAxis: { scale: true, axisLine: { lineStyle: { color: CHART_COLORS.axis } }, splitLine: { lineStyle: { color: CHART_COLORS.splitLine } } },
    series: [
      {
        name: "K线",
        type: "candlestick",
        data: kline,
        itemStyle: {
          color: CHART_COLORS.marketUp,
          color0: CHART_COLORS.marketDown,
          borderColor: CHART_COLORS.marketUp,
          borderColor0: CHART_COLORS.marketDown
        }
      },
      ...indicatorSeries,
      { name: "买入", type: "scatter", data: buys, symbol: "triangle", symbolSize: 11, itemStyle: { color: CHART_COLORS.marketUp } },
      { name: "卖出", type: "scatter", data: sells, symbol: "triangle", symbolRotate: 180, symbolSize: 11, itemStyle: { color: CHART_COLORS.marketDown } }
    ]
  };
}

function buildVolumeOption(result: BacktestResponse): EChartsCoreOption {
  const dates = result.bars.map((bar) => bar.datetime);
  const volume = result.bars.map((bar) => ({
    value: bar.volume,
    itemStyle: { color: bar.close >= bar.open ? CHART_COLORS.marketUp : CHART_COLORS.marketDown }
  }));

  return {
    animation: false,
    aria: { enabled: true },
    tooltip: { trigger: "axis" },
    grid: { left: 56, right: 20, top: 16, bottom: 30 },
    xAxis: { type: "category", data: dates, axisLabel: { hideOverlap: true } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: CHART_COLORS.splitLine } } },
    series: [{ name: "成交量", type: "bar", data: volume, barWidth: "58%" }]
  };
}

function buildEquityOption(result: BacktestResponse): EChartsCoreOption {
  const dates = result.equityCurve.map((item) => item.datetime);
  const equity = result.equityCurve.map((item) => item.equity);
  const drawdown = result.equityCurve.map((item) => Number((item.drawdown * 100).toFixed(2)));

  return {
    animation: false,
    aria: { enabled: true },
    tooltip: { trigger: "axis" },
    legend: { top: 0, data: ["权益", "回撤"] },
    grid: { left: 58, right: 48, top: 36, bottom: 30 },
    xAxis: { type: "category", data: dates, axisLabel: { hideOverlap: true } },
    yAxis: [
      { type: "value", scale: true, splitLine: { lineStyle: { color: CHART_COLORS.splitLine } } },
      { type: "value", axisLabel: { formatter: "{value}%" }, splitLine: { show: false } }
    ],
    series: [
      { name: "权益", type: "line", data: equity, showSymbol: false, lineStyle: { width: 2, color: CHART_COLORS.equity } },
      { name: "回撤", type: "line", yAxisIndex: 1, data: drawdown, showSymbol: false, areaStyle: { opacity: 0.12 }, lineStyle: { width: 1.5, color: CHART_COLORS.marketDown } }
    ]
  };
}
