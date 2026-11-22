"""Backend-enforced Risk Management Engine. Risk always precedes execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.config import RiskConfig


@dataclass
class RiskEvaluation:
    approved: bool
    reasons: List[str] = field(default_factory=list)
    recommended_quantity: float = 0.0
    estimated_max_loss: float = 0.0
    risk_reward_ratio: float = 0.0
    circuit_breaker_triggered: bool = False


class RiskManagementEngine:
    """Enforces position sizing, drawdown, daily/weekly loss, exposure, spread, and correlation caps."""

    # Deterministic correlation clusters to prevent hidden concentrated exposure
    CORRELATION_GROUPS: Dict[str, str] = {
        "BTCUSDT": "CRYPTO_MAJOR",
        "ETHUSDT": "CRYPTO_MAJOR",
        "SOLUSDT": "CRYPTO_MAJOR",
        "EURUSD": "USD_FX",
        "GBPUSD": "USD_FX",
        "AUDUSD": "USD_FX",
        "USDJPY": "USD_FX",
        "XAUUSD": "PRECIOUS_METALS",
        "XAGUSD": "PRECIOUS_METALS",
        "US500": "US_EQUITY_INDEX",
        "US100": "US_EQUITY_INDEX",
    }

    def __init__(self) -> None:
        self._peak_equity: Dict[str, float] = {}

    def update_peak_equity(self, mode: str, equity: float) -> float:
        if mode not in self._peak_equity or equity > self._peak_equity[mode]:
            self._peak_equity[mode] = equity
        return self._peak_equity[mode]

    def calculate_position_size(
        self,
        equity: float,
        entry_price: float,
        stop_loss: float,
        risk_cfg: RiskConfig,
        atr: Optional[float] = None,
        consecutive_losses: int = 0,
    ) -> float:
        """
        Calculate volatility-adjusted position size capped strictly by max equity risk per trade.
        Never increases size after losses (anti-martingale / flat-or-reduced sizing only).
        """
        if equity <= 0 or entry_price <= 0:
            return 0.0
        stop_distance = abs(entry_price - stop_loss)
        if stop_distance <= 0:
            return 0.0

        risk_amount = equity * (risk_cfg.max_risk_per_trade_pct / 100.0)
        base_qty = risk_amount / stop_distance

        # Volatility dampening if ATR is unusually wide relative to entry price (>3%)
        if atr and atr > 0:
            atr_pct = (atr / entry_price) * 100.0
            if atr_pct > 3.0:
                base_qty *= 3.0 / atr_pct

        # Cap notional by max leverage, portfolio exposure, and correlated exposure (with floor safety margin)
        max_notional = equity * min(
            risk_cfg.max_leverage,
            risk_cfg.max_portfolio_exposure_pct / 100.0,
            risk_cfg.max_correlated_exposure_pct / 100.0,
        ) * 0.999
        capped_qty = min(base_qty, max_notional / entry_price)

        # Strictly reduce size during losing streaks (never martingale / never increase after losses)
        if consecutive_losses > 0:
            capped_qty *= max(0.2, 0.75 ** consecutive_losses)

        return round(max(0.0, capped_qty), 6)

    def evaluate_trade(
        self,
        *,
        trading_mode: str,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        quantity: Optional[float],
        equity: float,
        available_margin: float,
        used_margin: float,
        daily_pnl: float,
        weekly_pnl: float,
        open_positions: List[Dict[str, Any]],
        spread_bps: float,
        estimated_slippage_bps: float,
        requested_leverage: float,
        consecutive_losses: int,
        risk_cfg: RiskConfig,
        atr: Optional[float] = None,
    ) -> RiskEvaluation:
        reasons: List[str] = []
        circuit_breaker = False

        # 1. Prohibitions
        if risk_cfg.allow_martingale or risk_cfg.allow_loss_doubling or risk_cfg.allow_uncontrolled_grid:
            reasons.append("Prohibited high-risk sizing method enabled.")

        # 2. Validate prices and stop-loss / take-profit geometry
        if entry_price <= 0 or stop_loss <= 0 or take_profit <= 0:
            reasons.append("Entry price, stop loss, and take profit must be positive.")
            return RiskEvaluation(approved=False, reasons=reasons)

        if side == "BUY":
            if stop_loss >= entry_price:
                reasons.append("BUY stop loss must be strictly below entry price.")
            if take_profit <= entry_price:
                reasons.append("BUY take profit must be strictly above entry price.")
        elif side == "SELL":
            if stop_loss <= entry_price:
                reasons.append("SELL stop loss must be strictly above entry price.")
            if take_profit >= entry_price:
                reasons.append("SELL take profit must be strictly below entry price.")

        risk_per_unit = abs(entry_price - stop_loss)
        reward_per_unit = abs(take_profit - entry_price)
        rr = round(reward_per_unit / risk_per_unit, 3) if risk_per_unit > 0 else 0.0
        if rr < risk_cfg.min_risk_reward_ratio:
            reasons.append(
                f"Risk/reward ratio {rr:.2f} is below minimum {risk_cfg.min_risk_reward_ratio:.2f}."
            )

        # 3. Equity & Circuit Breakers
        if equity <= 0:
            reasons.append("Account equity is zero or negative.")
            return RiskEvaluation(approved=False, reasons=reasons, circuit_breaker_triggered=True)

        daily_loss_pct = (-daily_pnl / equity) * 100.0 if daily_pnl < 0 else 0.0
        if daily_loss_pct >= risk_cfg.daily_loss_limit_pct:
            reasons.append(
                f"Daily loss limit reached ({daily_loss_pct:.2f}% >= {risk_cfg.daily_loss_limit_pct:.2f}%)."
            )
            circuit_breaker = True

        weekly_loss_pct = (-weekly_pnl / equity) * 100.0 if weekly_pnl < 0 else 0.0
        if weekly_loss_pct >= risk_cfg.weekly_loss_limit_pct:
            reasons.append(
                f"Weekly loss limit reached ({weekly_loss_pct:.2f}% >= {risk_cfg.weekly_loss_limit_pct:.2f}%)."
            )
            circuit_breaker = True

        peak = self.update_peak_equity(trading_mode, equity)
        drawdown_pct = ((peak - equity) / peak) * 100.0 if peak > 0 else 0.0
        if drawdown_pct >= risk_cfg.max_drawdown_pct:
            reasons.append(
                f"Maximum account drawdown reached ({drawdown_pct:.2f}% >= {risk_cfg.max_drawdown_pct:.2f}%)."
            )
            circuit_breaker = True

        if consecutive_losses >= risk_cfg.consecutive_loss_limit:
            reasons.append(
                f"Consecutive-loss circuit breaker triggered ({consecutive_losses} >= {risk_cfg.consecutive_loss_limit})."
            )
            circuit_breaker = True

        # 4. Market execution quality limits
        if spread_bps > risk_cfg.max_spread_bps:
            reasons.append(
                f"Spread {spread_bps:.1f} bps exceeds maximum {risk_cfg.max_spread_bps:.1f} bps."
            )
        if estimated_slippage_bps > risk_cfg.max_slippage_bps:
            reasons.append(
                f"Estimated slippage {estimated_slippage_bps:.1f} bps exceeds maximum {risk_cfg.max_slippage_bps:.1f} bps."
            )
        if requested_leverage > risk_cfg.max_leverage:
            reasons.append(
                f"Requested leverage {requested_leverage:.1f}x exceeds maximum {risk_cfg.max_leverage:.1f}x."
            )

        # 5. Position count & sizing
        if len(open_positions) >= risk_cfg.max_open_positions:
            reasons.append(
                f"Maximum open positions reached ({len(open_positions)} >= {risk_cfg.max_open_positions})."
            )

        recommended_qty = self.calculate_position_size(
            equity=equity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            risk_cfg=risk_cfg,
            atr=atr,
            consecutive_losses=consecutive_losses,
        )
        effective_qty = quantity if (quantity is not None and quantity > 0) else recommended_qty
        if effective_qty <= 0:
            reasons.append("Computed order quantity is zero.")

        max_loss = effective_qty * risk_per_unit
        max_loss_pct = (max_loss / equity) * 100.0
        if max_loss_pct > risk_cfg.max_risk_per_trade_pct * 1.01:
            reasons.append(
                f"Trade risk {max_loss_pct:.2f}% exceeds max risk per trade {risk_cfg.max_risk_per_trade_pct:.2f}%."
            )

        # 6. Portfolio & correlated exposure + margin utilization
        new_notional = effective_qty * entry_price
        existing_notional = sum(abs(p["quantity"] * p["current_price"]) for p in open_positions)
        total_exposure_pct = ((existing_notional + new_notional) / equity) * 100.0
        if total_exposure_pct > risk_cfg.max_portfolio_exposure_pct:
            reasons.append(
                f"Total portfolio exposure {total_exposure_pct:.2f}% exceeds cap {risk_cfg.max_portfolio_exposure_pct:.2f}%."
            )

        group = self.CORRELATION_GROUPS.get(symbol.upper(), symbol.upper())
        correlated_notional = sum(
            abs(p["quantity"] * p["current_price"])
            for p in open_positions
            if self.CORRELATION_GROUPS.get(p["symbol"].upper(), p["symbol"].upper()) == group
        )
        correlated_exposure_pct = ((correlated_notional + new_notional) / equity) * 100.0
        if correlated_exposure_pct > risk_cfg.max_correlated_exposure_pct:
            reasons.append(
                f"Correlated exposure in {group} ({correlated_exposure_pct:.2f}%) exceeds cap {risk_cfg.max_correlated_exposure_pct:.2f}%."
            )

        required_margin = new_notional / max(requested_leverage, 1.0)
        if required_margin > available_margin:
            reasons.append(
                f"Insufficient available margin (required {required_margin:.2f}, available {available_margin:.2f})."
            )
        projected_margin_util = ((used_margin + required_margin) / equity) * 100.0
        if projected_margin_util > risk_cfg.max_margin_utilization_pct:
            reasons.append(
                f"Margin utilization {projected_margin_util:.2f}% exceeds limit {risk_cfg.max_margin_utilization_pct:.2f}%."
            )

        return RiskEvaluation(
            approved=len(reasons) == 0,
            reasons=reasons,
            recommended_quantity=recommended_qty,
            estimated_max_loss=round(max_loss, 2),
            risk_reward_ratio=rr,
            circuit_breaker_triggered=circuit_breaker,
        )
