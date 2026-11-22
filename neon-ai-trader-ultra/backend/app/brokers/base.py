"""Unified Broker & Exchange Connector Interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.enums import AssetClass, DataFeedStatus


@dataclass
class ContractSpec:
    symbol: str
    broker_symbol: str
    asset_class: AssetClass
    min_volume: float = 0.001
    max_volume: float = 1000.0
    volume_step: float = 0.001
    tick_size: float = 0.01
    contract_size: float = 1.0
    trading_allowed: bool = True
    market_open: bool = True


@dataclass
class TickerQuote:
    symbol: str
    bid: float
    ask: float
    last: float
    volume_24h: float
    timestamp: str
    data_status: DataFeedStatus
    spread_bps: float = 0.0


@dataclass
class BrokerOrderResult:
    broker_order_id: str
    status: str
    filled_price: Optional[float] = None
    filled_quantity: float = 0.0
    commission: float = 0.0
    slippage_bps: float = 0.0
    error_message: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


class BrokerConnector(ABC):
    """Abstract base class for all broker and exchange connectors."""

    broker_name: str
    trading_mode: str  # Strictly "DEMO" or "REAL"
    account_id: str

    @abstractmethod
    def connect(self) -> Dict[str, Any]:
        """Establish connection and validate permissions."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close active connection cleanly."""

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Return connection status, latency, and heartbeat timestamp."""

    @abstractmethod
    def get_account_info(self) -> Dict[str, Any]:
        """Return balance, equity, margin, masked account ID, and permissions."""

    @abstractmethod
    def list_symbols(self) -> List[ContractSpec]:
        """Discover tradable symbols and contract specifications."""

    @abstractmethod
    def get_ticker(self, symbol: str) -> Optional[TickerQuote]:
        """Retrieve latest quote with timestamp and explicit data status."""

    @abstractmethod
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
        """Retrieve OHLCV candles with timestamps."""

    @abstractmethod
    def get_order_book(self, symbol: str, depth: int = 10) -> Dict[str, Any]:
        """Retrieve market depth / order book where supported."""

    @abstractmethod
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
        """Submit order to broker or paper engine."""

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel a pending order."""

    @abstractmethod
    def get_order_status(self, broker_order_id: str) -> Optional[Dict[str, Any]]:
        """Reconcile an existing order's state directly with the broker."""

    @abstractmethod
    def close_position(self, position_id: str) -> bool:
        """Close an open position on the broker."""
