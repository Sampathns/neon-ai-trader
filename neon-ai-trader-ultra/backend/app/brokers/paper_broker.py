"""Realistic Paper-Trading Simulator strictly scoped to DEMO mode."""

from __future__ import annotations

import math
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from app.brokers.base import BrokerConnector, BrokerOrderResult, ContractSpec, TickerQuote
from app.core.enums import AssetClass, ConnectionStatus, DataFeedStatus
from app.core.security import mask_account_id


class PaperBrokerConnector(BrokerConnector):
    """
    DEMO-only simulated broker with realistic commission, spread, slippage,
    margin tracking, and deterministic/repeatable candle feeds clearly labeled SIMULATED.
    """

    broker_name = "PAPER"
    trading_mode = "DEMO"

    DEFAULT_UNIVERSE: Dict[str, Dict[str, Any]] = {
        "BTCUSDT": {"asset_class": AssetClass.CRYPTO, "base_price": 68500.0, "vol": 0.008, "spread_bps": 2.5},
        "ETHUSDT": {"asset_class": AssetClass.CRYPTO, "base_price": 3450.0, "vol": 0.010, "spread_bps": 3.0},
        "EURUSD": {"asset_class": AssetClass.FOREX, "base_price": 1.0845, "vol": 0.0018, "spread_bps": 1.2},
        "GBPUSD": {"asset_class": AssetClass.FOREX, "base_price": 1.2680, "vol": 0.0022, "spread_bps": 1.6},
        "XAUUSD": {"asset_class": AssetClass.METALS, "base_price": 2345.0, "vol": 0.0045, "spread_bps": 3.5},
        "US500": {"asset_class": AssetClass.INDICES, "base_price": 5420.0, "vol": 0.0035, "spread_bps": 2.0},
    }

    def __init__(
        self,
        initial_balance: float = 100000.0,
        commission_bps: float = 6.0,
        slippage_bps: float = 3.0,
        account_id: str = "PAPER-DEMO-0001",
    ) -> None:
        self.account_id = account_id
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.commission_bps = commission_bps
        self.slippage_bps = slippage_bps
        self.connected = True
        self._last_heartbeat = time.time()
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._positions: Dict[str, Dict[str, Any]] = {}
        self._price_overrides: Dict[str, float] = {}
        self._stale_override_seconds: Optional[int] = None
        self._rate_limit_remaining: int = 1200

    def connect(self) -> Dict[str, Any]:
        self.connected = True
        self._last_heartbeat = time.time()
        return self.health_check()

    def disconnect(self) -> None:
        self.connected = False

    def set_simulated_price(self, symbol: str, price: float) -> None:
        self._price_overrides[symbol.upper()] = price

    def set_stale_feed_seconds(self, seconds: Optional[int]) -> None:
        """Testing hook to simulate stale market data feeds."""
        self._stale_override_seconds = seconds

    def health_check(self) -> Dict[str, Any]:
        return {
            "broker": self.broker_name,
            "mode": self.trading_mode,
            "status": ConnectionStatus.CONNECTED.value if self.connected else ConnectionStatus.DISCONNECTED.value,
            "latency_ms": 4.2 if self.connected else None,
            "rate_limit_remaining": self._rate_limit_remaining,
            "last_heartbeat": datetime.fromtimestamp(self._last_heartbeat, tz=timezone.utc).isoformat(),
            "data_status": DataFeedStatus.SIMULATED.value,
            "reason": "Paper simulator active (DEMO only)" if self.connected else "Simulated disconnect",
        }

    def get_account_info(self) -> Dict[str, Any]:
        unrealized = 0.0
        used_margin = 0.0
        for pos in self._positions.values():
            if pos["status"] != "OPEN":
                continue
            ticker = self.get_ticker(pos["symbol"])
            mark = ticker.last if ticker else pos["entry_price"]
            pnl = (
                (mark - pos["entry_price"]) * pos["quantity"]
                if pos["side"] == "BUY"
                else (pos["entry_price"] - mark) * pos["quantity"]
            )
            unrealized += pnl
            used_margin += pos["margin_used"]

        equity = self.balance + unrealized
        return {
            "broker": self.broker_name,
            "mode": self.trading_mode,
            "account_id_masked": mask_account_id(self.account_id),
            "balance": round(self.balance, 2),
            "equity": round(equity, 2),
            "unrealized_pnl": round(unrealized, 2),
            "used_margin": round(used_margin, 2),
            "available_margin": round(max(0.0, equity - used_margin), 2),
            "permissions": {
                "trade_allowed": self.connected,
                "withdraw_allowed": False,
                "paper_only": True,
            },
        }

    def list_symbols(self) -> List[ContractSpec]:
        specs: List[ContractSpec] = []
        for sym, meta in self.DEFAULT_UNIVERSE.items():
            specs.append(
                ContractSpec(
                    symbol=sym,
                    broker_symbol=sym,
                    asset_class=meta["asset_class"],
                    min_volume=0.001,
                    max_volume=500.0,
                    volume_step=0.001,
                    tick_size=0.0001 if meta["asset_class"] == AssetClass.FOREX else 0.01,
                    trading_allowed=True,
                    market_open=True,
                )
            )
        return specs

    def _current_price(self, symbol: str) -> float:
        sym = symbol.upper()
        if sym in self._price_overrides:
            return self._price_overrides[sym]
        meta = self.DEFAULT_UNIVERSE.get(sym)
        if not meta:
            raise ValueError(f"Unsupported symbol '{symbol}' in PaperBrokerConnector")
        # Gentle deterministic oscillation so repeated calls stay realistic without inventing live prices
        t = int(time.time() // 5)
        phase = sum(ord(c) for c in sym) % 31
        drift = math.sin((t + phase) * 0.17) * meta["vol"] * 0.6
        return round(meta["base_price"] * (1.0 + drift), 5)

    def get_ticker(self, symbol: str) -> Optional[TickerQuote]:
        if not self.connected:
            return None
        sym = symbol.upper()
        meta = self.DEFAULT_UNIVERSE.get(sym)
        if not meta:
            return None
        last = self._current_price(sym)
        spread_bps = meta["spread_bps"]
        half_spread = last * (spread_bps / 20000.0)
        ts = datetime.now(timezone.utc)
        if self._stale_override_seconds is not None:
            ts = ts - timedelta(seconds=self._stale_override_seconds)
        return TickerQuote(
            symbol=sym,
            bid=round(last - half_spread, 5),
            ask=round(last + half_spread, 5),
            last=round(last, 5),
            volume_24h=round(12500.0 * (1.0 + (sum(ord(c) for c in sym) % 7) * 0.2), 2),
            timestamp=ts.isoformat(),
            data_status=DataFeedStatus.SIMULATED,
            spread_bps=spread_bps,
        )

    def get_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200) -> List[Dict[str, Any]]:
        if not self.connected:
            return []
        sym = symbol.upper()
        meta = self.DEFAULT_UNIVERSE.get(sym)
        if not meta:
            return []

        tf_minutes = {
            "1m": 1, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "4h": 240, "1d": 1440, "1w": 10080, "1M": 43200,
        }.get(timeframe, 60)

        seed = abs(hash((sym, timeframe))) % (2**32)
        rng = np.random.default_rng(seed)
        base = meta["base_price"]
        vol = meta["vol"] * math.sqrt(tf_minutes / 60.0)
        now = datetime.now(timezone.utc)
        if self._stale_override_seconds is not None:
            now = now - timedelta(seconds=self._stale_override_seconds)

        # Deterministic synthetic series clearly marked SIMULATED for paper/backtest labs
        returns = rng.normal(loc=0.00025, scale=vol, size=limit)
        # Add realistic trend wave
        wave = np.sin(np.linspace(0, 4.5 * np.pi, limit)) * (vol * 0.45)
        closes = base * np.exp(np.cumsum(returns + wave))

        candles: List[Dict[str, Any]] = []
        for i in range(limit):
            c = float(closes[i])
            o = float(closes[i - 1]) if i > 0 else float(base)
            wick = abs(float(rng.normal(0, vol * 0.6))) * c
            h = max(o, c) + wick
            lo = max(1e-6, min(o, c) - wick)
            ts = now - timedelta(minutes=tf_minutes * (limit - 1 - i))
            candles.append(
                {
                    "timestamp": ts.isoformat(),
                    "open": round(o, 5),
                    "high": round(h, 5),
                    "low": round(lo, 5),
                    "close": round(c, 5),
                    "volume": round(float(rng.uniform(150.0, 2500.0)), 2),
                    "data_status": DataFeedStatus.SIMULATED.value,
                }
            )
        return candles

    def get_order_book(self, symbol: str, depth: int = 10) -> Dict[str, Any]:
        ticker = self.get_ticker(symbol)
        if not ticker:
            return {"symbol": symbol, "bids": [], "asks": [], "data_status": DataFeedStatus.UNAVAILABLE.value}
        step = max(ticker.last * 0.0002, 0.0001)
        bids = [[round(ticker.bid - i * step, 5), round(1.5 + i * 0.7, 3)] for i in range(depth)]
        asks = [[round(ticker.ask + i * step, 5), round(1.5 + i * 0.7, 3)] for i in range(depth)]
        return {
            "symbol": symbol.upper(),
            "bids": bids,
            "asks": asks,
            "timestamp": ticker.timestamp,
            "data_status": DataFeedStatus.SIMULATED.value,
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
        if not self.connected:
            return BrokerOrderResult(
                broker_order_id="",
                status="REJECTED",
                error_message="Paper broker is disconnected",
            )
        ticker = self.get_ticker(symbol)
        if not ticker:
            return BrokerOrderResult(
                broker_order_id="",
                status="REJECTED",
                error_message=f"Unknown symbol {symbol}",
            )

        broker_order_id = f"PAPER-{uuid.uuid4().hex[:10].upper()}"
        if order_type == "MARKET":
            ref_price = ticker.ask if side == "BUY" else ticker.bid
            slip_mult = 1.0 + (self.slippage_bps / 10000.0) if side == "BUY" else 1.0 - (self.slippage_bps / 10000.0)
            fill_price = round(ref_price * slip_mult, 5)
            commission = round(fill_price * quantity * (self.commission_bps / 10000.0), 4)
            self.balance -= commission
            self._orders[broker_order_id] = {
                "broker_order_id": broker_order_id,
                "client_order_id": client_order_id,
                "symbol": symbol.upper(),
                "side": side,
                "status": "FILLED",
                "filled_price": fill_price,
                "filled_quantity": quantity,
                "commission": commission,
            }
            self._positions[broker_order_id] = {
                "id": broker_order_id,
                "symbol": symbol.upper(),
                "side": side,
                "quantity": quantity,
                "entry_price": fill_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "margin_used": round((fill_price * quantity) / 2.0, 2),
                "status": "OPEN",
            }
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="FILLED",
                filled_price=fill_price,
                filled_quantity=quantity,
                commission=commission,
                slippage_bps=self.slippage_bps,
            )

        # Pending limit/stop order
        self._orders[broker_order_id] = {
            "broker_order_id": broker_order_id,
            "client_order_id": client_order_id,
            "symbol": symbol.upper(),
            "side": side,
            "status": "SUBMITTED",
            "requested_price": price or ticker.last,
            "filled_quantity": 0.0,
            "commission": 0.0,
        }
        return BrokerOrderResult(
            broker_order_id=broker_order_id,
            status="SUBMITTED",
            filled_price=None,
            filled_quantity=0.0,
            commission=0.0,
            slippage_bps=0.0,
        )

    def cancel_order(self, broker_order_id: str) -> bool:
        order = self._orders.get(broker_order_id)
        if not order or order["status"] not in ("PENDING", "SUBMITTED"):
            return False
        order["status"] = "CANCELLED"
        return True

    def get_order_status(self, broker_order_id: str) -> Optional[Dict[str, Any]]:
        return self._orders.get(broker_order_id)

    def close_position(self, position_id: str) -> bool:
        pos = self._positions.get(position_id)
        if not pos or pos["status"] != "OPEN":
            return False
        ticker = self.get_ticker(pos["symbol"])
        exit_price = ticker.bid if (ticker and pos["side"] == "BUY") else (ticker.ask if ticker else pos["entry_price"])
        pnl = (
            (exit_price - pos["entry_price"]) * pos["quantity"]
            if pos["side"] == "BUY"
            else (pos["entry_price"] - exit_price) * pos["quantity"]
        )
        commission = round(exit_price * pos["quantity"] * (self.commission_bps / 10000.0), 4)
        self.balance += pnl - commission
        pos["status"] = "CLOSED"
        return True
