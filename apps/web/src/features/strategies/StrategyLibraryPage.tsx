import { useMemo, useState } from "react";
import type { FactorDefinition, StrategyDefinition } from "../../api";

export function StrategyLibraryPage({
  strategies,
  factors,
  selectedStrategyId,
  onSelectStrategy
}: {
  strategies: StrategyDefinition[];
  factors: FactorDefinition[];
  selectedStrategyId: string;
  onSelectStrategy: (strategyId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const categories = useMemo(
    () => ["all", ...Array.from(new Set(strategies.map((strategy) => strategy.category)))],
    [strategies]
  );
  const filtered = strategies.filter((strategy) => {
    const haystack = [
      strategy.name,
      strategy.description,
      strategy.category,
      ...(strategy.tags ?? [])
    ].join(" ").toLowerCase();
    return (
      (category === "all" || strategy.category === category) &&
      haystack.includes(query.trim().toLowerCase())
    );
  });

  return (
    <main className="workspace-page strategy-library-page" data-testid="strategy-library-page">
      <section className="workspace-page-header">
        <div>
          <span>Research</span>
          <h1>策略库</h1>
        </div>
        <strong>{factors.length} 个本地因子可用</strong>
      </section>
      <section className="library-controls">
        <label>
          搜索策略
          <input value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
        <label>
          分类
          <select value={category} onChange={(event) => setCategory(event.target.value)}>
            {categories.map((item) => (
              <option value={item} key={item}>{item === "all" ? "全部" : item}</option>
            ))}
          </select>
        </label>
      </section>
      <section className="strategy-library-grid">
        {filtered.map((strategy) => (
          <article className="strategy-library-item" key={strategy.id}>
            <div>
              <span>{strategy.category}</span>
              <h2>{strategy.name}</h2>
            </div>
            <p>{strategy.description}</p>
            <dl>
              <div><dt>版本</dt><dd>{strategy.version ?? "1.0.0"}</dd></div>
              <div><dt>来源</dt><dd>{strategy.source?.name ?? strategy.source?.type ?? "built-in"}</dd></div>
              <div><dt>许可</dt><dd>{strategy.license ?? "internal"}</dd></div>
              <div><dt>风险</dt><dd>{strategy.riskLevel ?? "medium"}</dd></div>
            </dl>
            <div className="strategy-tags">
              {(strategy.tags ?? ["内置"]).map((tag) => <span key={tag}>{tag}</span>)}
            </div>
            <button
              type="button"
              className={strategy.id === selectedStrategyId ? "selected" : ""}
              onClick={() => onSelectStrategy(strategy.id)}
            >
              {strategy.id === selectedStrategyId ? "当前策略" : "选择策略"}
            </button>
          </article>
        ))}
      </section>
    </main>
  );
}
