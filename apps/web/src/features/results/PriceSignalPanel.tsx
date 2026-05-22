import type { EChartsCoreOption } from "echarts/core";
import { EChart } from "../../EChart";

export function PriceSignalPanel({
  candlestickOption,
  volumeOption
}: {
  candlestickOption: EChartsCoreOption | null;
  volumeOption: EChartsCoreOption | null;
}) {
  return (
    <div className="price-signal-layout">
      <section className="panel">
        <h2 className="panel-title">K线、策略指标与买卖点</h2>
        {candlestickOption ? (
          <EChart
            option={candlestickOption}
            className="chart chart-large"
            ariaLabel="价格K线、策略指标线和买卖点图"
            fallback="图表展示回测区间内的K线、策略指标线、买入点和卖出点。"
          />
        ) : (
          <div className="chart-empty">历史摘要不含价格 K线，重新运行可查看完整图表。</div>
        )}
      </section>
      <section className="panel">
        <h2 className="panel-title">成交量</h2>
        {volumeOption ? (
          <EChart
            option={volumeOption}
            className="chart chart-small"
            ariaLabel="成交量柱状图"
            fallback="图表展示每个交易日的成交量。"
          />
        ) : (
          <div className="chart-empty">暂无成交量明细。</div>
        )}
      </section>
    </div>
  );
}
