import React from "react";
import type { SignalDetail } from "../types/trading";

interface Props {
  signal: SignalDetail | null;
}

export const AiIntelligencePanel: React.FC<Props> = ({ signal }) => {
  if (!signal) {
    return (
      <section className="panel">
        <div className="panel-header">
          <span className="panel-title">AI INTELLIGENCE PANEL</span>
        </div>
        <p style={{ color: "#8b93a7", fontSize: "0.85rem" }}>Select an instrument to inspect AI analysis.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <span className="panel-title">AI INTELLIGENCE · {signal.symbol}</span>
        <span className="badge badge-purple">{signal.market_regime}</span>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 12 }}>
        <div className="kpi-card">
          <div className="kpi-label">Classification</div>
          <div className="kpi-value" style={{ color: "#00f5ff" }}>{signal.classification}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Calibrated Confidence</div>
          <div className="kpi-value">{(signal.confidence_estimate * 100).toFixed(1)}%</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">OOS Historical Win Rate</div>
          <div className="kpi-value">{(signal.historical_win_rate * 100).toFixed(1)}%</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Estimated Prob.</div>
          <div className="kpi-value">{(signal.estimated_probability * 100).toFixed(1)}%</div>
        </div>
      </div>

      <p style={{ fontSize: "0.82rem", color: "#cbd5e1", marginBottom: 10 }}>
        <strong>Market Structure:</strong> {signal.market_structure_explanation}
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, fontSize: "0.8rem" }}>
        <div>
          <div style={{ color: "#00ff9d", fontWeight: 700, marginBottom: 4 }}>Bullish Factors</div>
          <ul style={{ paddingLeft: 16 }}>
            {signal.bullish_factors.length ? (
              signal.bullish_factors.map((f, i) => <li key={i}>{f}</li>)
            ) : (
              <li style={{ color: "#8b93a7" }}>None confirmed</li>
            )}
          </ul>
        </div>
        <div>
          <div style={{ color: "#ff1e42", fontWeight: 700, marginBottom: 4 }}>Bearish & Risk Factors</div>
          <ul style={{ paddingLeft: 16 }}>
            {[...signal.bearish_factors, ...signal.risk_conditions].length ? (
              [...signal.bearish_factors, ...signal.risk_conditions].map((f, i) => <li key={i}>{f}</li>)
            ) : (
              <li style={{ color: "#8b93a7" }}>None flagged</li>
            )}
          </ul>
        </div>
      </div>

      <div style={{ marginTop: 10, fontSize: "0.78rem", color: "#8b93a7" }}>
        <div><strong>Fundamentals:</strong> {signal.fundamental_context?.note || "Active external provider"}</div>
        <div><strong>News:</strong> {signal.news_context?.note || `${signal.news_context?.items?.length || 0} verified items`}</div>
        <div><strong>Invalidation:</strong> {signal.invalidation_conditions.join(" | ")}</div>
      </div>
    </section>
  );
};
