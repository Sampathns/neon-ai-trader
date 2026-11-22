"""Strict DEMO/REAL trading mode controller with 7-step live authorization and Emergency STOP."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.enums import AlertSeverity, ConnectionStatus, TradingMode
from app.core.security import mask_account_id
from app.db.database import Database, utc_now_iso

LIVE_CONFIRMATION_PHRASE = "ENABLE REAL TRADING"
CLOSE_ALL_CONFIRMATION_PHRASE = "CLOSE ALL POSITIONS"


class ModeSwitchError(Exception):
    """Raised when a mode switch or live authorization fails safety checks."""


class TradingModeController:
    """Enforces backend-level isolation between DEMO and REAL trading modes."""

    def __init__(self, db: Database, broker_registry: Any, notification_service: Any) -> None:
        self.db = db
        self.broker_registry = broker_registry
        self.notifications = notification_service

    def get_status(self) -> Dict[str, Any]:
        state = self.db.get_mode_state()
        mode = state["current_mode"]
        broker_name = state["active_broker"]
        connector = self.broker_registry.get_connector(mode, broker_name)
        health = connector.health_check() if connector else {
            "status": ConnectionStatus.UNCONFIGURED.value,
            "broker": broker_name,
            "mode": mode,
        }
        account_info = (
            connector.get_account_info()
            if connector and health.get("status") == ConnectionStatus.CONNECTED.value
            else {
                "account_id_masked": mask_account_id(
                    getattr(connector, "account_id", "") if connector else ""
                ),
                "balance": 0.0,
                "equity": 0.0,
                "available_margin": 0.0,
                "used_margin": 0.0,
                "permissions": {"trade_allowed": False},
            }
        )
        open_positions = self.db.list_positions(mode, status="OPEN")
        exposure = sum(abs(p["quantity"] * p["current_price"]) for p in open_positions)

        return {
            "current_mode": mode,
            "real_trading_enabled": state["real_trading_enabled"],
            "auto_trading_enabled": state["auto_trading_enabled"],
            "ai_scanner_running": state["ai_scanner_running"],
            "emergency_stop_active": state["emergency_stop_active"],
            "active_broker": broker_name,
            "authorized_by": state["authorized_by"],
            "authorized_at": state["authorized_at"],
            "connection_health": health,
            "account_id_masked": account_info.get("account_id_masked", "UNCONFIGURED"),
            "balance": account_info.get("balance", 0.0),
            "equity": account_info.get("equity", 0.0),
            "available_margin": account_info.get("available_margin", 0.0),
            "used_margin": account_info.get("used_margin", 0.0),
            "open_positions_count": len(open_positions),
            "current_exposure": round(exposure, 2),
            "trading_permissions": account_info.get("permissions", {}),
        }

    def switch_mode(
        self,
        target_mode: TradingMode,
        actor: str,
        broker_name: Optional[str] = None,
        acknowledge_open_positions: bool = False,
    ) -> Dict[str, Any]:
        """Switch between DEMO and REAL mode without ever silently enabling real execution."""
        state = self.db.get_mode_state()
        current_mode = state["current_mode"]
        open_positions = self.db.list_positions(current_mode, status="OPEN")

        if open_positions and not acknowledge_open_positions:
            return {
                "switched": False,
                "warning": (
                    f"{len(open_positions)} open position(s) exist in {current_mode} mode. "
                    "Existing positions remain under their original account and are NEVER "
                    "automatically duplicated or transferred. Confirm acknowledgment to switch view."
                ),
                "open_positions_count": len(open_positions),
                "current_mode": current_mode,
            }

        if target_mode == TradingMode.DEMO:
            selected_broker = broker_name or "PAPER"
            updated = self.db.update_mode_state(
                current_mode=TradingMode.DEMO.value,
                real_trading_enabled=False,
                auto_trading_enabled=False,
                active_broker=selected_broker,
            )
            self.db.log_audit(
                "MODE_SWITCH_TO_DEMO",
                actor,
                TradingMode.DEMO.value,
                {"previous_mode": current_mode, "active_broker": selected_broker},
            )
            return {
                "switched": True,
                "mode_state": updated,
                "note": "Switched to DEMO mode. Real execution is disabled.",
            }

        # Switching view to REAL mode STILL keeps real_trading_enabled=False until 7-step authorization completes
        selected_broker = broker_name or "BINANCE"
        if selected_broker == "PAPER":
            raise ModeSwitchError("PAPER broker cannot be used in REAL trading mode.")

        updated = self.db.update_mode_state(
            current_mode=TradingMode.REAL.value,
            real_trading_enabled=False,
            auto_trading_enabled=False,
            active_broker=selected_broker,
        )
        self.db.log_audit(
            "MODE_SWITCH_TO_REAL_LOCKED",
            actor,
            TradingMode.REAL.value,
            {"previous_mode": current_mode, "active_broker": selected_broker},
        )
        return {
            "switched": True,
            "mode_state": updated,
            "live_risk_warning": (
                "LIVE TRADING WARNING: Real-money execution involves substantial risk of capital loss. "
                "Real trading remains DISABLED until you verify your live account, broker connection, "
                f"risk limits, and explicitly confirm with '{LIVE_CONFIRMATION_PHRASE}'."
            ),
            "requires_live_authorization": True,
        }

    def enable_real_trading(
        self,
        broker_name: str,
        verified_account_last4: str,
        confirmation_phrase: str,
        risk_acknowledged: bool,
        actor: str,
    ) -> Dict[str, Any]:
        """Execute the mandatory 7-step live trading authorization workflow."""
        state = self.db.get_mode_state()

        # Step 1: Must explicitly be in REAL mode
        if state["current_mode"] != TradingMode.REAL.value:
            raise ModeSwitchError("Select REAL MODE before enabling live trading.")

        # Emergency stop must be cleared before live execution can be authorized
        if state["emergency_stop_active"]:
            raise ModeSwitchError("Cannot enable live trading while EMERGENCY STOP is active.")

        # Step 2: Live risk warning acknowledgment
        if not risk_acknowledged:
            raise ModeSwitchError("Live-risk warning must be explicitly acknowledged.")

        # Step 3: Verify broker & credentials exist strictly for REAL mode
        if broker_name == "PAPER":
            raise ModeSwitchError("Paper simulator cannot be authorized for REAL trading.")
        connector = self.broker_registry.get_connector(TradingMode.REAL.value, broker_name)
        if connector is None:
            raise ModeSwitchError(f"Live broker connector '{broker_name}' is not configured.")

        # Step 4: Check broker connection & account verification
        health = connector.health_check()
        if health.get("status") != ConnectionStatus.CONNECTED.value:
            raise ModeSwitchError(
                f"Live broker '{broker_name}' connection check failed: {health.get('reason', 'disconnected')}."
            )

        acct = connector.get_account_info()
        masked = acct.get("account_id_masked", "")
        if not masked.endswith(verified_account_last4):
            raise ModeSwitchError(
                "Account verification failed: provided account identifier suffix does not match connected live account."
            )

        perms = acct.get("permissions", {})
        if perms.get("withdraw_allowed"):
            raise ModeSwitchError(
                "Security rejection: API key has withdrawal permission enabled. Use least-privilege trade-only keys."
            )

        # Step 5: Validate risk configuration
        risk_cfg = self.db.get_risk_config(TradingMode.REAL.value)
        if risk_cfg.max_risk_per_trade_pct <= 0 or risk_cfg.daily_loss_limit_pct <= 0:
            raise ModeSwitchError("Invalid live risk configuration: stop-loss and daily loss limits are mandatory.")
        if risk_cfg.allow_martingale or risk_cfg.allow_loss_doubling:
            raise ModeSwitchError("Prohibited risk settings detected.")

        # Step 6: Deliberate confirmation phrase
        if confirmation_phrase.strip() != LIVE_CONFIRMATION_PHRASE:
            raise ModeSwitchError(
                f"Explicit confirmation phrase required: type '{LIVE_CONFIRMATION_PHRASE}' verbatim."
            )

        # Step 7: All safety checks passed -> authorize live trading
        now = utc_now_iso()
        updated = self.db.update_mode_state(
            real_trading_enabled=True,
            active_broker=broker_name,
            authorized_by=actor,
            authorized_at=now,
        )
        self.db.log_audit(
            "REAL_TRADING_AUTHORIZED",
            actor,
            TradingMode.REAL.value,
            {"broker": broker_name, "account_id_masked": masked, "authorized_at": now},
        )
        self.notifications.emit(
            category="SECURITY",
            severity=AlertSeverity.WARNING,
            title="Live Trading Authorized",
            message=f"REAL trading enabled by {actor} on {broker_name} ({masked}).",
        )
        return {"authorized": True, "mode_state": updated, "account_id_masked": masked}

    def assert_execution_allowed(self, trading_mode: str, is_automated: bool = False) -> None:
        """Backend guard called before EVERY single order submission."""
        state = self.db.get_mode_state()
        if state["emergency_stop_active"]:
            raise ModeSwitchError("Execution blocked: EMERGENCY STOP is active.")
        if state["current_mode"] != trading_mode:
            raise ModeSwitchError(
                f"Mode mismatch: order targets {trading_mode} while system is in {state['current_mode']}."
            )
        if trading_mode == TradingMode.REAL.value and not state["real_trading_enabled"]:
            raise ModeSwitchError(
                "Unauthorized live execution rejected: REAL trading has not been explicitly authorized."
            )
        if is_automated and not state["auto_trading_enabled"]:
            raise ModeSwitchError("Automated execution is currently disabled.")

    def trigger_emergency_stop(self, actor: str, reason: str = "User triggered Emergency STOP") -> Dict[str, Any]:
        """Immediately halt all automation, disable real trading, and cancel pending orders."""
        state = self.db.get_mode_state()
        mode = state["current_mode"]
        broker_name = state["active_broker"]

        self.db.update_mode_state(
            emergency_stop_active=True,
            auto_trading_enabled=False,
            ai_scanner_running=False,
            real_trading_enabled=False,
        )
        cancelled = self.cancel_pending_orders(actor=actor, reason="Emergency STOP")
        self.db.log_audit(
            "EMERGENCY_STOP_TRIGGERED",
            actor,
            mode,
            {"reason": reason, "cancelled_orders": cancelled["cancelled_count"], "broker": broker_name},
        )
        self.notifications.emit(
            category="EMERGENCY",
            severity=AlertSeverity.CRITICAL,
            title="EMERGENCY STOP ACTIVATED",
            message=f"Trading halted by {actor}. Reason: {reason}. Cancelled {cancelled['cancelled_count']} pending order(s).",
        )
        return {
            "emergency_stop_active": True,
            "cancelled_orders": cancelled["cancelled_count"],
            "mode_state": self.db.get_mode_state(),
        }

    def reset_emergency_stop(self, actor: str) -> Dict[str, Any]:
        state = self.db.get_mode_state()
        updated = self.db.update_mode_state(emergency_stop_active=False)
        self.db.log_audit("EMERGENCY_STOP_RESET", actor, state["current_mode"], {})
        return {"emergency_stop_active": False, "mode_state": updated}

    def cancel_pending_orders(self, actor: str, reason: str = "Manual cancel") -> Dict[str, Any]:
        state = self.db.get_mode_state()
        mode = state["current_mode"]
        connector = self.broker_registry.get_connector(mode, state["active_broker"])
        orders = self.db.list_orders(mode, limit=200)
        cancelled_ids: List[str] = []
        for order in orders:
            if order["status"] in ("PENDING", "SUBMITTED"):
                if connector and order.get("broker_order_id"):
                    try:
                        connector.cancel_order(order["broker_order_id"])
                    except Exception:
                        pass
                self.db.update_order(order["id"], status="CANCELLED", error_message=reason)
                cancelled_ids.append(order["id"])
        self.db.log_audit(
            "CANCEL_PENDING_ORDERS",
            actor,
            mode,
            {"cancelled_count": len(cancelled_ids), "reason": reason},
        )
        return {"cancelled_count": len(cancelled_ids), "order_ids": cancelled_ids}

    def close_all_positions(self, confirmation_phrase: str, actor: str) -> Dict[str, Any]:
        """Close all open positions in the CURRENT mode only after explicit confirmation."""
        if confirmation_phrase.strip() != CLOSE_ALL_CONFIRMATION_PHRASE:
            raise ModeSwitchError(
                f"Confirmation required: type '{CLOSE_ALL_CONFIRMATION_PHRASE}' to close all positions."
            )
        state = self.db.get_mode_state()
        mode = state["current_mode"]
        connector = self.broker_registry.get_connector(mode, state["active_broker"])
        open_positions = self.db.list_positions(mode, status="OPEN")
        closed_ids: List[str] = []
        for pos in open_positions:
            if connector:
                try:
                    connector.close_position(pos["id"])
                except Exception:
                    pass
            pos["status"] = "CLOSED"
            pos["closed_at"] = utc_now_iso()
            pos["realized_pnl"] = pos.get("unrealized_pnl", 0.0)
            pos["unrealized_pnl"] = 0.0
            self.db.save_position(pos)
            closed_ids.append(pos["id"])
        self.db.log_audit(
            "CLOSE_ALL_POSITIONS",
            actor,
            mode,
            {"closed_count": len(closed_ids)},
        )
        return {"closed_count": len(closed_ids), "position_ids": closed_ids}
