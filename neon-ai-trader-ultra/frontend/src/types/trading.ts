export type TradingMode = "DEMO" | "REAL";

export interface ModeStatus {
  current_mode: TradingMode;
  real_trading_enabled: boolean;
  auto_trading_enabled: boolean;
  ai_scanner_running: boolean;
  emergency_stop_active: boolean;
  active_broker: string;
  authorized_by: string | null;
  authorized_at: string | null;
  account_id_masked: string;
  balance: number;
  equity: number;
  available_margin: number;
  used_margin: number;
  open_positions_count: number;
  current_exposure: number;
  trading_permissions: Record<string, unknown>;
  connection_health: {
    broker: string;
    mode: string;
    status: string;
    reason?: string;
    data_status?: string;
  };
  strategies: Record<string, boolean>;
}

export interface ScannerItem {
  market: string;
  symbol: string;
  current_price: number;
  volume_24h: number;
  trend: string;
  classification: string;
  confidence_estimate: number;
  risk_reward_ratio: number;
  market_regime: string;
  data_status: string;
  analysis_time: string;
  signal_id: string;
}

export interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface SignalDetail {
  id: string;
  symbol: string;
  asset_class: string;
  classification: string;
  direction: string;
  current_price: number;
  entry_zone: [number, number];
  stop_loss: number;
  take_profit_levels: number[];
  risk_reward_ratio: number;
  market_regime: string;
  market_structure_explanation: string;
  data_status: string;
  data_freshness_seconds: number;
  confidence_estimate: number;
  historical_win_rate: number;
  estimated_probability: number;
  bullish_factors: string[];
  bearish_factors: string[];
  risk_conditions: string[];
  invalidation_conditions: string[];
  supporting_indicators: Record<string, any>;
  fundamental_context: Record<string, any>;
  news_context: Record<string, any>;
}

export interface PositionRecord {
  id: string;
  trading_mode: TradingMode;
  symbol: string;
  side: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  stop_loss: number | null;
  take_profit: number | null;
  unrealized_pnl: number;
  realized_pnl: number;
  margin_used: number;
  status: string;
  strategy_name: string | null;
}

export interface BacktestResult {
  run_id: string;
  metrics: {
    symbol: string;
    timeframe: string;
    strategy: string;
    final_equity: number;
    net_profit: number;
    gross_profit: number;
    gross_loss: number;
    win_rate: number;
    profit_factor: number;
    average_win: number;
    average_loss: number;
    max_drawdown_pct: number;
    sharpe_ratio: number;
    sortino_ratio: number;
    total_trades: number;
    risk_reward_ratio: number;
    trading_fees: number;
    walk_forward_oos: { oos_trades: number; oos_net_profit: number; oos_win_rate: number };
    monte_carlo: Record<string, number>;
    disclaimer: string;
  };
  equity_curve: { timestamp: string; equity: number; drawdown_pct: number }[];
}

export interface NotificationItem {
  id: string;
  category: string;
  severity: string;
  title: string;
  message: string;
  created_at: string;
}
