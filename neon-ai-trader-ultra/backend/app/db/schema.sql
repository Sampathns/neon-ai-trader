-- NEON AI TRADER ULTRA — Relational Database Schema
-- Compatible with SQLite (local development) and PostgreSQL (production).

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'trader',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS broker_credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    broker_name TEXT NOT NULL,
    trading_mode TEXT NOT NULL CHECK (trading_mode IN ('DEMO', 'REAL')),
    account_id_masked TEXT NOT NULL,
    encrypted_payload TEXT NOT NULL,
    permissions_json TEXT NOT NULL DEFAULT '{}',
    is_active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    UNIQUE(broker_name, trading_mode)
);

CREATE TABLE IF NOT EXISTS trading_mode_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_mode TEXT NOT NULL CHECK (current_mode IN ('DEMO', 'REAL')) DEFAULT 'DEMO',
    real_trading_enabled INTEGER NOT NULL DEFAULT 0,
    auto_trading_enabled INTEGER NOT NULL DEFAULT 0,
    ai_scanner_running INTEGER NOT NULL DEFAULT 0,
    emergency_stop_active INTEGER NOT NULL DEFAULT 0,
    active_broker TEXT NOT NULL DEFAULT 'PAPER',
    authorized_by TEXT,
    authorized_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_configurations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trading_mode TEXT NOT NULL UNIQUE CHECK (trading_mode IN ('DEMO', 'REAL')),
    config_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    classification TEXT NOT NULL,
    direction TEXT NOT NULL,
    current_price REAL NOT NULL,
    entry_low REAL NOT NULL,
    entry_high REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit_1 REAL NOT NULL,
    take_profit_2 REAL NOT NULL,
    risk_reward REAL NOT NULL,
    confidence_score REAL NOT NULL,
    historical_win_rate REAL,
    estimated_probability REAL,
    regime TEXT NOT NULL,
    data_status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    trading_mode TEXT NOT NULL CHECK (trading_mode IN ('DEMO', 'REAL')),
    broker_name TEXT NOT NULL,
    account_id_masked TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    quantity REAL NOT NULL,
    requested_price REAL,
    filled_price REAL,
    stop_loss REAL,
    take_profit REAL,
    status TEXT NOT NULL,
    broker_order_id TEXT,
    commission REAL NOT NULL DEFAULT 0.0,
    slippage_bps REAL NOT NULL DEFAULT 0.0,
    strategy_name TEXT,
    signal_id TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY,
    trading_mode TEXT NOT NULL CHECK (trading_mode IN ('DEMO', 'REAL')),
    broker_name TEXT NOT NULL,
    account_id_masked TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    entry_price REAL NOT NULL,
    current_price REAL NOT NULL,
    stop_loss REAL,
    take_profit REAL,
    unrealized_pnl REAL NOT NULL DEFAULT 0.0,
    realized_pnl REAL NOT NULL DEFAULT 0.0,
    margin_used REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL CHECK (status IN ('OPEN', 'CLOSED')),
    strategy_name TEXT,
    opened_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    trading_mode TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id TEXT PRIMARY KEY,
    strategy_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    equity_curve_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
