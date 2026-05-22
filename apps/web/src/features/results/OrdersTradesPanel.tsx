import { useMemo, useState } from "react";
import type { BacktestResponse, TradeRecord } from "../../api";
import { formatMoney, formatNumber } from "../../format";
import { Panel, PanelTitle } from "./uiPrimitives";

const PAGE_SIZE = 12;
type TradeFilter = "all" | "buy" | "sell";

const FILTERS: Array<{ id: TradeFilter; label: string }> = [
  { id: "all", label: "全部" },
  { id: "buy", label: "买入" },
  { id: "sell", label: "卖出" }
];

export function OrdersTradesPanel({ result }: { result: BacktestResponse }) {
  const [tradeFilter, setTradeFilter] = useState<TradeFilter>("all");
  const [page, setPage] = useState(1);
  const filteredTrades = useMemo(
    () => result.trades.filter((trade) => tradeFilter === "all" || trade.side === tradeFilter),
    [result.trades, tradeFilter]
  );
  const totalPages = Math.max(1, Math.ceil(filteredTrades.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const visibleTrades = filteredTrades.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  function updateTradeFilter(nextFilter: TradeFilter) {
    setTradeFilter(nextFilter);
    setPage(1);
  }

  if (result.trades.length === 0) {
    return (
      <Panel>
        <PanelTitle>交易记录</PanelTitle>
        <div className="table-empty">当前参数未产生交易信号</div>
      </Panel>
    );
  }

  return (
    <Panel>
      <div className="panel-heading-row">
        <PanelTitle>交易记录</PanelTitle>
        <div className="table-actions">
          <div className="segmented-control" data-testid="trade-filter" aria-label="交易方向过滤">
            {FILTERS.map((filter) => (
              <button
                aria-pressed={tradeFilter === filter.id}
                className={tradeFilter === filter.id ? "trade-filter active" : "trade-filter"}
                key={filter.id}
                onClick={() => updateTradeFilter(filter.id)}
                type="button"
              >
                {filter.label}
              </button>
            ))}
          </div>
          <button
            className="secondary-button"
            onClick={() => exportTradesToCsv(filteredTrades, result.runId ?? result.symbol)}
            type="button"
          >
            导出 CSV
          </button>
        </div>
      </div>
      {filteredTrades.length === 0 ? (
        <div className="table-empty">当前方向没有交易记录</div>
      ) : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>日期</th>
                  <th>方向</th>
                  <th>成交价</th>
                  <th>数量</th>
                  <th>成交金额</th>
                  <th>手续费</th>
                </tr>
              </thead>
              <tbody>
                {visibleTrades.map((trade, index) => (
                  <tr key={`${trade.datetime}-${trade.side}-${safePage}-${index}`}>
                    <td>{trade.datetime}</td>
                    <td className={trade.side === "buy" ? "up-text" : "down-text"}>{trade.sideText}</td>
                    <td>{formatNumber(trade.price)}</td>
                    <td>{formatNumber(trade.quantity, 4)}</td>
                    <td>{formatMoney(trade.amount)}</td>
                    <td>{formatMoney(trade.commission)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-footer">
            <span>
              {filteredTrades.length} 笔交易，显示 {(safePage - 1) * PAGE_SIZE + 1}-
              {Math.min(safePage * PAGE_SIZE, filteredTrades.length)}
            </span>
            <div className="pager" aria-label="交易记录分页">
              <button disabled={safePage <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))} type="button">
                上一页
              </button>
              <span>{safePage} / {totalPages}</span>
              <button
                disabled={safePage >= totalPages}
                onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                type="button"
              >
                下一页
              </button>
            </div>
          </div>
        </>
      )}
    </Panel>
  );
}

function exportTradesToCsv(trades: TradeRecord[], name: string) {
  if (typeof document === "undefined" || trades.length === 0) {
    return;
  }
  const header = ["日期", "方向", "成交价", "数量", "成交金额", "手续费"];
  const rows = trades.map((trade) => [
    trade.datetime,
    trade.sideText,
    trade.price,
    trade.quantity,
    trade.amount,
    trade.commission
  ]);
  const csv = [header, ...rows]
    .map((row) => row.map((cell) => escapeCsvCell(String(cell))).join(","))
    .join("\n");
  const blob = new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${name}-trades.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function escapeCsvCell(value: string) {
  return /[",\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}
