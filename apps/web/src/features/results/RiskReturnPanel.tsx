import type { EChartsCoreOption } from "echarts/core";
import type { BacktestResponse } from "../../api";
import { EChart } from "../../EChart";
import { formatMoney, formatNumber, formatPercent } from "../../format";

export function RiskReturnPanel({
  result,
  equityOption
}: {
  result: BacktestResponse;
  equityOption: EChartsCoreOption | null;
}) {
  const { metrics } = result;
  const riskItems = [
    ["起始资金", formatMoney(metrics.startingCash)],
    ["最终权益", formatMoney(metrics.finalEquity)],
    ["累计收益", formatPercent(metrics.totalReturn)],
    ["最大回撤", formatPercent(metrics.maxDrawdown)],
    ["年化收益", formatOptionalPercent(metrics.annualizedReturn)],
    ["年化波动", formatOptionalPercent(metrics.annualizedVolatility)],
    ["夏普比率", formatOptionalNumber(metrics.sharpeRatio)],
    ["索提诺比率", formatOptionalNumber(metrics.sortinoRatio)],
    ["卡玛比率", formatOptionalNumber(metrics.calmarRatio)],
    ["资金暴露", formatOptionalPercent(metrics.exposure)],
    ["平均仓位", formatOptionalPercent(metrics.averagePositionWeight)],
    ["最大仓位", formatOptionalPercent(metrics.maxPositionWeight)]
  ];

  return (
    <div className="risk-return-layout">
      <section className="panel">
        <div className="panel-title">权益与回撤</div>
        {equityOption ? <EChart option={equityOption} className="chart chart-large" /> : null}
      </section>
      <section className="panel">
        <div className="panel-title">风险指标</div>
        <div className="compact-metric-grid">
          {riskItems.map(([label, value]) => (
            <div className="compact-metric" key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function formatOptionalNumber(value: number | null): string {
  return value == null ? "--" : formatNumber(value);
}

function formatOptionalPercent(value: number | null): string {
  return value == null ? "--" : formatPercent(value);
}
