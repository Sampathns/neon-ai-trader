"""Unified Broker Registry & Expandable Market Connector Interfaces."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.brokers.base import BrokerConnector, BrokerOrderResult, ContractSpec, TickerQuote
from app.brokers.binance_connector import BinanceConnector
from app.brokers.mt5_connector import MT5Connector
from app.brokers.paper_broker import PaperBrokerConnector
from app.core.config import Settings
from app.core.enums import AssetClass, ConnectionStatus, DataFeedStatus


class UnconfiguredMarketAdapter(BrokerConnector):
    """
    Explicitly marks expandable market connectors (Equities, Futures, Options,
    Bonds, Commodities, Energy, ETFs, Additional FX/Crypto) as UNCONFIGURED
    until an official supported provider is configured.
    """

    def __init__(self, broker_name: str, trading_mode: str, supported_assets: List[AssetClass]) -> None:
        self.broker_name = broker_name
        self.trading_mode = trading_mode
        self.account_id = ""
        self.supported_assets = supported_assets

    def connect(self) -> Dict[str, Any]:
        return self.health_check()

    def disconnect(self) -> None:
        return None

    def health_check(self) -> Dict[str, Any]:
        return {
            "broker": self.broker_name,
            "mode": self.trading_mode,
            "status": ConnectionStatus.UNCONFIGURED.value,
            "supported_asset_classes": [a.value for a in self.supported_assets],
            "reason": "Provider adapter interface ready; configure official provider credentials to activate.",
        }

    def get_account_info(self) -> Dict[str, Any]:
        return {
            "broker": self.broker_name,
            "mode": self.trading_mode,
            "account_id_masked": "UNCONFIGURED",
            "balance": 0.0,
            "equity": 0.0,
            "available_margin": 0.0,
            "used_margin": 0.0,
            "permissions": {"trade_allowed": False, "withdraw_allowed": False},
        }

    def list_symbols(self) -> List[ContractSpec]:
        return []

    def get_ticker(self, symbol: str) -> Optional[TickerQuote]:
        return None

    def get_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200) -> List[Dict[str, Any]]:
        return []

    def get_order_book(self, symbol: str, depth: int = 10) -> Dict[str, Any]:
        return {"symbol": symbol, "bids": [], "asks": [], "data_status": DataFeedStatus.UNAVAILABLE.value}

    def place_order(self, **kwargs: Any) -> BrokerOrderResult:
        return BrokerOrderResult(
            broker_order_id="",
            status="REJECTED",
            error_message=f"Provider '{self.broker_name}' is not configured.",
        )

    def cancel_order(self, broker_order_id: str) -> bool:
        return False

    def get_order_status(self, broker_order_id: str) -> Optional[Dict[str, Any]]:
        return None

    def close_position(self, position_id: str) -> bool:
        return False


class BrokerRegistry:
    """Maintains strictly isolated DEMO and REAL broker connector pools."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._connectors: Dict[str, Dict[str, BrokerConnector]] = {
            "DEMO": {
                "PAPER": PaperBrokerConnector(
                    initial_balance=settings.paper_initial_balance,
                    commission_bps=settings.paper_commission_bps,
                    slippage_bps=settings.paper_slippage_bps,
                ),
                "MT5": MT5Connector(settings.get_credentials("DEMO", "MT5")),
                "BINANCE": BinanceConnector(settings.get_credentials("DEMO", "BINANCE")),
                "EQUITIES_IBKR": UnconfiguredMarketAdapter(
                    "EQUITIES_IBKR", "DEMO", [AssetClass.EQUITIES, AssetClass.ETFS, AssetClass.OPTIONS, AssetClass.BONDS]
                ),
                "FUTURES_CME": UnconfiguredMarketAdapter(
                    "FUTURES_CME", "DEMO", [AssetClass.FUTURES, AssetClass.COMMODITIES, AssetClass.ENERGY, AssetClass.METALS, AssetClass.INDICES]
                ),
            },
            "REAL": {
                "MT5": MT5Connector(settings.get_credentials("REAL", "MT5")),
                "BINANCE": BinanceConnector(settings.get_credentials("REAL", "BINANCE")),
                "EQUITIES_IBKR": UnconfiguredMarketAdapter(
                    "EQUITIES_IBKR", "REAL", [AssetClass.EQUITIES, AssetClass.ETFS, AssetClass.OPTIONS, AssetClass.BONDS]
                ),
                "FUTURES_CME": UnconfiguredMarketAdapter(
                    "FUTURES_CME", "REAL", [AssetClass.FUTURES, AssetClass.COMMODITIES, AssetClass.ENERGY, AssetClass.METALS, AssetClass.INDICES]
                ),
            },
        }

    def get_connector(self, trading_mode: str, broker_name: str) -> Optional[BrokerConnector]:
        bucket = self._connectors.get(trading_mode, {})
        connector = bucket.get(broker_name.upper())
        if connector and connector.trading_mode != trading_mode:
            raise ValueError("Fatal broker isolation error: connector mode mismatch.")
        return connector

    def register_connector(self, trading_mode: str, broker_name: str, connector: BrokerConnector) -> None:
        if connector.trading_mode != trading_mode:
            raise ValueError("Cannot register connector under a different trading mode.")
        self._connectors.setdefault(trading_mode, {})[broker_name.upper()] = connector

    def list_health(self, trading_mode: str) -> List[Dict[str, Any]]:
        return [c.health_check() for c in self._connectors.get(trading_mode, {}).values()]
