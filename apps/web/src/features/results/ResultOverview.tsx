import type { BacktestResponse } from "../../api";
import { formatMoney, formatNumber, formatPercent } from "../../format";

export function ResultOverview({ result }: { result: BacktestResponse }) {
  const { metrics } = result;
  const items = [
    ["累计收益", formatPercent(metrics.totalReturn)],
    ["年化收益", formatOptionalPercent(metrics.annualizedReturn)],
    ["最大回撤", formatPercent(metrics.maxDrawdown)],
    ["年化波动", formatOptionalPercent(metrics.annualizedVolatility)],
    ["夏普比率", formatOptionalNumber(metrics.sharpeRatio)],
    ["索提诺比率", formatOptionalNumber(metrics.sortinoRatio)],
    ["卡玛比率", formatOptionalNumber(metrics.calmarRatio)],
    ["胜率", formatOptionalPercent(metrics.winRate)],
    ["换手率", formatOptionalNumber(metrics.turnover)],
    ["资金暴露", formatOptionalPercent(metrics.exposure)],
    ["最终权益", formatMoney(metrics.finalEquity)],
    ["交易次数", String(metrics.tradeCount)]
  ];

  return (
    <div className="metric-strip result-metric-strip">
      {items.map(([label, value]) => (
        <div className="metric-item" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function formatOptionalNumber(value: number | null): string {
  return value == null ? "--" : formatNumber(value);
}

function formatOptionalPercent(value: number | null): string {
  return value == null ? "--" : formatPercent(value);
}
