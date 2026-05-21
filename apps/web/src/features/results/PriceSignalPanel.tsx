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
        <div className="panel-title">K线、策略指标与买卖点</div>
        {candlestickOption ? <EChart option={candlestickOption} className="chart chart-large" /> : null}
      </section>
      <section className="panel">
        <div className="panel-title">成交量</div>
        {volumeOption ? <EChart option={volumeOption} className="chart chart-small" /> : null}
      </section>
    </div>
  );
}
