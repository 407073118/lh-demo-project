import { useEffect, useRef, useState } from "react";
import type { EChartsCoreOption, EChartsType } from "echarts/core";

type EChartProps = {
  option: EChartsCoreOption;
  className?: string;
  ariaLabel: string;
  fallback?: string;
};

let echartsLoad: Promise<typeof import("echarts/core")> | null = null;

async function loadECharts() {
  if (!echartsLoad) {
    echartsLoad = (async () => {
      const echarts = await import("echarts/core");
      const [charts, components, renderers] = await Promise.all([
        import("echarts/charts"),
        import("echarts/components"),
        import("echarts/renderers")
      ]);
      echarts.use([
        charts.BarChart,
        charts.CandlestickChart,
        charts.LineChart,
        charts.ScatterChart,
        components.AriaComponent,
        components.DataZoomComponent,
        components.GridComponent,
        components.LegendComponent,
        components.TooltipComponent,
        renderers.CanvasRenderer
      ]);
      return echarts;
    })();
  }
  return echartsLoad;
}

export function EChart({ option, className, ariaLabel, fallback }: EChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<EChartsType | null>(null);
  const optionRef = useRef(option);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    optionRef.current = option;
    chartRef.current?.setOption(option, true);
  }, [option]);

  useEffect(() => {
    let isDisposed = false;
    let resizeObserver: ResizeObserver | null = null;

    async function mountChart() {
      if (!containerRef.current) {
        return;
      }
      const echarts = await loadECharts();
      if (isDisposed || !containerRef.current) {
        return;
      }
      chartRef.current = echarts.init(containerRef.current);
      chartRef.current.setOption(optionRef.current, true);
      resizeObserver = new ResizeObserver(() => {
        chartRef.current?.resize();
      });
      resizeObserver.observe(containerRef.current);
      setIsLoading(false);
    }

    void mountChart();

    return () => {
      isDisposed = true;
      resizeObserver?.disconnect();
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  return (
    <figure className="chart-figure">
      <div
        ref={containerRef}
        aria-busy={isLoading}
        aria-label={ariaLabel}
        className={className}
        role="img"
      />
      <figcaption className="sr-only">{fallback ?? ariaLabel}</figcaption>
    </figure>
  );
}
