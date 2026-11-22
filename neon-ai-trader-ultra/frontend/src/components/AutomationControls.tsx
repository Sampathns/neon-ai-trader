import React from "react";
import type { ModeStatus, TradingMode } from "../types/trading";

interface Props {
  status: ModeStatus;
  onStartScanner: () => void;
  onEnableAuto: () => void;
  onPauseAutomation: () => void;
  onStopNewTrades: () => void;
  onCancelPending: () => void;
  onEmergencyStop: () => void;
  onSelectMode: (mode: TradingMode) => void;
}

export const AutomationControls: React.FC<Props> = ({
  status,
  onStartScanner,
  onEnableAuto,
  onPauseAutomation,
  onStopNewTrades,
  onCancelPending,
  onEmergencyStop,
  onSelectMode,
}) => {
  return (
    <section className="panel">
      <div className="panel-header">
        <span className="panel-title">AUTOMATION & EXECUTION CONTROLS</span>
        <span className="badge badge-wait">
          SCANNER: {status.ai_scanner_running ? "RUNNING" : "IDLE"} · AUTO:{" "}
          {status.auto_trading_enabled ? "ENABLED" : "DISABLED"}
        </span>
      </div>

      <div className="controls-grid">
        <button className="btn btn-demo-active" onClick={onStartScanner}>
          [ START AI SCANNER ]
        </button>
        <button className="btn btn-purple" onClick={onEnableAuto}>
          [ ENABLE AUTO TRADING ]
        </button>
        <button className="btn" onClick={onPauseAutomation}>
          [ PAUSE AUTOMATION ]
        </button>
        <button className="btn" onClick={onStopNewTrades}>
          [ STOP ALL NEW TRADES ]
        </button>
        <button className="btn" onClick={onCancelPending}>
          [ CANCEL PENDING ORDERS ]
        </button>
        <button className="btn btn-emergency" onClick={onEmergencyStop}>
          [ EMERGENCY STOP ]
        </button>
        <button
          className={`btn ${status.current_mode === "DEMO" ? "btn-demo-active" : ""}`}
          onClick={() => onSelectMode("DEMO")}
        >
          [ DEMO MODE ]
        </button>
        <button
          className={`btn ${status.current_mode === "REAL" ? "btn-real-active" : ""}`}
          onClick={() => onSelectMode("REAL")}
        >
          [ REAL MODE ]
        </button>
      </div>
    </section>
  );
};
