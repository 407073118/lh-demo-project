import type { BacktestResponse, StrategyParams } from "../../api";
import { formatNumber } from "../../format";

export function DataLineagePanel({ result }: { result: BacktestResponse }) {
  const rows = [
    ["运行编号", result.runId ?? "未落库"],
    ["策略", result.strategy.name],
    ["策略 ID", result.strategy.id],
    ["数据来源", result.dataSource.provider],
    ["数据频率", result.dataSource.frequency],
    ["复权方式", result.dataSource.adjust || "不复权"],
    ["数据状态", result.dataSource.cached ? "数据库缓存" : "实时读取"],
    ["回测区间", `${result.dataSource.start} 至 ${result.dataSource.end}`],
    ["K线数量", `${result.metrics.barCount} 根`],
    ["交易信号", `${result.metrics.signalCount} 个`],
    ["数据库", result.database.connected ? "已连接" : "未连接"],
    ["策略参数", formatStrategyParams(result.strategy.params.strategyParams)]
  ];

  return (
    <div className="lineage-layout">
      <section className="panel">
        <div className="panel-title">运行元数据</div>
        <div className="overview-grid">
          {rows.map(([label, value]) => (
            <div className="overview-row" key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
      </section>
      <section className="panel">
        <div className="panel-title">运行日志</div>
        <div className="run-logs">
          {result.logs.map((line, index) => (
            <div key={`${line}-${index}`}>{line}</div>
          ))}
        </div>
      </section>
    </div>
  );
}

function formatStrategyParams(params: StrategyParams): string {
  const entries = Object.entries(params);
  if (entries.length === 0) {
    return "默认参数";
  }
  return entries
    .map(([key, value]) => `${strategyParamName(key)}=${formatNumber(value)}`)
    .join(" / ");
}

function strategyParamName(key: string): string {
  const names: Record<string, string> = {
    fastWindow: "短均线",
    slowWindow: "长均线",
    lookbackWindow: "突破窗口",
    exitWindow: "退出窗口",
    rsiWindow: "RSI周期",
    oversold: "超卖阈值",
    overbought: "过热阈值"
  };
  return names[key] ?? key;
}
