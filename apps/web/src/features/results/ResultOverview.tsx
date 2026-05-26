import type { BacktestResponse } from "../../api";
import { formatMoney, formatNumber, formatPercent } from "../../format";

type MetricTone = "positive" | "negative" | "risk" | "neutral";

type MetricItem = {
  label: string;
  value: string;
  tone: MetricTone;
};

export function ResultOverview({ result }: { result: BacktestResponse }) {
  const { metrics } = result;
  const metricsItems: MetricItem[] = [
    {
      label: "累计收益",
      value: formatPercent(metrics.totalReturn),
      tone: metricTone(metrics.totalReturn)
    },
    {
      label: "最大回撤",
      value: formatPercent(metrics.maxDrawdown),
      tone: "risk"
    },
    {
      label: "最终权益",
      value: formatMoney(metrics.finalEquity),
      tone: "neutral"
    },
    {
      label: "夏普比率",
      value: formatOptionalNumber(metrics.sharpeRatio),
      tone: "neutral"
    },
    {
      label: "交易次数",
      value: formatNumber(metrics.tradeCount, 0),
      tone: "neutral"
    },
    {
      label: "胜率",
      value: formatOptionalPercent(metrics.winRate),
      tone: "neutral"
    }
  ];

  return (
    <section className="compact-metric-strip" aria-label="核心回测指标">
      {metricsItems.map((metric) => (
        <div className={`compact-result-metric ${metric.tone}`} key={metric.label}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
        </div>
      ))}
    </section>
  );
}

function metricTone(value: number): MetricTone {
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
