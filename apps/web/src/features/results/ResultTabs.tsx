import { useState } from "react";
import type { ReactNode } from "react";

export type ResultTabId = "overview" | "risk" | "price" | "orders" | "lineage";

const RESULT_TABS: Array<{ id: ResultTabId; label: string }> = [
  { id: "overview", label: "概览" },
  { id: "risk", label: "收益/风险" },
  { id: "price", label: "价格/信号" },
  { id: "orders", label: "订单/成交" },
  { id: "lineage", label: "数据血缘" }
];

export function ResultTabs({ panels }: { panels: Record<ResultTabId, ReactNode> }) {
  const [activeTab, setActiveTab] = useState<ResultTabId>("overview");

  return (
    <section className="result-workbench">
      <div className="result-tab-bar" role="tablist" aria-label="回测结果">
        {RESULT_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            className={activeTab === tab.id ? "result-tab active" : "result-tab"}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="result-tab-panel" role="tabpanel">
        {panels[activeTab]}
      </div>
    </section>
  );
}
