"""Backtesting & Strategy Lab: fees, spread, slippage, funding, walk-forward OOS, and Monte Carlo."""

from __future__ import annotations

import math
import uuid
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from app.core.enums import StrategyType


class BacktestingEngine:
    """
    Event-driven historical simulator modeling transaction fees, spread, slippage,
    funding costs, walk-forward out-of-sample split, and Monte Carlo drawdown bands.
    """

    DISCLAIMER = (
        "Simulated historical backtest results do not guarantee future performance. "
        "Always evaluate out-of-sample metrics and parameter stability."
    )

    def run_backtest(
        self,
        df: pd.DataFrame,
        *,
        symbol: str,
        timeframe: str,
        strategy: StrategyType,
        initial_capital: float = 100000.0,
        risk_per_trade_pct: float = 0.5,
        fee_bps: float = 6.0,
        spread_bps: float = 4.0,
        slippage_bps: float = 3.0,
        funding_bps_per_8h: float = 1.0,
        run_monte_carlo: bool = True,
        monte_carlo_runs: int = 200,
    ) -> Dict[str, Any]:
        if df.empty or len(df) < 80:
            raise ValueError("At least 80 historical candles are required for backtesting.")

        data = df.copy().reset_index(drop=True)
        close = data["close"].astype(float)
        high = data["high"].astype(float)
        low = data["low"].astype(float)

        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        delta = close.diff()
        gain = delta.clip(lower=0.0).ewm(alpha=1 / 14, adjust=False).mean()
        loss = (-delta.clip(upper=0.0)).ewm(alpha=1 / 14, adjust=False).mean()
        rsi = (100.0 - (100.0 / (1.0 + gain / loss.replace(0, np.nan)))).fillna(50.0)
        tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / 14, adjust=False).mean().bfill()

        equity = initial_capital
        peak_equity = initial_capital
        max_dd_pct = 0.0
        total_fees = 0.0
        trades: List[Dict[str, Any]] = []
        equity_curve: List[Dict[str, Any]] = []

        in_pos = False
        pos_side = ""
        entry_px = 0.0
        stop_px = 0.0
        tp_px = 0.0
        qty = 0.0
        entry_bar = 0
        cost_bps_one_way = (fee_bps + spread_bps / 2.0 + slippage_bps) / 10000.0

        # Chronological 70% in-sample / 30% out-of-sample split
        oos_start_idx = int(len(data) * 0.7)

        for i in range(30, len(data)):
            c = float(close.iloc[i])
            h = float(high.iloc[i])
            lo = float(low.iloc[i])
            a = max(float(atr.iloc[i]), c * 0.002)
            ts = str(data["timestamp"].iloc[i])

            if in_pos:
                exit_reason = None
                exit_px = c
                if pos_side == "BUY":
                    if lo <= stop_px:
                        exit_px = stop_px * (1.0 - slippage_bps / 10000.0)
                        exit_reason = "STOP_LOSS"
                    elif h >= tp_px:
                        exit_px = tp_px
                        exit_reason = "TAKE_PROFIT"
                else:
                    if h >= stop_px:
                        exit_px = stop_px * (1.0 + slippage_bps / 10000.0)
                        exit_reason = "STOP_LOSS"
                    elif lo <= tp_px:
                        exit_px = tp_px
                        exit_reason = "TAKE_PROFIT"

                if exit_reason or i == len(data) - 1:
                    bars_held = max(1, i - entry_bar)
                    gross = (exit_px - entry_px) * qty if pos_side == "BUY" else (entry_px - exit_px) * qty
                    exit_fee = exit_px * qty * cost_bps_one_way
                    funding_cost = exit_px * qty * (funding_bps_per_8h / 10000.0) * (bars_held / 8.0)
                    entry_fee = entry_px * qty * cost_bps_one_way
                    fees = entry_fee + exit_fee + funding_cost
                    net = gross - fees
                    equity += net
                    total_fees += fees
                    trades.append(
                        {
                            "entry_bar": entry_bar,
                            "exit_bar": i,
                            "side": pos_side,
                            "entry_price": round(entry_px, 5),
                            "exit_price": round(exit_px, 5),
                            "quantity": round(qty, 6),
                            "gross_pnl": round(gross, 2),
                            "fees": round(fees, 2),
                            "net_pnl": round(net, 2),
                            "exit_reason": exit_reason or "END_OF_SERIES",
                            "is_out_of_sample": bool(entry_bar >= oos_start_idx),
                        }
                    )
                    in_pos = False
            else:
                signal_side = None
                if strategy in (StrategyType.TREND_FOLLOWING, StrategyType.MOMENTUM, StrategyType.MARKET_STRUCTURE):
                    if float(ema_fast.iloc[i]) > float(ema_slow.iloc[i]) and float(rsi.iloc[i]) > 52:
                        signal_side = "BUY"
                    elif float(ema_fast.iloc[i]) < float(ema_slow.iloc[i]) and float(rsi.iloc[i]) < 48:
                        signal_side = "SELL"
                elif strategy == StrategyType.MEAN_REVERSION:
                    if float(rsi.iloc[i]) < 32:
                        signal_side = "BUY"
                    elif float(rsi.iloc[i]) > 68:
                        signal_side = "SELL"
                elif strategy in (StrategyType.BREAKOUT, StrategyType.VOLATILITY):
                    prev_hi = float(high.iloc[i - 20 : i].max())
                    prev_lo = float(low.iloc[i - 20 : i].min())
                    if c > prev_hi:
                        signal_side = "BUY"
                    elif c < prev_lo:
                        signal_side = "SELL"
                elif strategy == StrategyType.PULLBACK:
                    if float(ema_fast.iloc[i]) > float(ema_slow.iloc[i]) and 42 <= float(rsi.iloc[i]) <= 50:
                        signal_side = "BUY"
                    elif float(ema_fast.iloc[i]) < float(ema_slow.iloc[i]) and 50 <= float(rsi.iloc[i]) <= 58:
                        signal_side = "SELL"

                if signal_side:
                    in_pos = True
                    pos_side = signal_side
                    entry_bar = i
                    entry_px = c * (1.0 + cost_bps_one_way) if pos_side == "BUY" else c * (1.0 - cost_bps_one_way)
                    stop_dist = 1.5 * a
                    stop_px = entry_px - stop_dist if pos_side == "BUY" else entry_px + stop_dist
                    tp_px = entry_px + 2.5 * a if pos_side == "BUY" else entry_px - 2.5 * a
                    risk_amt = equity * (risk_per_trade_pct / 100.0)
                    qty = min(risk_amt / max(stop_dist, 1e-8), (equity * 0.25) / entry_px)

            peak_equity = max(peak_equity, equity)
            dd_pct = ((peak_equity - equity) / peak_equity) * 100.0 if peak_equity > 0 else 0.0
            max_dd_pct = max(max_dd_pct, dd_pct)
            equity_curve.append({"timestamp": ts, "equity": round(equity, 2), "drawdown_pct": round(dd_pct, 2)})

        # Performance statistics
        pnls = np.array([t["net_pnl"] for t in trades], dtype=float) if trades else np.array([0.0])
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        gross_profit = float(wins.sum()) if len(wins) else 0.0
        gross_loss = float(abs(losses.sum())) if len(losses) else 0.0
        net_profit = float(equity - initial_capital)
        total_trades = len(trades)
        win_rate = (len(wins) / total_trades) if total_trades > 0 else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
        avg_win = float(wins.mean()) if len(wins) else 0.0
        avg_loss = float(abs(losses.mean())) if len(losses) else 0.0
        realized_rr = (avg_win / avg_loss) if avg_loss > 0 else 0.0

        # Sharpe & Sortino on trade returns
        trade_rets = pnls / initial_capital
        std_all = float(np.std(trade_rets)) if len(trade_rets) > 1 else 0.0
        downside = trade_rets[trade_rets < 0]
        std_down = float(np.std(downside)) if len(downside) > 1 else 0.0
        sharpe = (float(np.mean(trade_rets)) / std_all) * math.sqrt(max(total_trades, 1)) if std_all > 0 else 0.0
        sortino = (float(np.mean(trade_rets)) / std_down) * math.sqrt(max(total_trades, 1)) if std_down > 0 else 0.0

        # Out-of-sample walk-forward summary
        oos_trades = [t for t in trades if t["is_out_of_sample"]]
        oos_net = sum(t["net_pnl"] for t in oos_trades)
        oos_win_rate = (
            sum(1 for t in oos_trades if t["net_pnl"] > 0) / len(oos_trades) if oos_trades else 0.0
        )

        # Monte Carlo bootstrap of trade sequence
        mc_summary: Dict[str, Any] = {}
        if run_monte_carlo and total_trades >= 3:
            rng = np.random.default_rng(42)
            final_equities: List[float] = []
            mc_drawdowns: List[float] = []
            for _ in range(monte_carlo_runs):
                sampled = rng.choice(pnls, size=total_trades, replace=True)
                curve = initial_capital + np.cumsum(sampled)
                peaks = np.maximum.accumulate(np.insert(curve, 0, initial_capital))[1:]
                dds = ((peaks - curve) / np.maximum(peaks, 1e-8)) * 100.0
                final_equities.append(float(curve[-1]))
                mc_drawdowns.append(float(np.max(dds)))
            mc_summary = {
                "runs": monte_carlo_runs,
                "median_final_equity": round(float(np.median(final_equities)), 2),
                "p5_final_equity": round(float(np.percentile(final_equities, 5)), 2),
                "p95_final_equity": round(float(np.percentile(final_equities, 95)), 2),
                "p95_max_drawdown_pct": round(float(np.percentile(mc_drawdowns, 95)), 2),
            }

        metrics = {
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "strategy": strategy.value,
            "initial_capital": initial_capital,
            "final_equity": round(equity, 2),
            "net_profit": round(net_profit, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "win_rate": round(win_rate, 4),
            "profit_factor": round(profit_factor, 3),
            "average_win": round(avg_win, 2),
            "average_loss": round(avg_loss, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "total_trades": total_trades,
            "risk_reward_ratio": round(realized_rr, 3),
            "trading_fees": round(total_fees, 2),
            "walk_forward_oos": {
                "oos_trades": len(oos_trades),
                "oos_net_profit": round(oos_net, 2),
                "oos_win_rate": round(oos_win_rate, 4),
            },
            "monte_carlo": mc_summary,
            "disclaimer": self.DISCLAIMER,
        }

        return {
            "run_id": str(uuid.uuid4()),
            "metrics": metrics,
            "equity_curve": equity_curve,
            "trades": trades[-100:],
        }
