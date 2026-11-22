"""FastAPI REST and WebSocket endpoints for NEON AI TRADER ULTRA."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from app.core.config import RiskConfig
from app.core.enums import AlertSeverity, AssetClass, TradingMode
from app.core.mode_controller import ModeSwitchError
from app.core.security import (
    create_access_token,
    mask_account_id,
    verify_access_token,
    verify_password,
)
from app.db.models import (
    BacktestRequest,
    BrokerCredentialRequest,
    CloseAllPositionsRequest,
    EnableRealTradingRequest,
    LoginRequest,
    ModeSwitchRequest,
    OrderRequest,
    RiskConfigUpdate,
    StrategyToggleRequest,
    TokenResponse,
)
from app.trading.execution_engine import ExecutionError


def build_router(container: Dict[str, Any]) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    settings = container["settings"]
    db = container["db"]
    vault = container["vault"]
    registry = container["registry"]
    mode_ctrl = container["mode_controller"]
    data_engine = container["data_engine"]
    signal_engine = container["signal_engine"]
    strategy_engine = container["strategy_engine"]
    execution_engine = container["execution_engine"]
    backtester = container["backtester"]
    notifications = container["notifications"]

    def get_current_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Provide Bearer token.",
            )
        token = authorization.split(" ", 1)[1].strip()
        try:
            return verify_access_token(token, settings.secret_key)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    # --- Health & Auth ---
    @router.get("/health")
    def health() -> Dict[str, Any]:
        state = db.get_mode_state()
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": settings.app_version,
            "trading_mode": state["current_mode"],
            "real_trading_enabled": state["real_trading_enabled"],
            "emergency_stop_active": state["emergency_stop_active"],
        }

    @router.post("/auth/login", response_model=TokenResponse)
    def login(payload: LoginRequest) -> TokenResponse:
        user = db.get_user(payload.username)
        if not user or not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password.")
        token = create_access_token(user["username"], user["role"], settings.secret_key)
        db.log_audit("USER_LOGIN", user["username"], db.get_mode_state()["current_mode"], {})
        return TokenResponse(access_token=token, username=user["username"], role=user["role"])

    # --- Dashboard & Trading Mode Controls ---
    @router.get("/mode/status")
    def mode_status() -> Dict[str, Any]:
        status_payload = mode_ctrl.get_status()
        status_payload["brokers"] = registry.list_health(status_payload["current_mode"])
        status_payload["strategies"] = strategy_engine.list_strategies()
        return status_payload

    @router.post("/mode/switch")
    def switch_mode(
        payload: ModeSwitchRequest, user: Dict[str, Any] = Depends(get_current_user)
    ) -> Dict[str, Any]:
        try:
            return mode_ctrl.switch_mode(
                target_mode=payload.target_mode,
                actor=user["sub"],
                broker_name=payload.broker_name,
                acknowledge_open_positions=payload.acknowledge_open_positions,
            )
        except ModeSwitchError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/mode/enable-real")
    def enable_real(
        payload: EnableRealTradingRequest, user: Dict[str, Any] = Depends(get_current_user)
    ) -> Dict[str, Any]:
        try:
            return mode_ctrl.enable_real_trading(
                broker_name=payload.broker_name,
                verified_account_last4=payload.verified_account_last4,
                confirmation_phrase=payload.confirmation_phrase,
                risk_acknowledged=payload.risk_acknowledged,
                actor=user["sub"],
            )
        except ModeSwitchError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    # --- Automation & Emergency Controls ---
    @router.post("/automation/scanner/{action}")
    def scanner_control(action: str, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        running = action.lower() == "start"
        state = db.get_mode_state()
        if running and state["emergency_stop_active"]:
            raise HTTPException(status_code=400, detail="Cannot start scanner while EMERGENCY STOP is active.")
        updated = db.update_mode_state(ai_scanner_running=running)
        db.log_audit("SCANNER_TOGGLE", user["sub"], state["current_mode"], {"running": running})
        return {"ai_scanner_running": running, "mode_state": updated}

    @router.post("/automation/auto-trading/{action}")
    def auto_trading_control(action: str, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        enabled = action.lower() == "enable"
        state = db.get_mode_state()
        if enabled:
            if state["emergency_stop_active"]:
                raise HTTPException(status_code=400, detail="Cannot enable auto trading during EMERGENCY STOP.")
            if state["current_mode"] == TradingMode.REAL.value and not state["real_trading_enabled"]:
                raise HTTPException(status_code=403, detail="REAL trading must be explicitly authorized first.")
        updated = db.update_mode_state(auto_trading_enabled=enabled)
        db.log_audit("AUTO_TRADING_TOGGLE", user["sub"], state["current_mode"], {"enabled": enabled})
        return {"auto_trading_enabled": enabled, "mode_state": updated}

    @router.post("/automation/emergency-stop")
    def emergency_stop(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        return mode_ctrl.trigger_emergency_stop(actor=user["sub"])

    @router.post("/automation/emergency-stop/reset")
    def reset_emergency_stop(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        return mode_ctrl.reset_emergency_stop(actor=user["sub"])

    @router.post("/automation/cancel-pending")
    def cancel_pending(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        return mode_ctrl.cancel_pending_orders(actor=user["sub"])

    @router.post("/automation/close-all-positions")
    def close_all_positions(
        payload: CloseAllPositionsRequest, user: Dict[str, Any] = Depends(get_current_user)
    ) -> Dict[str, Any]:
        try:
            return mode_ctrl.close_all_positions(payload.confirmation_phrase, actor=user["sub"])
        except ModeSwitchError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # --- Market Scanner, Charts & AI Intelligence ---
    @router.get("/market/scanner")
    def market_scanner(timeframe: str = Query("1h")) -> Dict[str, Any]:
        state = db.get_mode_state()
        mode = state["current_mode"]
        connector = registry.get_connector(mode, state["active_broker"])
        if connector is None:
            return {"mode": mode, "items": [], "paused_symbols": data_engine.paused_symbols}

        specs = connector.list_symbols()
        items: List[Dict[str, Any]] = []
        for spec in specs[:12]:
            sig = signal_engine.generate_signal(
                connector, spec.symbol, asset_class=spec.asset_class, timeframe=timeframe
            )
            db.save_signal(sig)
            ticker = connector.get_ticker(spec.symbol)
            items.append(
                {
                    "market": spec.asset_class.value,
                    "symbol": spec.symbol,
                    "current_price": sig["current_price"],
                    "volume_24h": ticker.volume_24h if ticker else 0.0,
                    "trend": sig["supporting_indicators"].get("trend", "NEUTRAL"),
                    "classification": sig["classification"],
                    "confidence_estimate": sig["confidence_estimate"],
                    "risk_reward_ratio": sig["risk_reward_ratio"],
                    "market_regime": sig["market_regime"],
                    "data_status": sig["data_status"],
                    "analysis_time": sig["signal_timestamp"],
                    "signal_id": sig["id"],
                }
            )
        return {
            "mode": mode,
            "broker": state["active_broker"],
            "timeframe": timeframe,
            "items": items,
            "paused_symbols": data_engine.paused_symbols,
        }

    @router.get("/market/candles/{symbol}")
    def get_candles(symbol: str, timeframe: str = Query("1h"), limit: int = Query(120, ge=30, le=500)) -> Dict[str, Any]:
        state = db.get_mode_state()
        connector = registry.get_connector(state["current_mode"], state["active_broker"])
        if connector is None:
            raise HTTPException(status_code=503, detail="Active broker connector unavailable.")
        df, quality = data_engine.fetch_validated_ohlcv(connector, symbol.upper(), timeframe=timeframe, limit=limit)
        order_book = connector.get_order_book(symbol.upper(), depth=8)
        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "data_status": quality.data_status.value,
            "age_seconds": quality.age_seconds,
            "candles": df.to_dict(orient="records") if not df.empty else [],
            "order_book": order_book,
        }

    @router.get("/analysis/signal/{symbol}")
    def analyze_symbol(
        symbol: str,
        asset_class: AssetClass = Query(AssetClass.CRYPTO),
        timeframe: str = Query("1h"),
    ) -> Dict[str, Any]:
        state = db.get_mode_state()
        connector = registry.get_connector(state["current_mode"], state["active_broker"])
        if connector is None:
            raise HTTPException(status_code=503, detail="Active broker connector unavailable.")
        sig = signal_engine.generate_signal(connector, symbol.upper(), asset_class=asset_class, timeframe=timeframe)
        sig["strategy_consensus"] = strategy_engine.evaluate(sig)
        db.save_signal(sig)
        return sig

    # --- Orders, Positions & Reconciliation ---
    @router.post("/trading/orders")
    def place_order(
        payload: OrderRequest, user: Dict[str, Any] = Depends(get_current_user)
    ) -> Dict[str, Any]:
        try:
            return execution_engine.submit_order(
                symbol=payload.symbol,
                side=payload.side,
                order_type=payload.order_type,
                quantity=payload.quantity,
                entry_price=payload.entry_price,
                stop_loss=payload.stop_loss,
                take_profit=payload.take_profit,
                strategy_name=payload.strategy_name,
                signal_id=payload.signal_id,
                idempotency_key=payload.idempotency_key,
                requested_leverage=payload.requested_leverage,
                actor=user["sub"],
                is_automated=False,
            )
        except ModeSwitchError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ExecutionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/trading/orders")
    def list_orders(limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
        mode = db.get_mode_state()["current_mode"]
        return {"mode": mode, "orders": db.list_orders(mode, limit=limit)}

    @router.get("/trading/positions")
    def list_positions(status_filter: Optional[str] = Query("OPEN")) -> Dict[str, Any]:
        mode = db.get_mode_state()["current_mode"]
        return {"mode": mode, "positions": db.list_positions(mode, status=status_filter)}

    @router.post("/trading/reconcile")
    def reconcile(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        return execution_engine.reconcile_orders(actor=user["sub"])

    # --- Risk & Strategies ---
    @router.get("/risk/config")
    def get_risk_config() -> Dict[str, Any]:
        mode = db.get_mode_state()["current_mode"]
        return {"mode": mode, "config": db.get_risk_config(mode).__dict__}

    @router.put("/risk/config")
    def update_risk_config(
        payload: RiskConfigUpdate, user: Dict[str, Any] = Depends(get_current_user)
    ) -> Dict[str, Any]:
        mode = db.get_mode_state()["current_mode"]
        cfg = RiskConfig(**payload.dict())
        saved = db.save_risk_config(mode, cfg)
        db.log_audit("RISK_CONFIG_UPDATED", user["sub"], mode, saved.__dict__)
        return {"mode": mode, "config": saved.__dict__}

    @router.get("/strategies")
    def get_strategies() -> Dict[str, bool]:
        return strategy_engine.list_strategies()

    @router.post("/strategies/toggle")
    def toggle_strategy(
        payload: StrategyToggleRequest, user: Dict[str, Any] = Depends(get_current_user)
    ) -> Dict[str, bool]:
        updated = strategy_engine.toggle_strategy(payload.strategy, payload.enabled)
        db.log_audit(
            "STRATEGY_TOGGLED",
            user["sub"],
            db.get_mode_state()["current_mode"],
            {"strategy": payload.strategy.value, "enabled": payload.enabled},
        )
        return updated

    # --- Backtesting Lab ---
    @router.post("/backtesting/run")
    def run_backtest(payload: BacktestRequest) -> Dict[str, Any]:
        # Always pull historical simulation bars from the active DEMO/Paper connector or current broker
        connector = registry.get_connector("DEMO", "PAPER")
        df, _ = data_engine.fetch_validated_ohlcv(
            connector, payload.symbol.upper(), timeframe=payload.timeframe, limit=payload.bars
        )
        if df.empty:
            raise HTTPException(status_code=400, detail=f"No historical candles available for {payload.symbol}.")
        result = backtester.run_backtest(
            df,
            symbol=payload.symbol.upper(),
            timeframe=payload.timeframe,
            strategy=payload.strategy,
            initial_capital=payload.initial_capital,
            risk_per_trade_pct=payload.risk_per_trade_pct,
            fee_bps=payload.fee_bps,
            spread_bps=payload.spread_bps,
            slippage_bps=payload.slippage_bps,
            funding_bps_per_8h=payload.funding_bps_per_8h,
            run_monte_carlo=payload.run_monte_carlo,
            monte_carlo_runs=payload.monte_carlo_runs,
        )
        db.save_backtest_run(
            run_id=result["run_id"],
            strategy_name=payload.strategy.value,
            symbol=payload.symbol.upper(),
            timeframe=payload.timeframe,
            metrics=result["metrics"],
            equity_curve=result["equity_curve"],
        )
        return result

    # --- Encrypted Broker Credential Vault ---
    @router.post("/brokers/credentials")
    def store_broker_credentials(
        payload: BrokerCredentialRequest, user: Dict[str, Any] = Depends(get_current_user)
    ) -> Dict[str, Any]:
        if payload.permissions.get("withdraw_allowed"):
            raise HTTPException(
                status_code=400,
                detail="Security policy violation: withdrawal-enabled API keys are prohibited.",
            )
        encrypted = vault.encrypt(
            json.dumps(
                {
                    "api_key": payload.api_key,
                    "api_secret": payload.api_secret,
                    "server": payload.server,
                    "bridge_url": payload.bridge_url,
                }
            )
        )
        masked = mask_account_id(payload.account_id)
        db.save_encrypted_credential(
            broker_name=payload.broker_name.upper(),
            trading_mode=payload.trading_mode.value,
            account_id_masked=masked,
            encrypted_payload=encrypted,
            permissions=payload.permissions,
        )
        db.log_audit(
            "BROKER_CREDENTIALS_STORED",
            user["sub"],
            payload.trading_mode.value,
            {"broker": payload.broker_name.upper(), "account_id_masked": masked},
        )
        return {"stored": True, "broker": payload.broker_name.upper(), "mode": payload.trading_mode.value, "account_id_masked": masked}

    # --- Notifications & Audit Logs ---
    @router.get("/notifications")
    def list_notifications(limit: int = Query(50, ge=1, le=200)) -> Dict[str, Any]:
        return {"notifications": notifications.list_recent(limit=limit)}

    @router.get("/audit-logs")
    def list_audit_logs(
        limit: int = Query(100, ge=1, le=500),
        _: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        return {"audit_logs": db.list_audit_logs(limit=limit)}

    # --- Real-Time WebSocket Stream ---
    @router.websocket("/ws/stream")
    async def websocket_stream(ws: WebSocket) -> None:
        await ws.accept()
        try:
            await ws.send_json({"type": "STATUS", "payload": mode_ctrl.get_status()})
            while True:
                msg = await ws.receive_text()
                if msg.strip().lower() == "ping":
                    await ws.send_json({"type": "PONG", "payload": mode_ctrl.get_status()})
        except WebSocketDisconnect:
            return

    return router
