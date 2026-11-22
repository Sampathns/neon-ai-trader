"""MetaTrader 5 connector supporting native Windows MT5 Python API and remote HTTP Bridge."""

from __future__ import annotations

import platform
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.brokers.base import BrokerConnector, BrokerOrderResult, ContractSpec, TickerQuote
from app.core.config import BrokerCredentialConfig
from app.core.enums import AssetClass, ConnectionStatus, DataFeedStatus
from app.core.security import mask_account_id


class MT5Connector(BrokerConnector):
    """
    MetaTrader 5 Forex & CFD Connector.
    - On Windows with `MetaTrader5` installed: connects natively to the MT5 terminal.
    - On Linux/macOS/Docker: delegates securely over HTTPS to the dedicated `mt5_bridge` service.
    - Strictly isolates DEMO vs REAL credentials and never fabricates broker connections.
    """

    broker_name = "MT5"

    def __init__(self, creds: BrokerCredentialConfig, symbol_suffix: str = "") -> None:
        self.creds = creds
        self.trading_mode = creds.mode
        self.account_id = creds.account_id
        self.symbol_suffix = symbol_suffix
        self._mt5 = None
        self._connected = False
        self._mode_transport = "UNCONFIGURED"
        self._last_error: Optional[str] = None

    def _resolve_symbol(self, symbol: str) -> str:
        clean = symbol.upper()
        if self.symbol_suffix and not clean.endswith(self.symbol_suffix):
            return f"{clean}{self.symbol_suffix}"
        return clean

    def _headers(self) -> Dict[str, str]:
        return {"X-MT5-Bridge-Token": self.creds.bridge_token} if self.creds.bridge_token else {}

    def connect(self) -> Dict[str, Any]:
        if not self.creds.is_configured:
            self._connected = False
            self._last_error = f"MT5 {self.trading_mode} credentials not configured."
            return self.health_check()

        # Prefer HTTP bridge when bridge_url is provided (standard for Linux/Docker backend)
        if self.creds.bridge_url:
            try:
                resp = httpx.get(
                    f"{self.creds.bridge_url.rstrip('/')}/health",
                    headers=self._headers(),
                    timeout=5.0,
                )
                resp.raise_for_status()
                self._connected = True
                self._mode_transport = "BRIDGE"
                self._last_error = None
                return self.health_check()
            except Exception as exc:
                self._connected = False
                self._last_error = f"MT5 bridge connection failed: {exc}"
                return self.health_check()

        # Native Windows MT5 Python package
        if platform.system() != "Windows":
            self._connected = False
            self._last_error = (
                f"Native MetaTrader5 Python module requires Windows (detected {platform.system()}). "
                "Configure NEON_MT5_*_BRIDGE_URL to connect via the dedicated mt5_bridge service."
            )
            return self.health_check()

        try:
            import MetaTrader5 as mt5  # type: ignore[import-not-found]

            if not mt5.initialize(
                login=int(self.creds.account_id),
                password=self.creds.api_secret,
                server=self.creds.server,
            ):
                self._connected = False
                self._last_error = f"MT5 initialize failed: {mt5.last_error()}"
                return self.health_check()
            self._mt5 = mt5
            self._connected = True
            self._mode_transport = "NATIVE_WINDOWS"
            self._last_error = None
        except ImportError:
            self._connected = False
            self._last_error = "MetaTrader5 Python package is not installed."
        return self.health_check()

    def disconnect(self) -> None:
        if self._mt5 is not None:
            try:
                self._mt5.shutdown()
            except Exception:
                pass
        self._connected = False

    def health_check(self) -> Dict[str, Any]:
        if not self.creds.is_configured:
            status = ConnectionStatus.UNCONFIGURED.value
        elif self._connected:
            status = ConnectionStatus.CONNECTED.value
        else:
            status = ConnectionStatus.DISCONNECTED.value
        return {
            "broker": self.broker_name,
            "mode": self.trading_mode,
            "status": status,
            "transport": self._mode_transport,
            "account_id_masked": mask_account_id(self.account_id),
            "os": platform.system(),
            "reason": self._last_error or ("Connected" if self._connected else "Not connected"),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_account_info(self) -> Dict[str, Any]:
        if not self._connected:
            return {
                "broker": self.broker_name,
                "mode": self.trading_mode,
                "account_id_masked": mask_account_id(self.account_id),
                "balance": 0.0,
                "equity": 0.0,
                "available_margin": 0.0,
                "used_margin": 0.0,
                "permissions": {"trade_allowed": False, "withdraw_allowed": False},
            }
        if self._mode_transport == "BRIDGE":
            resp = httpx.get(
                f"{self.creds.bridge_url.rstrip('/')}/account",
                headers=self._headers(),
                timeout=5.0,
            )
            resp.raise_for_status()
            data = resp.json()
            data["account_id_masked"] = mask_account_id(self.account_id)
            return data

        info = self._mt5.account_info()
        return {
            "broker": self.broker_name,
            "mode": self.trading_mode,
            "account_id_masked": mask_account_id(str(info.login)),
            "balance": float(info.balance),
            "equity": float(info.equity),
            "available_margin": float(info.margin_free),
            "used_margin": float(info.margin),
            "leverage": int(info.leverage),
            "permissions": {
                "trade_allowed": bool(info.trade_allowed),
                "trade_expert": bool(info.trade_expert),
                "withdraw_allowed": False,
            },
        }

    def list_symbols(self) -> List[ContractSpec]:
        if not self._connected:
            return []
        if self._mode_transport == "BRIDGE":
            resp = httpx.get(
                f"{self.creds.bridge_url.rstrip('/')}/symbols",
                headers=self._headers(),
                timeout=8.0,
            )
            resp.raise_for_status()
            return [
                ContractSpec(
                    symbol=s["symbol"],
                    broker_symbol=s["broker_symbol"],
                    asset_class=AssetClass.FOREX,
                    min_volume=s.get("min_volume", 0.01),
                    max_volume=s.get("max_volume", 100.0),
                    volume_step=s.get("volume_step", 0.01),
                    tick_size=s.get("tick_size", 0.00001),
                    trading_allowed=s.get("trading_allowed", True),
                )
                for s in resp.json().get("symbols", [])
            ]
        raw = self._mt5.symbols_get() or []
        return [
            ContractSpec(
                symbol=s.name,
                broker_symbol=s.name,
                asset_class=AssetClass.FOREX,
                min_volume=float(s.volume_min),
                max_volume=float(s.volume_max),
                volume_step=float(s.volume_step),
                tick_size=float(s.trade_tick_size),
                trading_allowed=bool(s.trade_mode != 0),
            )
            for s in raw[:100]
        ]

    def get_ticker(self, symbol: str) -> Optional[TickerQuote]:
        if not self._connected:
            return None
        bsym = self._resolve_symbol(symbol)
        if self._mode_transport == "BRIDGE":
            resp = httpx.get(
                f"{self.creds.bridge_url.rstrip('/')}/ticker/{bsym}",
                headers=self._headers(),
                timeout=5.0,
            )
            if resp.status_code != 200:
                return None
            d = resp.json()
            spread_bps = ((d["ask"] - d["bid"]) / d["ask"] * 10000.0) if d["ask"] else 0.0
            return TickerQuote(
                symbol=symbol.upper(),
                bid=d["bid"],
                ask=d["ask"],
                last=d.get("last", (d["bid"] + d["ask"]) / 2.0),
                volume_24h=d.get("volume", 0.0),
                timestamp=d["timestamp"],
                data_status=DataFeedStatus.LIVE,
                spread_bps=round(spread_bps, 2),
            )
        tick = self._mt5.symbol_info_tick(bsym)
        if tick is None:
            return None
        spread_bps = ((tick.ask - tick.bid) / tick.ask * 10000.0) if tick.ask else 0.0
        return TickerQuote(
            symbol=symbol.upper(),
            bid=float(tick.bid),
            ask=float(tick.ask),
            last=float(tick.last or (tick.bid + tick.ask) / 2.0),
            volume_24h=float(tick.volume),
            timestamp=datetime.fromtimestamp(tick.time, tz=timezone.utc).isoformat(),
            data_status=DataFeedStatus.LIVE,
            spread_bps=round(spread_bps, 2),
        )

    def get_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200) -> List[Dict[str, Any]]:
        if not self._connected:
            return []
        bsym = self._resolve_symbol(symbol)
        if self._mode_transport == "BRIDGE":
            resp = httpx.get(
                f"{self.creds.bridge_url.rstrip('/')}/ohlcv/{bsym}",
                params={"timeframe": timeframe, "limit": limit},
                headers=self._headers(),
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json().get("candles", [])
        return []

    def get_order_book(self, symbol: str, depth: int = 10) -> Dict[str, Any]:
        return {
            "symbol": symbol.upper(),
            "bids": [],
            "asks": [],
            "data_status": DataFeedStatus.LIVE.value if self._connected else DataFeedStatus.UNAVAILABLE.value,
        }

    def place_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float],
        stop_loss: Optional[float],
        take_profit: Optional[float],
        client_order_id: str,
    ) -> BrokerOrderResult:
        if not self._connected:
            return BrokerOrderResult(
                broker_order_id="",
                status="REJECTED",
                error_message="MT5 connector is not connected.",
            )
        bsym = self._resolve_symbol(symbol)
        if self._mode_transport == "BRIDGE":
            resp = httpx.post(
                f"{self.creds.bridge_url.rstrip('/')}/orders",
                json={
                    "symbol": bsym,
                    "side": side,
                    "order_type": order_type,
                    "quantity": quantity,
                    "price": price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "client_order_id": client_order_id,
                },
                headers=self._headers(),
                timeout=10.0,
            )
            resp.raise_for_status()
            d = resp.json()
            return BrokerOrderResult(
                broker_order_id=str(d.get("broker_order_id", "")),
                status=d.get("status", "REJECTED"),
                filled_price=d.get("filled_price"),
                filled_quantity=d.get("filled_quantity", 0.0),
                error_message=d.get("error_message"),
                raw=d,
            )
        return BrokerOrderResult(
            broker_order_id="",
            status="REJECTED",
            error_message="Direct Windows MT5 order routing requires active terminal session.",
        )

    def cancel_order(self, broker_order_id: str) -> bool:
        if not self._connected or self._mode_transport != "BRIDGE":
            return False
        resp = httpx.delete(
            f"{self.creds.bridge_url.rstrip('/')}/orders/{broker_order_id}",
            headers=self._headers(),
            timeout=5.0,
        )
        return resp.status_code == 200

    def get_order_status(self, broker_order_id: str) -> Optional[Dict[str, Any]]:
        if not self._connected or self._mode_transport != "BRIDGE":
            return None
        resp = httpx.get(
            f"{self.creds.bridge_url.rstrip('/')}/orders/{broker_order_id}",
            headers=self._headers(),
            timeout=5.0,
        )
        return resp.json() if resp.status_code == 200 else None

    def close_position(self, position_id: str) -> bool:
        if not self._connected or self._mode_transport != "BRIDGE":
            return False
        resp = httpx.post(
            f"{self.creds.bridge_url.rstrip('/')}/positions/{position_id}/close",
            headers=self._headers(),
            timeout=8.0,
        )
        return resp.status_code == 200
