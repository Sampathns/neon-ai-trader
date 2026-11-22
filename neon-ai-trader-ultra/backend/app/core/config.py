"""Environment-based configuration with strict DEMO/REAL credential isolation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class BrokerCredentialConfig:
    """Isolated credential bundle for a single broker and a single mode."""

    broker_name: str
    mode: str  # "DEMO" or "REAL"
    api_key: str = ""
    api_secret: str = ""
    account_id: str = ""
    server: str = ""
    base_url: str = ""
    bridge_url: str = ""
    bridge_token: str = ""

    @property
    def is_configured(self) -> bool:
        if self.broker_name == "PAPER":
            return True
        if self.broker_name == "MT5":
            return bool(self.account_id and (self.server or self.bridge_url))
        if self.broker_name == "BINANCE":
            return bool(self.api_key and self.api_secret)
        return bool(self.api_key)


@dataclass
class RiskConfig:
    """Conservative default risk configuration enforced on the backend."""

    max_risk_per_trade_pct: float = 0.5
    daily_loss_limit_pct: float = 2.0
    weekly_loss_limit_pct: float = 5.0
    max_drawdown_pct: float = 10.0
    max_open_positions: int = 5
    max_portfolio_exposure_pct: float = 25.0
    max_correlated_exposure_pct: float = 12.0
    max_spread_bps: float = 25.0
    max_slippage_bps: float = 20.0
    max_leverage: float = 5.0
    max_margin_utilization_pct: float = 40.0
    consecutive_loss_limit: int = 3
    min_risk_reward_ratio: float = 1.5
    allow_martingale: bool = False  # Permanently prohibited
    allow_loss_doubling: bool = False  # Permanently prohibited
    allow_uncontrolled_grid: bool = False  # Permanently prohibited


@dataclass
class Settings:
    """Application settings loaded strictly from environment variables."""

    app_name: str = "NEON AI TRADER ULTRA"
    app_version: str = "1.0.0-ultra"
    environment: str = field(default_factory=lambda: os.getenv("NEON_ENV", "development"))
    database_url: str = field(
        default_factory=lambda: os.getenv("NEON_DATABASE_URL", "sqlite:///./neon_trader.db")
    )
    secret_key: str = field(
        default_factory=lambda: os.getenv("NEON_SECRET_KEY", "dev-only-change-in-production-32bytes!")
    )
    encryption_key: str = field(
        default_factory=lambda: os.getenv("NEON_ENCRYPTION_KEY", "")
    )
    cors_origins: List[str] = field(
        default_factory=lambda: [
            origin.strip()
            for origin in os.getenv(
                "NEON_CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
            ).split(",")
            if origin.strip()
        ]
    )
    max_data_age_seconds: int = field(
        default_factory=lambda: int(os.getenv("NEON_MAX_DATA_AGE_SECONDS", "60"))
    )
    paper_initial_balance: float = field(
        default_factory=lambda: float(os.getenv("NEON_PAPER_INITIAL_BALANCE", "100000.0"))
    )
    paper_commission_bps: float = field(
        default_factory=lambda: float(os.getenv("NEON_PAPER_COMMISSION_BPS", "6.0"))
    )
    paper_slippage_bps: float = field(
        default_factory=lambda: float(os.getenv("NEON_PAPER_SLIPPAGE_BPS", "3.0"))
    )
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("NEON_TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("NEON_TELEGRAM_CHAT_ID", ""))
    smtp_host: str = field(default_factory=lambda: os.getenv("NEON_SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("NEON_SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: os.getenv("NEON_SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("NEON_SMTP_PASSWORD", ""))
    alert_email_to: str = field(default_factory=lambda: os.getenv("NEON_ALERT_EMAIL_TO", ""))

    # Strictly separated DEMO vs REAL broker credentials
    demo_credentials: Dict[str, BrokerCredentialConfig] = field(default_factory=dict)
    real_credentials: Dict[str, BrokerCredentialConfig] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.demo_credentials:
            self.demo_credentials = {
                "PAPER": BrokerCredentialConfig(
                    broker_name="PAPER",
                    mode="DEMO",
                    account_id="PAPER-DEMO-0001",
                ),
                "MT5": BrokerCredentialConfig(
                    broker_name="MT5",
                    mode="DEMO",
                    account_id=os.getenv("NEON_MT5_DEMO_LOGIN", ""),
                    api_secret=os.getenv("NEON_MT5_DEMO_PASSWORD", ""),
                    server=os.getenv("NEON_MT5_DEMO_SERVER", ""),
                    bridge_url=os.getenv("NEON_MT5_DEMO_BRIDGE_URL", ""),
                    bridge_token=os.getenv("NEON_MT5_DEMO_BRIDGE_TOKEN", ""),
                ),
                "BINANCE": BrokerCredentialConfig(
                    broker_name="BINANCE",
                    mode="DEMO",
                    api_key=os.getenv("NEON_BINANCE_TESTNET_API_KEY", ""),
                    api_secret=os.getenv("NEON_BINANCE_TESTNET_API_SECRET", ""),
                    account_id=os.getenv("NEON_BINANCE_TESTNET_ACCOUNT_ID", "BINANCE-TESTNET"),
                    base_url=os.getenv(
                        "NEON_BINANCE_TESTNET_BASE_URL", "https://testnet.binance.vision"
                    ),
                ),
            }
        if not self.real_credentials:
            self.real_credentials = {
                "MT5": BrokerCredentialConfig(
                    broker_name="MT5",
                    mode="REAL",
                    account_id=os.getenv("NEON_MT5_LIVE_LOGIN", ""),
                    api_secret=os.getenv("NEON_MT5_LIVE_PASSWORD", ""),
                    server=os.getenv("NEON_MT5_LIVE_SERVER", ""),
                    bridge_url=os.getenv("NEON_MT5_LIVE_BRIDGE_URL", ""),
                    bridge_token=os.getenv("NEON_MT5_LIVE_BRIDGE_TOKEN", ""),
                ),
                "BINANCE": BrokerCredentialConfig(
                    broker_name="BINANCE",
                    mode="REAL",
                    api_key=os.getenv("NEON_BINANCE_LIVE_API_KEY", ""),
                    api_secret=os.getenv("NEON_BINANCE_LIVE_API_SECRET", ""),
                    account_id=os.getenv("NEON_BINANCE_LIVE_ACCOUNT_ID", ""),
                    base_url=os.getenv("NEON_BINANCE_LIVE_BASE_URL", "https://api.binance.com"),
                ),
            }

    def get_credentials(self, mode: str, broker_name: str) -> BrokerCredentialConfig:
        """Retrieve credentials strictly scoped to the requested mode."""
        bucket = self.demo_credentials if mode == "DEMO" else self.real_credentials
        if broker_name not in bucket:
            raise KeyError(f"Broker '{broker_name}' is not registered for mode '{mode}'")
        cred = bucket[broker_name]
        if cred.mode != mode:
            raise ValueError("Credential mode isolation violation detected")
        return cred


def load_settings() -> Settings:
    return Settings()
