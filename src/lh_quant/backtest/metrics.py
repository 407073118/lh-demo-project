"""回测指标计算工具，统一生成风险、交易质量和资金使用指标。"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def calculate_backtest_metrics(
    equity_curve: pd.DataFrame,
    trades: pd.DataFrame,
    starting_cash: float,
) -> dict[str, float | int | None]:
    """计算收益、风险、交易质量、仓位暴露和换手率指标。"""

    if equity_curve.empty:
        raise ValueError("equity_curve must not be empty")
    if starting_cash <= 0:
        raise ValueError("starting_cash must be positive")

    equity = equity_curve["equity"].astype(float)
    if not np.isfinite(equity).all():
        raise ValueError("equity_curve equity must contain finite values")
    final_equity = float(equity.iloc[-1])
    total_return = final_equity / float(starting_cash) - 1.0
    running_peak = equity.cummax()
    drawdown = equity / running_peak - 1.0
    max_drawdown = float(drawdown.min())
    daily_returns = equity.pct_change().dropna()

    return {
        "starting_cash": float(starting_cash),
        "final_equity": final_equity,
        "total_return": round(float(total_return), 6),
        "max_drawdown": round(max_drawdown, 6),
        "trade_count": len(trades),
        **_risk_metrics(
            total_return=total_return,
            max_drawdown=max_drawdown,
            equity_count=len(equity),
            daily_returns=daily_returns,
        ),
        **_trade_quality_metrics(trades),
        **_exposure_metrics(equity_curve),
        **_turnover_metrics(trades, equity),
    }


def _risk_metrics(
    total_return: float,
    max_drawdown: float,
    equity_count: int,
    daily_returns: pd.Series,
) -> dict[str, float | None]:
    """根据权益收益序列计算年化、波动、夏普、Sortino 和 Calmar。"""

    if equity_count < 2:
        return {
            "annualized_return": None,
            "annualized_volatility": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "calmar_ratio": None,
        }

    return_periods = equity_count - 1
    annualized_return = (1.0 + total_return) ** (
        TRADING_DAYS_PER_YEAR / return_periods
    ) - 1.0
    daily_std = float(daily_returns.std(ddof=0))
    annualized_volatility = daily_std * float(np.sqrt(TRADING_DAYS_PER_YEAR))
    sharpe_ratio = (
        None
        if daily_std == 0
        else float(daily_returns.mean() / daily_std * np.sqrt(TRADING_DAYS_PER_YEAR))
    )

    downside = daily_returns.clip(upper=0)
    downside_deviation = (
        float(np.sqrt(np.mean(np.square(downside))) * np.sqrt(TRADING_DAYS_PER_YEAR))
        if not downside.empty
        else 0.0
    )
    sortino_ratio = (
        None
        if downside_deviation == 0
        else float(annualized_return / downside_deviation)
    )
    calmar_ratio = None if max_drawdown == 0 else float(annualized_return / abs(max_drawdown))

    return {
        "annualized_return": round(float(annualized_return), 6),
        "annualized_volatility": round(float(annualized_volatility), 6),
        "sharpe_ratio": _round_optional(sharpe_ratio),
        "sortino_ratio": _round_optional(sortino_ratio),
        "calmar_ratio": _round_optional(calmar_ratio),
    }


def _trade_quality_metrics(trades: pd.DataFrame) -> dict[str, float | int | None]:
    """根据成交记录计算闭合交易、胜率、盈亏比、期望和佣金。"""

    total_commission = _sum_column(trades, "commission")
    if trades.empty:
        return {
            "closed_trade_count": 0,
            "win_rate": None,
            "profit_factor": None,
            "expectancy": None,
            "average_win": None,
            "average_loss": None,
            "total_commission": 0.0,
        }

    round_trips = _round_trip_pnls(trades)
    if not round_trips:
        return {
            "closed_trade_count": 0,
            "win_rate": None,
            "profit_factor": None,
            "expectancy": None,
            "average_win": None,
            "average_loss": None,
            "total_commission": round(total_commission, 6),
        }

    wins = [pnl for pnl in round_trips if pnl > 0]
    losses = [pnl for pnl in round_trips if pnl < 0]
    gross_profit = float(sum(wins))
    gross_loss = abs(float(sum(losses)))

    if gross_loss == 0 and gross_profit > 0:
        profit_factor: float | None = None
    elif gross_loss == 0:
        profit_factor = 0.0
    else:
        profit_factor = round(gross_profit / gross_loss, 6)

    return {
        "closed_trade_count": len(round_trips),
        "win_rate": round(len(wins) / len(round_trips), 6),
        "profit_factor": profit_factor,
        "expectancy": round(float(np.mean(round_trips)), 6),
        "average_win": round(float(np.mean(wins)), 6) if wins else None,
        "average_loss": round(float(np.mean(losses)), 6) if losses else None,
        "total_commission": round(total_commission, 6),
    }


def _round_trip_pnls(trades: pd.DataFrame) -> list[float]:
    """按当前单标的全仓模型把买入和卖出配对为单笔往返盈亏。"""

    pnls: list[float] = []
    open_lot: dict[str, float] | None = None
    for row in trades.itertuples(index=False):
        side = str(row.side).lower()
        price = float(row.price)
        quantity = float(row.quantity)
        commission = float(row.commission)

        if side == "buy" and open_lot is None:
            open_lot = {
                "price": price,
                "quantity": quantity,
                "commission": commission,
            }
        elif side == "sell" and open_lot is not None:
            quantity_used = min(quantity, open_lot["quantity"])
            pnl = (
                (price - open_lot["price"]) * quantity_used
                - open_lot["commission"]
                - commission
            )
            pnls.append(round(float(pnl), 6))
            open_lot = None

    return pnls


def _exposure_metrics(equity_curve: pd.DataFrame) -> dict[str, float | None]:
    """根据持仓市值占权益比例计算暴露天数和仓位权重。"""

    required_columns = {"position", "price", "equity"}
    if equity_curve.empty or not required_columns <= set(equity_curve.columns):
        return {
            "exposure": None,
            "average_position_weight": None,
            "max_position_weight": None,
        }

    market_value = (
        equity_curve["position"].astype(float) * equity_curve["price"].astype(float)
    )
    equity = equity_curve["equity"].astype(float).replace(0, np.nan)
    weights = (market_value / equity).fillna(0)

    return {
        "exposure": round(float((weights.abs() > 0).mean()), 6),
        "average_position_weight": round(float(weights.abs().mean()), 6),
        "max_position_weight": round(float(weights.abs().max()), 6),
    }


def _turnover_metrics(
    trades: pd.DataFrame,
    equity: pd.Series,
) -> dict[str, float | None]:
    """按成交额除以平均权益估算单次回测区间换手。"""

    if trades.empty:
        return {"turnover": 0.0}

    amounts = trades["price"].astype(float) * trades["quantity"].astype(float)
    average_equity = float(equity.mean())
    return {
        "turnover": None
        if average_equity == 0
        else round(float(amounts.sum() / average_equity), 6)
    }


def _sum_column(frame: pd.DataFrame, column: str) -> float:
    """安全汇总可选数值列，列不存在时返回零。"""

    if column not in frame:
        return 0.0
    return float(frame[column].sum())


def _round_optional(value: Any) -> float | None:
    """把可选浮点数四舍五入，并把非有限值转换为空值。"""

    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return round(float(value), 6)
