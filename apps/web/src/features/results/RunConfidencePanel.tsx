import type { BacktestResponse } from "../../api";

type ConfidenceDrawer = "job" | "history" | "lineage" | "trade";

type RunConfidencePanelProps = {
  result: BacktestResponse;
  onOpenConfig?: () => void;
  onOpenInspector?: (drawer: ConfidenceDrawer) => void;
};

export function RunConfidencePanel({
  result,
  onOpenConfig,
  onOpenInspector
}: RunConfidencePanelProps) {
  const coverage = result.dataSource.coverage;
  const coverageStatus = coverage?.status ?? "unknown";
  const actualProvider = result.dataSource.actualProvider ?? result.dataSource.provider;
  const requestedProvider = result.dataSource.requestedProvider ?? "auto";
  const fallbackCount = result.dataSource.fallbackChain?.length ?? 0;
  const missingCount = coverage?.missingDates.length ?? 0;
  const dataVersion = result.dataSource.dataVersion ?? "unknown";
  const engineVersion = result.dataSource.engineVersion ?? "signal-close-v1";

  return (
    <aside className={`run-confidence-panel ${coverageStatus}`} data-testid="run-confidence-panel">
      <div className="confidence-header">
        <div>
          <span>可信度</span>
          <strong>{confidenceLabel(coverageStatus, missingCount)}</strong>
        </div>
        <em>{result.dataSource.cached ? "缓存命中" : "新数据"}</em>
      </div>

      <dl className="confidence-grid">
        <div>
          <dt>实际来源</dt>
          <dd>{actualProvider}</dd>
        </div>
        <div>
          <dt>请求来源</dt>
          <dd>{requestedProvider}</dd>
        </div>
        <div>
          <dt>复权</dt>
          <dd>{result.dataSource.adjust || "不复权"}</dd>
        </div>
        <div>
          <dt>数据版本</dt>
          <dd title={dataVersion}>{dataVersion}</dd>
        </div>
        <div>
          <dt>K线数量</dt>
          <dd>{coverage?.actualRows ?? result.bars.length}</dd>
        </div>
        <div>
          <dt>缺失日期</dt>
          <dd className={missingCount > 0 ? "risk-text" : undefined}>{missingCount}</dd>
        </div>
        <div>
          <dt>引擎</dt>
          <dd title={engineVersion}>{engineVersion}</dd>
        </div>
        <div>
          <dt>回退链</dt>
          <dd>{fallbackCount}</dd>
        </div>
      </dl>

      <div className="confidence-actions" aria-label="可信度操作">
        <button type="button" onClick={onOpenConfig}>参数</button>
        <button type="button" onClick={() => onOpenInspector?.("lineage")}>血缘</button>
        <button type="button" onClick={() => onOpenInspector?.("job")}>任务</button>
      </div>
    </aside>
  );
}

function confidenceLabel(status: string, missingCount: number): string {
  if (status === "complete" && missingCount === 0) {
    return "数据完整";
  }
  if (status === "missing" || missingCount > 0) {
    return "存在缺口";
  }
  return "待确认";
}
