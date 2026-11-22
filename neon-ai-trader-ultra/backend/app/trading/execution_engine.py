"""Autonomous Trade Execution Engine with pre-trade checks, idempotency, and broker reconciliation."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from app.core.enums import AlertSeverity, OrderSide, OrderStatus, OrderType
from app.core.mode_controller import ModeSwitchError, TradingModeController
from app.db.database import Database, utc_now_iso
from app.market_data.engine import MarketDataEngine
from app.risk.engine import RiskManagementEngine


class ExecutionError(Exception):
    """Raised when an order fails pre-trade validation, risk, or broker checks."""


class TradeExecutionEngine:
    """
    Strictly separated from AI analysis. Every single order passes through:
    1. Mode & authorization guard (Emergency STOP / REAL mode authorization)
    2. Idempotency check (prevents duplicate order submissions)
    3. Broker connectivity & symbol validation
    4. Market data freshness & spread check
    5. Backend Risk Management Engine validation
    6. Broker order submission + persistent order/position tracking + reconciliation.
    """

    def __init__(
        self,
        db: Database,
        broker_registry: Any,
        mode_controller: TradingModeController,
        risk_engine: RiskManagementEngine,
        data_engine: MarketDataEngine,
        notifications: Any,
    ) -> None:
        self.db = db
        self.broker_registry = broker_registry
        self.mode_controller = mode_controller
        self.risk_engine = risk_engine
        self.data_engine = data_engine
        self.notifications = notifications

    def _compute_realized_metrics(self, trading_mode: str) -> Dict[str, Any]:
        closed = self.db.list_positions(trading_mode, status="CLOSED")
        daily_pnl = sum(float(p.get("realized_pnl", 0.0)) for p in closed)
        weekly_pnl = daily_pnl
        consecutive_losses = 0
        for pos in closed:
            if float(pos.get("realized_pnl", 0.0)) < 0:
                consecutive_losses += 1
            else:
                break
        return {
            "daily_pnl": daily_pnl,
            "weekly_pnl": weekly_pnl,
            "consecutive_losses": consecutive_losses,
        }

    def submit_order(
        self,
        *,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        stop_loss: float,
        take_profit: float,
        actor: str,
        quantity: Optional[float] = None,
        entry_price: Optional[float] = None,
        strategy_name: str = "MANUAL",
        signal_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        requested_leverage: float = 1.0,
        is_automated: bool = False,
        override_daily_pnl: Optional[float] = None,
        override_consecutive_losses: Optional[int] = None,
    ) -> Dict[str, Any]:
        state = self.db.get_mode_state()
        mode = state["current_mode"]
        broker_name = state["active_broker"]

        # 1. Mode & Live Authorization Guard
        self.mode_controller.assert_execution_allowed(mode, is_automated=is_automated)

        # 2. Idempotency Guard (prevent duplicate order submission)
        idem_key = idempotency_key or f"{mode}:{broker_name}:{symbol}:{side.value}:{uuid.uuid4().hex}"
        existing = self.db.get_order_by_idempotency_key(idem_key)
        if existing:
            return {
                "duplicate_prevented": True,
                "order": existing,
                "message": "Duplicate order prevented via idempotency key; returning original order record.",
            }

        # 3. Broker connection & symbol validation
        connector = self.broker_registry.get_connector(mode, broker_name)
        if connector is None:
            raise ExecutionError(f"Broker '{broker_name}' is not available in {mode} mode.")
        if not self.data_engine.ensure_connected(connector):
            self.notifications.emit(
                category="CONNECTIVITY",
                severity=AlertSeverity.CRITICAL,
                title="Broker Connection Failure",
                message=f"Unable to connect to {broker_name} ({mode}) for order on {symbol}.",
            )
            raise ExecutionError(f"Broker '{broker_name}' is disconnected.")

        # 4. Data freshness & quote validation
        ticker = connector.get_ticker(symbol)
        quality = self.data_engine.validate_ticker(ticker)
        if not quality.is_valid or ticker is None:
            raise ExecutionError(f"Order blocked due to market data quality: {'; '.join(quality.reasons)}")

        ref_price = entry_price if (order_type != OrderType.MARKET and entry_price) else (
            ticker.ask if side == OrderSide.BUY else ticker.bid
        )
        account = connector.get_account_info()
        risk_cfg = self.db.get_risk_config(mode)
        open_positions = self.db.list_positions(mode, status="OPEN")
        perf = self._compute_realized_metrics(mode)
        daily_pnl = override_daily_pnl if override_daily_pnl is not None else perf["daily_pnl"]
        consec_losses = (
            override_consecutive_losses
            if override_consecutive_losses is not None
            else perf["consecutive_losses"]
        )

        # 5. Mandatory Backend Risk Check
        evaluation = self.risk_engine.evaluate_trade(
            trading_mode=mode,
            symbol=symbol.upper(),
            side=side.value,
            entry_price=ref_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            quantity=quantity,
            equity=account["equity"],
            available_margin=account["available_margin"],
            used_margin=account["used_margin"],
            daily_pnl=daily_pnl,
            weekly_pnl=perf["weekly_pnl"],
            open_positions=open_positions,
            spread_bps=ticker.spread_bps,
            estimated_slippage_bps=3.0,
            requested_leverage=requested_leverage,
            consecutive_losses=consec_losses,
            risk_cfg=risk_cfg,
        )

        if not evaluation.approved:
            if evaluation.circuit_breaker_triggered:
                self.db.update_mode_state(auto_trading_enabled=False)
                self.notifications.emit(
                    category="RISK",
                    severity=AlertSeverity.CRITICAL,
                    title="Risk Circuit Breaker Triggered",
                    message=f"Automated execution halted in {mode}: {'; '.join(evaluation.reasons)}",
                )
            self.db.log_audit(
                "ORDER_REJECTED_BY_RISK",
                actor,
                mode,
                {"symbol": symbol, "side": side.value, "reasons": evaluation.reasons},
            )
            raise ExecutionError(f"Risk Engine rejected order: {'; '.join(evaluation.reasons)}")

        final_qty = quantity if (quantity is not None and quantity > 0) else evaluation.recommended_quantity

        # Persist PENDING order BEFORE broker submission for full reconciliation auditability
        order_record = self.db.create_order(
            {
                "idempotency_key": idem_key,
                "trading_mode": mode,
                "broker_name": broker_name,
                "account_id_masked": account["account_id_masked"],
                "symbol": symbol.upper(),
                "side": side.value,
                "order_type": order_type.value,
                "quantity": final_qty,
                "requested_price": ref_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "status": OrderStatus.PENDING.value,
                "strategy_name": strategy_name,
                "signal_id": signal_id,
            }
        )

        # 6. Submit to broker
        result = connector.place_order(
            symbol=symbol.upper(),
            side=side.value,
            order_type=order_type.value,
            quantity=final_qty,
            price=ref_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            client_order_id=order_record["id"],
        )

        updated_order = self.db.update_order(
            order_record["id"],
            status=result.status,
            broker_order_id=result.broker_order_id,
            filled_price=result.filled_price,
            commission=result.commission,
            slippage_bps=result.slippage_bps,
            error_message=result.error_message,
        )

        position_record = None
        if result.status == OrderStatus.FILLED.value and result.filled_price is not None:
            position_record = self.db.save_position(
                {
                    "id": result.broker_order_id or str(uuid.uuid4()),
                    "trading_mode": mode,
                    "broker_name": broker_name,
                    "account_id_masked": account["account_id_masked"],
                    "symbol": symbol.upper(),
                    "side": side.value,
                    "quantity": final_qty,
                    "entry_price": result.filled_price,
                    "current_price": result.filled_price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "unrealized_pnl": 0.0,
                    "realized_pnl": 0.0,
                    "margin_used": round((result.filled_price * final_qty) / max(requested_leverage, 1.0), 2),
                    "status": "OPEN",
                    "strategy_name": strategy_name,
                }
            )
            self.notifications.emit(
                category="EXECUTION",
                severity=AlertSeverity.INFO,
                title=f"Trade Opened ({mode})",
                message=(
                    f"{side.value} {final_qty} {symbol.upper()} @ {result.filled_price} "
                    f"(SL={stop_loss}, TP={take_profit}, R/R={evaluation.risk_reward_ratio})."
                ),
            )

        self.db.log_audit(
            "ORDER_SUBMITTED",
            actor,
            mode,
            {
                "order_id": order_record["id"],
                "broker_order_id": result.broker_order_id,
                "symbol": symbol.upper(),
                "side": side.value,
                "quantity": final_qty,
                "status": result.status,
            },
        )
        return {
            "duplicate_prevented": False,
            "order": updated_order,
            "position": position_record,
            "risk_evaluation": {
                "estimated_max_loss": evaluation.estimated_max_loss,
                "risk_reward_ratio": evaluation.risk_reward_ratio,
            },
        }

    def reconcile_orders(self, actor: str = "system") -> Dict[str, Any]:
        """Reconcile uncertain/pending local orders with broker state before any retry."""
        state = self.db.get_mode_state()
        mode = state["current_mode"]
        connector = self.broker_registry.get_connector(mode, state["active_broker"])
        orders = self.db.list_orders(mode, limit=200)
        reconciled = 0
        for order in orders:
            if order["status"] in ("PENDING", "SUBMITTED") and order.get("broker_order_id") and connector:
                remote = connector.get_order_status(order["broker_order_id"])
                if remote and remote.get("status") and remote["status"] != order["status"]:
                    self.db.update_order(
                        order["id"],
                        status=remote["status"],
                        filled_price=remote.get("filled_price", order.get("filled_price")),
                    )
                    reconciled += 1
        self.db.log_audit("ORDER_RECONCILIATION", actor, mode, {"reconciled_count": reconciled})
        return {"mode": mode, "reconciled_count": reconciled, "checked_at": utc_now_iso()}
