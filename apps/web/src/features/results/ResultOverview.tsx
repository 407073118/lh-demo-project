import type { BacktestResponse } from "../../api";
import { formatMoney, formatNumber, formatPercent } from "../../format";

export function ResultOverview({ result }: { result: BacktestResponse }) {
  const { metrics } = result;
  const primaryItems = [
    ["累计收益", formatPercent(metrics.totalReturn), metricTone(metrics.totalReturn)],
    ["最大回撤", formatPercent(metrics.maxDrawdown), "risk"],
    ["最终权益", formatMoney(metrics.finalEquity), metricTone(metrics.finalEquity - metrics.startingCash)],
    ["夏普比率", formatOptionalNumber(metrics.sharpeRatio), metricTone(metrics.sharpeRatio ?? 0)],
    ["交易次数", String(metrics.tradeCount), "neutral"]
  ];
  const secondaryItems = [
    ["年化收益", formatOptionalPercent(metrics.annualizedReturn)],
    ["年化波动", formatOptionalPercent(metrics.annualizedVolatility)],
    ["索提诺比率", formatOptionalNumber(metrics.sortinoRatio)],
    ["卡玛比率", formatOptionalNumber(metrics.calmarRatio)],
    ["胜率", formatOptionalPercent(metrics.winRate)],
    ["换手率", formatOptionalNumber(metrics.turnover)],
    ["资金暴露", formatOptionalPercent(metrics.exposure)]
  ];

  return (
    <section className="result-overview" aria-label="核心回测指标">
      <div className="metric-strip result-metric-strip">
        {primaryItems.map(([label, value, tone]) => (
          <div className={`metric-item ${tone}`} key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <section className="panel metric-detail-panel">
        <h2 className="panel-title">指标明细</h2>
        <div className="compact-metric-grid">
          {secondaryItems.map(([label, value]) => (
            <div className="compact-metric" key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
      </section>
    </section>
  );
}

function metricTone(value: number): "positive" | "negative" | "neutral" {
  if (value > 0) {
    return "positive";
  }
  if (value < 0) {
    return "negative";
  }
  return "neutral";
}

function formatOptionalNumber(value: number | null): string {
  return value == null ? "--" : formatNumber(value);
}

function formatOptionalPercent(value: number | null): string {
  return value == null ? "--" : formatPercent(value);
}
