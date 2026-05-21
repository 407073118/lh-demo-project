import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import type { EChartsCoreOption } from "echarts/core";
import type {
  BacktestRequest,
  BacktestResponse,
  DatabaseStatus,
  RunSummary,
  StrategyDefinition,
  StrategyParamDefinition,
  StrategyParams
} from "./api";
import { fetchHealth, fetchRecentRuns, fetchRunDetail, fetchStrategies, runBacktest } from "./api";
import {
  RiskExecutionSection,
  StrategyConfigSection,
  UniverseDataSection
} from "./features/config/WorkbenchConfigSections";
import { DataLineagePanel } from "./features/results/DataLineagePanel";
import { OrdersTradesPanel } from "./features/results/OrdersTradesPanel";
import { PriceSignalPanel } from "./features/results/PriceSignalPanel";
import { ResultOverview } from "./features/results/ResultOverview";
import { ResultTabs } from "./features/results/ResultTabs";
import { RiskReturnPanel } from "./features/results/RiskReturnPanel";
import { formatPercent } from "./format";
import { evaluateStrategyConstraints } from "./strategyConstraints";

const today = new Date().toISOString().slice(0, 10);
const defaultStrategyId = "moving_average";
const defaultStrategyParams: StrategyParams = {
  fastWindow: 5,
  slowWindow: 20
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

export default function App() {
  const [connectionState, setConnectionState] = useState<ConnectionState>("checking");
  const [strategies, setStrategies] = useState<StrategyDefinition[]>([]);
  const [form, setForm] = useState<BacktestRequest>(initialRequest);
  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [databaseStatus, setDatabaseStatus] = useState<DatabaseStatus | null>(null);
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
  const dataSourceText = result
    ? `${result.dataSource.provider} A股日线`
    : "平台行情库（AKShare入库优先）";
  const hasDirtyParams = result ? JSON.stringify(form) !== JSON.stringify(result.strategy.params) : false;
  const databaseReady = databaseStatus?.connected === true;

  useEffect(() => {
    async function loadInitialState() {
      try {
        const [health, strategyPayload] = await Promise.all([fetchHealth(), fetchStrategies()]);
        setConnectionState(health.status === "ok" ? "online" : "offline");
        setDatabaseStatus(health.database);
        setStrategies(strategyPayload.strategies);
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
      if (!Number.isFinite(value)) {
        return `${param.label}必须填写数字`;
      }
      if (value < param.min || value > param.max) {
        return `${param.label}必须在 ${param.min} 到 ${param.max} 之间`;
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
    () => (result ? buildCandlestickOption(result) : null),
    [result]
  );
  const volumeOption = useMemo(() => (result ? buildVolumeOption(result) : null), [result]);
  const equityOption = useMemo(() => (result ? buildEquityOption(result) : null), [result]);

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
    try {
      const payload = await runBacktest(form);
      setResult(payload);
      setDatabaseStatus(payload.database);
      setSelectedRunId(payload.runId ?? null);
      setLastRunAt(new Date().toLocaleString("zh-CN", { hour12: false }));
      await refreshRecentRuns();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "回测运行失败");
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
      setSelectedRunId(runId);
      setDatabaseStatus(detail.database);
      setLastRunAt(detail.summary.createdAt);
      setNotice("已加载历史运行摘要；完整价格图需要重新运行或后续保存 bars 快照。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取回测详情失败");
    } finally {
      setIsLoadingRunDetail(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <div className="product-name">LH Quant A股研究工作台</div>
          <div className="product-subtitle">真实数据 · 策略配置 · 回测分析</div>
        </div>
        <div className="header-status">
          <StatusBadge state={connectionState} />
          <DatabaseBadge status={databaseStatus} />
          <span>数据源：{dataSourceText}</span>
          <span>运行编号：{result?.runId ?? "--"}</span>
          <span>最近运行：{lastRunAt}</span>
        </div>
      </header>

      <main className="workspace">
        <aside className="sidebar">
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

            {validationError ? <div className="form-error">{validationError}</div> : null}
            {error ? <div className="form-error">{error}</div> : null}
            {notice ? <div className="form-info">{notice}</div> : null}
            {blockingMessage ? <div className="form-warning">{blockingMessage}</div> : null}
            {hasDirtyParams ? <div className="form-warning">参数已修改，请重新运行回测</div> : null}

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
          <RecentRunsPanel
            status={databaseStatus}
            runs={recentRuns}
            error={recentRunsError}
            selectedRunId={selectedRunId}
            isLoading={isLoadingRunDetail}
            onOpenRun={openRunDetail}
          />
        </aside>

        <section className="main-panel">
          {result ? (
            <ResultTabs
              panels={{
                overview: <ResultOverview result={result} />,
                risk: <RiskReturnPanel result={result} equityOption={equityOption} />,
                price: (
                  <PriceSignalPanel
                    candlestickOption={candlestickOption}
                    volumeOption={volumeOption}
                  />
                ),
                orders: <OrdersTradesPanel result={result} />,
                lineage: <DataLineagePanel result={result} />
              }}
            />
          ) : (
            <div className="empty-state">
              <h2>选择策略后运行回测</h2>
              <p>左侧选择策略模板、填写 A股代码和参数，右侧会展示 K线、策略指标、权益曲线和交易明细。</p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

function buildDefaultStrategyParams(strategy: StrategyDefinition): StrategyParams {
  return Object.fromEntries(strategy.params.map((param) => [param.key, param.default]));
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
    tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
    legend: { top: 0, data: ["K线", ...result.indicatorLines.map((line) => line.name), "买入", "卖出"] },
    grid: { left: 56, right: 24, top: 36, bottom: 52 },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 22, bottom: 14 }],
    xAxis: { type: "category", data: dates, boundaryGap: true, axisLine: { lineStyle: { color: "#AEB7C4" } } },
    yAxis: { scale: true, axisLine: { lineStyle: { color: "#AEB7C4" } }, splitLine: { lineStyle: { color: "#EEF1F5" } } },
    series: [
      {
        name: "K线",
        type: "candlestick",
        data: kline,
        itemStyle: {
          color: "#D92D20",
          color0: "#039855",
          borderColor: "#D92D20",
          borderColor0: "#039855"
        }
      },
      ...indicatorSeries,
      { name: "买入", type: "scatter", data: buys, symbol: "triangle", symbolSize: 11, itemStyle: { color: "#D92D20" } },
      { name: "卖出", type: "scatter", data: sells, symbol: "triangle", symbolRotate: 180, symbolSize: 11, itemStyle: { color: "#039855" } }
    ]
  };
}

function buildVolumeOption(result: BacktestResponse): EChartsCoreOption {
  const dates = result.bars.map((bar) => bar.datetime);
  const volume = result.bars.map((bar) => ({
    value: bar.volume,
    itemStyle: { color: bar.close >= bar.open ? "#D92D20" : "#039855" }
  }));

  return {
    animation: false,
    tooltip: { trigger: "axis" },
    grid: { left: 56, right: 20, top: 16, bottom: 30 },
    xAxis: { type: "category", data: dates, axisLabel: { hideOverlap: true } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#EEF1F5" } } },
    series: [{ name: "成交量", type: "bar", data: volume, barWidth: "58%" }]
  };
}

function buildEquityOption(result: BacktestResponse): EChartsCoreOption {
  const dates = result.equityCurve.map((item) => item.datetime);
  const equity = result.equityCurve.map((item) => item.equity);
  const drawdown = result.equityCurve.map((item) => Number((item.drawdown * 100).toFixed(2)));

  return {
    animation: false,
    tooltip: { trigger: "axis" },
    legend: { top: 0, data: ["权益", "回撤"] },
    grid: { left: 58, right: 48, top: 36, bottom: 30 },
    xAxis: { type: "category", data: dates, axisLabel: { hideOverlap: true } },
    yAxis: [
      { type: "value", scale: true, splitLine: { lineStyle: { color: "#EEF1F5" } } },
      { type: "value", axisLabel: { formatter: "{value}%" }, splitLine: { show: false } }
    ],
    series: [
      { name: "权益", type: "line", data: equity, showSymbol: false, lineStyle: { width: 2, color: "#2563EB" } },
      { name: "回撤", type: "line", yAxisIndex: 1, data: drawdown, showSymbol: false, areaStyle: { opacity: 0.12 }, lineStyle: { width: 1.5, color: "#039855" } }
    ]
  };
}
