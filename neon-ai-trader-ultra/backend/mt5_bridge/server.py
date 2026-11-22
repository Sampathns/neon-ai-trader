"""Dedicated Windows MetaTrader 5 HTTP Bridge Service for Linux/Docker backend deployments."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

BRIDGE_TOKEN = os.getenv("NEON_MT5_BRIDGE_TOKEN", "")
MT5_LOGIN = os.getenv("NEON_MT5_LOGIN", "")
MT5_PASSWORD = os.getenv("NEON_MT5_PASSWORD", "")
MT5_SERVER = os.getenv("NEON_MT5_SERVER", "")

bridge_app = FastAPI(title="NEON MT5 Windows Bridge", version="1.0.0")


def verify_bridge_token(x_mt5_bridge_token: Optional[str] = Header(default=None)) -> None:
    if BRIDGE_TOKEN and x_mt5_bridge_token != BRIDGE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid MT5 bridge token.")


def _get_mt5() -> Any:
    try:
        import MetaTrader5 as mt5  # type: ignore[import-not-found]
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="MetaTrader5 Python package is unavailable. Run this bridge on Windows with MT5 installed.",
        ) from exc
    if not mt5.initialize(login=int(MT5_LOGIN), password=MT5_PASSWORD, server=MT5_SERVER):
        raise HTTPException(status_code=503, detail=f"MT5 initialize failed: {mt5.last_error()}")
    return mt5


class BridgeOrderRequest(BaseModel):
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    client_order_id: str


@bridge_app.get("/health", dependencies=[Depends(verify_bridge_token)])
def bridge_health() -> Dict[str, Any]:
    mt5 = _get_mt5()
    info = mt5.terminal_info()
    return {
        "status": "CONNECTED" if info and info.connected else "DISCONNECTED",
        "trade_allowed": bool(info.trade_allowed) if info else False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@bridge_app.get("/account", dependencies=[Depends(verify_bridge_token)])
def bridge_account() -> Dict[str, Any]:
    mt5 = _get_mt5()
    acc = mt5.account_info()
    if acc is None:
        raise HTTPException(status_code=503, detail="Failed to retrieve MT5 account info.")
    return {
        "balance": float(acc.balance),
        "equity": float(acc.equity),
        "available_margin": float(acc.margin_free),
        "used_margin": float(acc.margin),
        "leverage": int(acc.leverage),
        "permissions": {"trade_allowed": bool(acc.trade_allowed), "withdraw_allowed": False},
    }


@bridge_app.get("/ticker/{symbol}", dependencies=[Depends(verify_bridge_token)])
def bridge_ticker(symbol: str) -> Dict[str, Any]:
    mt5 = _get_mt5()
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise HTTPException(status_code=404, detail=f"Ticker unavailable for {symbol}")
    return {
        "symbol": symbol,
        "bid": float(tick.bid),
        "ask": float(tick.ask),
        "last": float(tick.last or (tick.bid + tick.ask) / 2.0),
        "volume": float(tick.volume),
        "timestamp": datetime.fromtimestamp(tick.time, tz=timezone.utc).isoformat(),
    }


@bridge_app.post("/orders", dependencies=[Depends(verify_bridge_token)])
def bridge_order(req: BridgeOrderRequest) -> Dict[str, Any]:
    mt5 = _get_mt5()
    tick = mt5.symbol_info_tick(req.symbol)
    if tick is None:
        raise HTTPException(status_code=400, detail=f"Symbol {req.symbol} not available.")
    order_type = mt5.ORDER_TYPE_BUY if req.side.upper() == "BUY" else mt5.ORDER_TYPE_SELL
    px = tick.ask if req.side.upper() == "BUY" else tick.bid
    payload = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": req.symbol,
        "volume": float(req.quantity),
        "type": order_type,
        "price": float(px),
        "sl": float(req.stop_loss or 0.0),
        "tp": float(req.take_profit or 0.0),
        "deviation": 20,
        "comment": req.client_order_id[:28],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(payload)
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        return {
            "broker_order_id": "",
            "status": "REJECTED",
            "error_message": f"MT5 retcode={getattr(res, 'retcode', 'NONE')}",
        }
    return {
        "broker_order_id": str(res.order),
        "status": "FILLED",
        "filled_price": float(res.price),
        "filled_quantity": float(res.volume),
    }
