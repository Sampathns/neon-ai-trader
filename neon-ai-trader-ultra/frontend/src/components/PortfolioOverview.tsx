import React from "react";
import type { ModeStatus, PositionRecord } from "../types/trading";

interface Props {
  status: ModeStatus;
  positions: PositionRecord[];
}

export const PortfolioOverview: React.FC<Props> = ({ status, positions }) => {
  const floatingPnl = positions.reduce((acc, p) => acc + (p.unrealized_pnl || 0), 0);

  return (
    <section className="panel">
      <div className="panel-header">
        <span className="panel-title">PORTFOLIO & RISK TELEMETRY ({status.current_mode})</span>
        <span className="badge badge-cyan">EXPOSURE: ${status.current_exposure.toLocaleString()}</span>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 14 }}>
        <div className="kpi-card">
          <div className="kpi-label">Account Equity</div>
          <div className="kpi-value" style={{ color: "#00f5ff" }}>${status.equity.toLocaleString()}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Available Balance</div>
          <div className="kpi-value">${status.balance.toLocaleString()}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Available Margin</div>
          <div className="kpi-value">${status.available_margin.toLocaleString()}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Floating P/L</div>
          <div className="kpi-value" style={{ color: floatingPnl >= 0 ? "#00ff9d" : "#ff1e42" }}>
            {floatingPnl >= 0 ? "+" : ""}${floatingPnl.toFixed(2)}
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Open Positions</div>
          <div className="kpi-value">{positions.length}</div>
        </div>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table className="neon-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Side</th>
              <th>Qty</th>
              <th>Entry</th>
              <th>Current</th>
              <th>SL / TP</th>
              <th>Floating P/L</th>
              <th>Margin</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {positions.length === 0 ? (
              <tr>
                <td colSpan={9} style={{ color: "#8b93a7", textAlign: "center" }}>
                  No open positions in {status.current_mode} mode.
                </td>
              </tr>
            ) : (
              positions.map((p) => (
                <tr key={p.id}>
                  <td style={{ color: "#00f5ff" }}>{p.symbol}</td>
                  <td>{p.side}</td>
                  <td>{p.quantity}</td>
                  <td>{p.entry_price}</td>
                  <td>{p.current_price}</td>
                  <td>{p.stop_loss ?? "-"} / {p.take_profit ?? "-"}</td>
                  <td style={{ color: p.unrealized_pnl >= 0 ? "#00ff9d" : "#ff1e42" }}>
                    {p.unrealized_pnl.toFixed(2)}
                  </td>
                  <td>${p.margin_used.toFixed(2)}</td>
                  <td>{p.status}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
};
