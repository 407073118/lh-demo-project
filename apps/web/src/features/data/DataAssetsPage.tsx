import type { DataAsset, DataAssetDetailResponse, DatabaseStatus } from "../../api";

export function DataAssetsPage({
  assets,
  selectedAsset,
  databaseStatus,
  onSelectAsset,
  onRetry
}: {
  assets: DataAsset[];
  selectedAsset: DataAssetDetailResponse["asset"] | null;
  databaseStatus: DatabaseStatus | null;
  onSelectAsset: (assetId: string) => void;
  onRetry: () => void;
}) {
  if (databaseStatus && !databaseStatus.connected) {
    return (
      <main className="workspace-page data-assets-page" data-testid="data-assets-page">
        <section className="database-empty-state">
          <h1>数据底座未连接</h1>
          <p>{databaseStatus.message}</p>
          <div className="empty-actions">
            <button type="button">配置数据库</button>
            <button type="button">使用示例数据</button>
            <button type="button" onClick={onRetry}>重试连接</button>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="workspace-page data-assets-page" data-testid="data-assets-page">
      <section className="workspace-page-header">
        <div>
          <span>Data</span>
          <h1>数据资产</h1>
        </div>
        <button type="button" onClick={onRetry}>刷新</button>
      </section>
      <section className="asset-table-shell">
        <div className="asset-table-header">
          <span>资产</span>
          <span>Provider</span>
          <span>覆盖</span>
          <span>质量</span>
          <span>行数</span>
        </div>
        {assets.map((asset) => (
          <button
            className="asset-row"
            key={asset.id}
            type="button"
            onClick={() => onSelectAsset(asset.id)}
          >
            <strong>{asset.name}</strong>
            <span>{asset.provider}</span>
            <span>{asset.coverage}</span>
            <span>{qualityText(asset)}</span>
            <span>{asset.rowCount.toLocaleString("zh-CN")}</span>
          </button>
        ))}
      </section>
      {selectedAsset ? (
        <section className="asset-detail-panel">
          <div>
            <span>字段</span>
            <strong>{selectedAsset.fields.join(" / ")}</strong>
          </div>
          <div>
            <span>最近同步</span>
            <strong>{selectedAsset.lastSync ?? "暂无"}</strong>
          </div>
          <p>{selectedAsset.description}</p>
          <div className="sync-job-list">
            {selectedAsset.syncJobs.length === 0 ? (
              <span>暂无同步任务</span>
            ) : (
              selectedAsset.syncJobs.map((job) => (
                <span key={job.jobId}>{job.provider} · {job.status} · {Math.round(job.progress * 100)}%</span>
              ))
            )}
          </div>
        </section>
      ) : null}
    </main>
  );
}

function qualityText(asset: DataAsset): string {
  const score = asset.quality.score == null ? "--" : `${Math.round(asset.quality.score * 100)}%`;
  return `${asset.quality.status} ${score}`;
}
