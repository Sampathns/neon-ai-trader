import React from "react";
import type { ModeStatus, TradingMode } from "../types/trading";

interface Props {
  status: ModeStatus;
  onSelectMode: (mode: TradingMode) => void;
  onEmergencyStop: () => void;
}

export const HeaderBar: React.FC<Props> = ({ status, onSelectMode, onEmergencyStop }) => {
  const isDemo = status.current_mode === "DEMO";
  return (
    <header className="panel top-bar">
      <div>
        <div className="brand-title">NEON AI TRADER ULTRA</div>
        <div className="brand-sub">
          INTELLIGENCE FIRST · EXECUTION SECOND · RISK ALWAYS
        </div>
      </div>

      <div className="mode-switch" role="group" aria-label="Trading Mode Selector">
        <button
          className={`btn ${isDemo ? "btn-demo-active" : ""}`}
          onClick={() => onSelectMode("DEMO")}
        >
          [ DEMO TRADING ]
        </button>
        <button
          className={`btn ${!isDemo ? "btn-real-active" : ""}`}
          onClick={() => onSelectMode("REAL")}
        >
          [ REAL TRADING ]
        </button>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <span className={`badge ${isDemo ? "badge-cyan" : "badge-sell"}`}>
          MODE: {status.current_mode} {status.real_trading_enabled ? "(LIVE ARMED)" : "(SAFE)"}
        </span>
        <span className="badge badge-purple">
          {status.active_broker} · {status.account_id_masked}
        </span>
        <span className="badge badge-wait">
          CONN: {status.connection_health?.status || "UNKNOWN"}
        </span>
        <button className="btn btn-emergency" onClick={onEmergencyStop}>
          [ EMERGENCY STOP ]
        </button>
      </div>
    </header>
  );
};
