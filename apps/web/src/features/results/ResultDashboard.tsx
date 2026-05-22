import { useState } from "react";
import type { EChartsCoreOption } from "echarts/core";
import type { BacktestResponse } from "../../api";
import { formatNumber } from "../../format";
import { DataLineagePanel } from "./DataLineagePanel";
import { OrdersTradesPanel } from "./OrdersTradesPanel";
import { PriceSignalPanel } from "./PriceSignalPanel";
import { ResultOverview } from "./ResultOverview";
import { RiskReturnPanel } from "./RiskReturnPanel";
import { Panel, PanelTitle } from "./uiPrimitives";

type ResultDashboardProps = {
  result: BacktestResponse;
  candlestickOption: EChartsCoreOption | null;
  volumeOption: EChartsCoreOption | null;
  equityOption: EChartsCoreOption | null;
  runTimestamp: string;
};

type DetailView = "trades" | "chartData" | "logs" | "lineage";

export function ResultDashboard({
  result,
  candlestickOption,
  volumeOption,
  equityOption,
  runTimestamp
}: ResultDashboardProps) {
  return (
    <div className="result-dashboard" data-testid="result-dashboard">
      <RunSummaryBar result={result} runTimestamp={runTimestamp} />
      <ResultOverview result={result} />
      <div className="dashboard-chart-grid">
        <PriceSignalPanel candlestickOption={candlestickOption} volumeOption={volumeOption} />
        <RiskReturnPanel result={result} equityOption={equityOption} />
      </div>
      <RunDetailsPanel result={result} />
    </div>
  );
}

function RunSummaryBar({
  result,
  runTimestamp
}: {
  result: BacktestResponse;
  runTimestamp: string;
}) {
  return (
    <section className="run-summary-bar" aria-label="运行快照">
      <div>
        <span>策略</span>
        <strong>{result.strategy.name}</strong>
      </div>
      <div>
        <span>数据源</span>
        <strong>{result.dataSource.provider}</strong>
      </div>
      <div>
        <span>区间</span>
        <strong>
          {result.dataSource.start} 至 {result.dataSource.end}
        </strong>
      </div>
      <div>
        <span>运行编号</span>
        <strong>{result.runId ?? "未落库"}</strong>
      </div>
      <div>
        <span>最近运行</span>
        <strong>{runTimestamp}</strong>
      </div>
    </section>
  );
}

function RunDetailsPanel({ result }: { result: BacktestResponse }) {
  const [activeView, setActiveView] = useState<DetailView>("trades");

  return (
    <section className="run-details">
      <div className="detail-toggle" aria-label="运行明细视图">
        <button
          aria-pressed={activeView === "trades"}
          className={activeView === "trades" ? "detail-toggle-button active" : "detail-toggle-button"}
          onClick={() => setActiveView("trades")}
          type="button"
        >
          交易记录
        </button>
        <button
          aria-pressed={activeView === "chartData"}
          className={activeView === "chartData" ? "detail-toggle-button active" : "detail-toggle-button"}
          data-testid="chart-data-toggle"
          onClick={() => setActiveView("chartData")}
          type="button"
        >
          图表数据
        </button>
        <button
          aria-pressed={activeView === "logs"}
          className={activeView === "logs" ? "detail-toggle-button active" : "detail-toggle-button"}
          onClick={() => setActiveView("logs")}
          type="button"
        >
          运行日志
        </button>
        <button
          aria-pressed={activeView === "lineage"}
          className={activeView === "lineage" ? "detail-toggle-button active" : "detail-toggle-button"}
          onClick={() => setActiveView("lineage")}
          type="button"
        >
          数据血缘
        </button>
      </div>
      {activeView === "trades" ? <OrdersTradesPanel result={result} /> : null}
      {activeView === "chartData" ? <ChartDataPanel result={result} /> : null}
      {activeView === "logs" ? <RunLogsPanel logs={result.logs} /> : null}
      {activeView === "lineage" ? <DataLineagePanel result={result} /> : null}
    </section>
  );
}

function ChartDataPanel({ result }: { result: BacktestResponse }) {
  const visibleBars = result.bars.slice(-30).reverse();
  return (
    <Panel>
      <div className="panel-heading-row">
        <PanelTitle>图表数据</PanelTitle>
        <div className="chart-data-summary">
          {result.bars.length} 根K线 · {result.indicatorLines.length} 条指标线
        </div>
      </div>
      {visibleBars.length === 0 ? (
        <div className="table-empty">当前结果没有可展示的行情明细</div>
      ) : (
        <div className="table-wrap">
          <table data-testid="chart-data-table">
            <thead>
              <tr>
                <th>日期</th>
                <th>开盘</th>
                <th>最高</th>
                <th>最低</th>
                <th>收盘</th>
                <th>成交量</th>
              </tr>
            </thead>
            <tbody>
              {visibleBars.map((bar) => (
                <tr key={bar.datetime}>
                  <td>{bar.datetime}</td>
                  <td>{formatNumber(bar.open)}</td>
                  <td>{formatNumber(bar.high)}</td>
                  <td>{formatNumber(bar.low)}</td>
                  <td>{formatNumber(bar.close)}</td>
                  <td>{formatNumber(bar.volume, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function RunLogsPanel({ logs }: { logs: string[] }) {
  return (
    <Panel>
      <PanelTitle>运行日志</PanelTitle>
      <div className="run-logs">
        {logs.length === 0 ? (
          <div>暂无运行日志。</div>
        ) : (
          logs.map((line, index) => <div key={`${line}-${index}`}>{line}</div>)
        )}
      </div>
    </Panel>
  );
}
