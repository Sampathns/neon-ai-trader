"""FastAPI application entrypoint and dependency container for NEON AI TRADER ULTRA."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.analysis.fundamentals_news import FundamentalAnalyzer, NewsIntelligenceEngine
from app.analysis.signal_engine import AISignalEngine
from app.api.routes import build_router
from app.backtesting.engine import BacktestingEngine
from app.brokers.registry import BrokerRegistry
from app.core.config import Settings, load_settings
from app.core.mode_controller import TradingModeController
from app.core.security import SecretVault
from app.db.database import Database
from app.market_data.engine import MarketDataEngine
from app.notifications.service import NotificationService
from app.risk.engine import RiskManagementEngine
from app.trading.execution_engine import TradeExecutionEngine
from app.trading.strategies import StrategyEngine


def create_app(
    settings: Optional[Settings] = None,
    db_path: Optional[str] = None,
) -> FastAPI:
    cfg = settings or load_settings()
    resolved_db = db_path or cfg.database_url.replace("sqlite:///", "")
    db = Database(db_path=resolved_db)
    vault = SecretVault(cfg.encryption_key or cfg.secret_key)
    registry = BrokerRegistry(cfg)
    notifications = NotificationService(db, cfg)
    mode_controller = TradingModeController(db, registry, notifications)
    data_engine = MarketDataEngine(max_data_age_seconds=cfg.max_data_age_seconds)
    news_engine = NewsIntelligenceEngine()
    fundamental_analyzer = FundamentalAnalyzer()
    signal_engine = AISignalEngine(data_engine, news_engine, fundamental_analyzer)
    strategy_engine = StrategyEngine()
    risk_engine = RiskManagementEngine()
    execution_engine = TradeExecutionEngine(
        db=db,
        broker_registry=registry,
        mode_controller=mode_controller,
        risk_engine=risk_engine,
        data_engine=data_engine,
        notifications=notifications,
    )
    backtester = BacktestingEngine()

    container: Dict[str, Any] = {
        "settings": cfg,
        "db": db,
        "vault": vault,
        "registry": registry,
        "notifications": notifications,
        "mode_controller": mode_controller,
        "data_engine": data_engine,
        "news_engine": news_engine,
        "fundamental_analyzer": fundamental_analyzer,
        "signal_engine": signal_engine,
        "strategy_engine": strategy_engine,
        "risk_engine": risk_engine,
        "execution_engine": execution_engine,
        "backtester": backtester,
    }

    app = FastAPI(
        title=cfg.app_name,
        version=cfg.app_version,
        description="Modular Autonomous Multi-Market AI Trading Platform (DEMO default; REAL requires 7-step authorization).",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.container = container
    app.include_router(build_router(container))
    return app


app = create_app()
