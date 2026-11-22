"""Pydantic API schemas for NEON AI TRADER ULTRA."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.enums import OrderSide, OrderType, StrategyType, TradingMode


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class ModeSwitchRequest(BaseModel):
    target_mode: TradingMode
    broker_name: Optional[str] = None
    acknowledge_open_positions: bool = False


class EnableRealTradingRequest(BaseModel):
    broker_name: str
    verified_account_last4: str = Field(..., min_length=2, max_length=16)
    confirmation_phrase: str
    risk_acknowledged: bool = False


class CloseAllPositionsRequest(BaseModel):
    confirmation_phrase: str


class OrderRequest(BaseModel):
    symbol: str
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    quantity: Optional[float] = None
    entry_price: Optional[float] = None
    stop_loss: float
    take_profit: float
    strategy_name: str = "MANUAL"
    signal_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    requested_leverage: float = 1.0


class RiskConfigUpdate(BaseModel):
    max_risk_per_trade_pct: float = Field(0.5, gt=0, le=5.0)
    daily_loss_limit_pct: float = Field(2.0, gt=0, le=15.0)
    weekly_loss_limit_pct: float = Field(5.0, gt=0, le=25.0)
    max_drawdown_pct: float = Field(10.0, gt=0, le=40.0)
    max_open_positions: int = Field(5, ge=1, le=50)
    max_portfolio_exposure_pct: float = Field(25.0, gt=0, le=100.0)
    max_correlated_exposure_pct: float = Field(12.0, gt=0, le=50.0)
    max_spread_bps: float = Field(25.0, gt=0, le=200.0)
    max_slippage_bps: float = Field(20.0, gt=0, le=200.0)
    max_leverage: float = Field(5.0, ge=1.0, le=20.0)
    max_margin_utilization_pct: float = Field(40.0, gt=0, le=80.0)
    consecutive_loss_limit: int = Field(3, ge=1, le=10)
    min_risk_reward_ratio: float = Field(1.5, ge=1.0, le=10.0)


class BacktestRequest(BaseModel):
    symbol: str = "BTCUSDT"
    timeframe: str = "1h"
    strategy: StrategyType = StrategyType.TREND_FOLLOWING
    initial_capital: float = Field(100000.0, gt=0)
    risk_per_trade_pct: float = Field(0.5, gt=0, le=5.0)
    fee_bps: float = Field(6.0, ge=0)
    spread_bps: float = Field(4.0, ge=0)
    slippage_bps: float = Field(3.0, ge=0)
    funding_bps_per_8h: float = Field(1.0, ge=0)
    bars: int = Field(300, ge=100, le=2000)
    run_monte_carlo: bool = True
    monte_carlo_runs: int = Field(200, ge=20, le=1000)


class StrategyToggleRequest(BaseModel):
    strategy: StrategyType
    enabled: bool


class BrokerCredentialRequest(BaseModel):
    broker_name: str
    trading_mode: TradingMode
    account_id: str
    api_key: str = ""
    api_secret: str = ""
    server: str = ""
    bridge_url: str = ""
    permissions: Dict[str, Any] = Field(default_factory=dict)
