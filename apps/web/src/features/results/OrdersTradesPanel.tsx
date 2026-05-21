import type { BacktestResponse } from "../../api";
import { formatMoney, formatNumber } from "../../format";

export function OrdersTradesPanel({ result }: { result: BacktestResponse }) {
  if (result.trades.length === 0) {
    return (
      <section className="panel">
        <div className="panel-title">交易记录</div>
        <div className="table-empty">当前参数未产生交易信号</div>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="panel-title">交易记录</div>
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
            {result.trades.map((trade, index) => (
              <tr key={`${trade.datetime}-${trade.side}-${index}`}>
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
    </section>
  );
}
