"""Core enumerations for NEON AI TRADER ULTRA."""

from enum import Enum


class TradingMode(str, Enum):
    DEMO = "DEMO"
    REAL = "REAL"


class AssetClass(str, Enum):
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"
    EQUITIES = "EQUITIES"
    INDICES = "INDICES"
    COMMODITIES = "COMMODITIES"
    METALS = "METALS"
    ENERGY = "ENERGY"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    BONDS = "BONDS"
    ETFS = "ETFS"


class SignalClassification(str, Enum):
    STRONG_BUY = "STRONG BUY"
    BUY = "BUY"
    WAIT = "WAIT"
    SELL = "SELL"
    STRONG_SELL = "STRONG SELL"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class MarketRegime(str, Enum):
    TRENDING_BULLISH = "TRENDING_BULLISH"
    TRENDING_BEARISH = "TRENDING_BEARISH"
    RANGING_CONSOLIDATION = "RANGING_CONSOLIDATION"
    HIGH_VOLATILITY_EXPANSION = "HIGH_VOLATILITY_EXPANSION"
    TREND_EXHAUSTION = "TREND_EXHAUSTION"
    UNKNOWN = "UNKNOWN"


class DataFeedStatus(str, Enum):
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    SIMULATED = "SIMULATED"
    UNAVAILABLE = "UNAVAILABLE"


class ConnectionStatus(str, Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    UNCONFIGURED = "UNCONFIGURED"
    ERROR = "ERROR"


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class StrategyType(str, Enum):
    TREND_FOLLOWING = "TREND_FOLLOWING"
    BREAKOUT = "BREAKOUT"
    PULLBACK = "PULLBACK"
    MOMENTUM = "MOMENTUM"
    MEAN_REVERSION = "MEAN_REVERSION"
    VOLATILITY = "VOLATILITY"
    MARKET_STRUCTURE = "MARKET_STRUCTURE"
