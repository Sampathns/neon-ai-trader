"""Thread-safe database repository layer with strict DEMO/REAL record isolation."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import RiskConfig
from app.core.security import hash_password, redact_secrets


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """SQLite persistence layer (production PostgreSQL uses identical DDL schema)."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        schema_file = Path(__file__).parent / "schema.sql"
        ddl = schema_file.read_text(encoding="utf-8")
        with self._lock:
            self._conn.executescript(ddl)
            now = utc_now_iso()
            # Ensure singleton mode state exists in safe DEMO default
            self._conn.execute(
                """
                INSERT OR IGNORE INTO trading_mode_state
                (id, current_mode, real_trading_enabled, auto_trading_enabled,
                 ai_scanner_running, emergency_stop_active, active_broker, updated_at)
                VALUES (1, 'DEMO', 0, 0, 0, 0, 'PAPER', ?)
                """,
                (now,),
            )
            # Ensure default conservative risk configurations exist for both modes
            default_risk = json.dumps(RiskConfig().__dict__)
            for mode in ("DEMO", "REAL"):
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO risk_configurations (trading_mode, config_json, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (mode, default_risk, now),
                )
            # Ensure a default local admin user exists for initial setup
            self._conn.execute(
                """
                INSERT OR IGNORE INTO users (username, password_hash, role, is_active, created_at)
                VALUES (?, ?, 'admin', 1, ?)
                """,
                ("admin", hash_password("neon-admin-change-me"), now),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- Users ---
    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            return dict(row) if row else None

    def create_user(self, username: str, password: str, role: str = "trader") -> Dict[str, Any]:
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO users (username, password_hash, role, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
                (username, hash_password(password), role, now),
            )
            self._conn.commit()
            return self.get_user(username)  # type: ignore[return-value]

    # --- Mode State ---
    def get_mode_state(self) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM trading_mode_state WHERE id = 1").fetchone()
            d = dict(row)
            d["real_trading_enabled"] = bool(d["real_trading_enabled"])
            d["auto_trading_enabled"] = bool(d["auto_trading_enabled"])
            d["ai_scanner_running"] = bool(d["ai_scanner_running"])
            d["emergency_stop_active"] = bool(d["emergency_stop_active"])
            return d

    def update_mode_state(self, **kwargs: Any) -> Dict[str, Any]:
        allowed = {
            "current_mode",
            "real_trading_enabled",
            "auto_trading_enabled",
            "ai_scanner_running",
            "emergency_stop_active",
            "active_broker",
            "authorized_by",
            "authorized_at",
        }
        fields = {k: (int(v) if isinstance(v, bool) else v) for k, v in kwargs.items() if k in allowed}
        if not fields:
            return self.get_mode_state()
        fields["updated_at"] = utc_now_iso()
        clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values())
        with self._lock:
            self._conn.execute(f"UPDATE trading_mode_state SET {clause} WHERE id = 1", values)
            self._conn.commit()
            return self.get_mode_state()

    # --- Encrypted Credentials ---
    def save_encrypted_credential(
        self,
        broker_name: str,
        trading_mode: str,
        account_id_masked: str,
        encrypted_payload: str,
        permissions: Dict[str, Any],
    ) -> None:
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO broker_credentials
                (broker_name, trading_mode, account_id_masked, encrypted_payload, permissions_json, is_active, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(broker_name, trading_mode) DO UPDATE SET
                    account_id_masked = excluded.account_id_masked,
                    encrypted_payload = excluded.encrypted_payload,
                    permissions_json = excluded.permissions_json,
                    updated_at = excluded.updated_at
                """,
                (broker_name, trading_mode, account_id_masked, encrypted_payload, json.dumps(permissions), now),
            )
            self._conn.commit()

    def get_encrypted_credential(self, broker_name: str, trading_mode: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM broker_credentials WHERE broker_name = ? AND trading_mode = ?",
                (broker_name, trading_mode),
            ).fetchone()
            return dict(row) if row else None

    # --- Risk Config ---
    def get_risk_config(self, trading_mode: str) -> RiskConfig:
        with self._lock:
            row = self._conn.execute(
                "SELECT config_json FROM risk_configurations WHERE trading_mode = ?",
                (trading_mode,),
            ).fetchone()
            if not row:
                return RiskConfig()
            data = json.loads(row["config_json"])
            # Enforce permanently prohibited strategies even if tampered with in DB
            data["allow_martingale"] = False
            data["allow_loss_doubling"] = False
            data["allow_uncontrolled_grid"] = False
            return RiskConfig(**data)

    def save_risk_config(self, trading_mode: str, cfg: RiskConfig) -> RiskConfig:
        cfg.allow_martingale = False
        cfg.allow_loss_doubling = False
        cfg.allow_uncontrolled_grid = False
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO risk_configurations (trading_mode, config_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(trading_mode) DO UPDATE SET
                    config_json = excluded.config_json,
                    updated_at = excluded.updated_at
                """,
                (trading_mode, json.dumps(cfg.__dict__), now),
            )
            self._conn.commit()
            return cfg

    # --- Orders (strictly isolated by trading_mode) ---
    def create_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        now = utc_now_iso()
        order.setdefault("id", str(uuid.uuid4()))
        order.setdefault("created_at", now)
        order.setdefault("updated_at", now)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO orders (
                    id, idempotency_key, trading_mode, broker_name, account_id_masked,
                    symbol, side, order_type, quantity, requested_price, filled_price,
                    stop_loss, take_profit, status, broker_order_id, commission,
                    slippage_bps, strategy_name, signal_id, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order["id"],
                    order["idempotency_key"],
                    order["trading_mode"],
                    order["broker_name"],
                    order["account_id_masked"],
                    order["symbol"],
                    order["side"],
                    order["order_type"],
                    order["quantity"],
                    order.get("requested_price"),
                    order.get("filled_price"),
                    order.get("stop_loss"),
                    order.get("take_profit"),
                    order["status"],
                    order.get("broker_order_id"),
                    order.get("commission", 0.0),
                    order.get("slippage_bps", 0.0),
                    order.get("strategy_name"),
                    order.get("signal_id"),
                    order.get("error_message"),
                    order["created_at"],
                    order["updated_at"],
                ),
            )
            self._conn.commit()
            return self.get_order_by_id(order["id"])  # type: ignore[return-value]

    def get_order_by_idempotency_key(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM orders WHERE idempotency_key = ?", (key,)
            ).fetchone()
            return dict(row) if row else None

    def get_order_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            return dict(row) if row else None

    def update_order(self, order_id: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        kwargs["updated_at"] = utc_now_iso()
        clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [order_id]
        with self._lock:
            self._conn.execute(f"UPDATE orders SET {clause} WHERE id = ?", values)
            self._conn.commit()
            return self.get_order_by_id(order_id)

    def list_orders(self, trading_mode: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM orders WHERE trading_mode = ? ORDER BY created_at DESC LIMIT ?",
                (trading_mode, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    # --- Positions (strictly isolated by trading_mode) ---
    def save_position(self, pos: Dict[str, Any]) -> Dict[str, Any]:
        pos.setdefault("id", str(uuid.uuid4()))
        pos.setdefault("opened_at", utc_now_iso())
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO positions (
                    id, trading_mode, broker_name, account_id_masked, symbol, side,
                    quantity, entry_price, current_price, stop_loss, take_profit,
                    unrealized_pnl, realized_pnl, margin_used, status, strategy_name,
                    opened_at, closed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    current_price = excluded.current_price,
                    stop_loss = excluded.stop_loss,
                    take_profit = excluded.take_profit,
                    unrealized_pnl = excluded.unrealized_pnl,
                    realized_pnl = excluded.realized_pnl,
                    margin_used = excluded.margin_used,
                    status = excluded.status,
                    closed_at = excluded.closed_at
                """,
                (
                    pos["id"],
                    pos["trading_mode"],
                    pos["broker_name"],
                    pos["account_id_masked"],
                    pos["symbol"],
                    pos["side"],
                    pos["quantity"],
                    pos["entry_price"],
                    pos["current_price"],
                    pos.get("stop_loss"),
                    pos.get("take_profit"),
                    pos.get("unrealized_pnl", 0.0),
                    pos.get("realized_pnl", 0.0),
                    pos.get("margin_used", 0.0),
                    pos["status"],
                    pos.get("strategy_name"),
                    pos["opened_at"],
                    pos.get("closed_at"),
                ),
            )
            self._conn.commit()
            return pos

    def list_positions(
        self, trading_mode: str, status: Optional[str] = "OPEN"
    ) -> List[Dict[str, Any]]:
        with self._lock:
            if status:
                rows = self._conn.execute(
                    "SELECT * FROM positions WHERE trading_mode = ? AND status = ? ORDER BY opened_at DESC",
                    (trading_mode, status),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM positions WHERE trading_mode = ? ORDER BY opened_at DESC",
                    (trading_mode,),
                ).fetchall()
            return [dict(r) for r in rows]

    # --- Signals ---
    def save_signal(self, signal: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO signals (
                    id, symbol, asset_class, classification, direction, current_price,
                    entry_low, entry_high, stop_loss, take_profit_1, take_profit_2,
                    risk_reward, confidence_score, historical_win_rate, estimated_probability,
                    regime, data_status, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal["id"],
                    signal["symbol"],
                    signal["asset_class"],
                    signal["classification"],
                    signal["direction"],
                    signal["current_price"],
                    signal["entry_zone"][0],
                    signal["entry_zone"][1],
                    signal["stop_loss"],
                    signal["take_profit_levels"][0],
                    signal["take_profit_levels"][-1],
                    signal["risk_reward_ratio"],
                    signal["confidence_estimate"],
                    signal.get("historical_win_rate"),
                    signal.get("estimated_probability"),
                    signal["market_regime"],
                    signal["data_status"],
                    json.dumps(signal),
                    signal["signal_timestamp"],
                ),
            )
            self._conn.commit()

    def list_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload_json FROM signals ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [json.loads(r["payload_json"]) for r in rows]

    # --- Audit Log ---
    def log_audit(
        self, event_type: str, actor: str, trading_mode: str, details: Dict[str, Any]
    ) -> None:
        safe_details = redact_secrets(json.dumps(details))
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit_logs (event_type, actor, trading_mode, details_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (event_type, actor, trading_mode, safe_details, utc_now_iso()),
            )
            self._conn.commit()

    def list_audit_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            result = []
            for r in rows:
                item = dict(r)
                item["details"] = json.loads(item.pop("details_json"))
                result.append(item)
            return result

    # --- Notifications ---
    def save_notification(
        self, category: str, severity: str, title: str, message: str
    ) -> Dict[str, Any]:
        nid = str(uuid.uuid4())
        now = utc_now_iso()
        safe_msg = redact_secrets(message)
        with self._lock:
            self._conn.execute(
                "INSERT INTO notifications (id, category, severity, title, message, acknowledged, created_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
                (nid, category, severity, title, safe_msg, now),
            )
            self._conn.commit()
        return {
            "id": nid,
            "category": category,
            "severity": severity,
            "title": title,
            "message": safe_msg,
            "acknowledged": False,
            "created_at": now,
        }

    def list_notifications(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["acknowledged"] = bool(d["acknowledged"])
                out.append(d)
            return out

    # --- Backtest Runs ---
    def save_backtest_run(
        self,
        run_id: str,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        metrics: Dict[str, Any],
        equity_curve: List[Dict[str, Any]],
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO backtest_runs (id, strategy_name, symbol, timeframe, metrics_json, equity_curve_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, strategy_name, symbol, timeframe, json.dumps(metrics), json.dumps(equity_curve), utc_now_iso()),
            )
            self._conn.commit()
