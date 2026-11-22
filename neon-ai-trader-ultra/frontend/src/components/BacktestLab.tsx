import React, { useState } from "react";
import { api } from "../services/api";
import type { BacktestResult } from "../types/trading";

export const BacktestLab: React.FC = () => {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [strategy, setStrategy] = useState("TREND_FOLLOWING");
  const [timeframe, setTimeframe] = useState("1h");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.runBacktest({
        symbol,
        timeframe,
        strategy,
        initial_capital: 100000,
      });
      setResult(res);
    } catch (err: any) {
      setError(err.message || "Backtest failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="panel">
      <div className="panel-header">
        <span className="panel-title">BACKTESTING & STRATEGY LAB</span>
        <span className="badge badge-purple">WALK-FORWARD + MONTE CARLO</span>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 14 }}>
        <select className="input-field" style={{ width: 150, marginTop: 0 }} value={symbol} onChange={(e) => setSymbol(e.target.value)}>
          <option value="BTCUSDT">BTCUSDT</option>
          <option value="ETHUSDT">ETHUSDT</option>
          <option value="EURUSD">EURUSD</option>
          <option value="XAUUSD">XAUUSD</option>
          <option value="US500">US500</option>
        </select>
        <select className="input-field" style={{ width: 190, marginTop: 0 }} value={strategy} onChange={(e) => setStrategy(e.target.value)}>
          <option value="TREND_FOLLOWING">TREND_FOLLOWING</option>
          <option value="BREAKOUT">BREAKOUT</option>
          <option value="PULLBACK">PULLBACK</option>
          <option value="MOMENTUM">MOMENTUM</option>
          <option value="MEAN_REVERSION">MEAN_REVERSION</option>
          <option value="VOLATILITY">VOLATILITY</option>
          <option value="MARKET_STRUCTURE">MARKET_STRUCTURE</option>
        </select>
        <select className="input-field" style={{ width: 100, marginTop: 0 }} value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
          <option value="15m">15m</option>
          <option value="1h">1h</option>
          <option value="4h">4h</option>
          <option value="1d">1d</option>
        </select>
        <button className="btn btn-demo-active" onClick={run} disabled={loading}>
          {loading ? "RUNNING..." : "RUN BACKTEST"}
        </button>
      </div>

      {error && <div style={{ color: "#ff5c77", marginBottom: 10 }}>{error}</div>}

      {result && (
        <div>
          <div className="kpi-grid">
            <div className="kpi-card">
              <div className="kpi-label">Net Profit</div>
              <div className="kpi-value" style={{ color: result.metrics.net_profit >= 0 ? "#00ff9d" : "#ff1e42" }}>
                ${result.metrics.net_profit.toLocaleString()}
              </div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Win Rate / Profit Factor</div>
              <div className="kpi-value">
                {(result.metrics.win_rate * 100).toFixed(1)}% · {result.metrics.profit_factor.toFixed(2)}
              </div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Max Drawdown</div>
              <div className="kpi-value" style={{ color: "#ff1e42" }}>
                {result.metrics.max_drawdown_pct.toFixed(2)}%
              </div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Sharpe / Sortino</div>
              <div className="kpi-value">
                {result.metrics.sharpe_ratio.toFixed(2)} / {result.metrics.sortino_ratio.toFixed(2)}
              </div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Total Trades / Fees</div>
              <div className="kpi-value">
                {result.metrics.total_trades} · ${result.metrics.trading_fees.toFixed(2)}
              </div>
            </div>
          </div>
          <p style={{ marginTop: 10, fontSize: "0.75rem", color: "#8b93a7" }}>
            {result.metrics.disclaimer}
          </p>
        </div>
      )}
    </section>
  );
};
