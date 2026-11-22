import React, { useCallback, useEffect, useState } from "react";
import { AiIntelligencePanel } from "./components/AiIntelligencePanel";
import { AlertsPanel } from "./components/AlertsPanel";
import { AutomationControls } from "./components/AutomationControls";
import { BacktestLab } from "./components/BacktestLab";
import { HeaderBar } from "./components/HeaderBar";
import { MarketScanner } from "./components/MarketScanner";
import { PortfolioOverview } from "./components/PortfolioOverview";
import { RealModeModal } from "./components/RealModeModal";
import { TradingTerminal } from "./components/TradingTerminal";
import { api } from "./services/api";
import type {
  Candle,
  ModeStatus,
  NotificationItem,
  PositionRecord,
  ScannerItem,
  SignalDetail,
  TradingMode,
} from "./types/trading";

export const App: React.FC = () => {
  const [status, setStatus] = useState<ModeStatus | null>(null);
  const [scanner, setScanner] = useState<ScannerItem[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [dataStatus, setDataStatus] = useState("SIMULATED");
  const [signal, setSignal] = useState<SignalDetail | null>(null);
  const [positions, setPositions] = useState<PositionRecord[]>([]);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [realModalOpen, setRealModalOpen] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [serverUrlInput, setServerUrlInput] = useState(api.getBaseUrl());

  const refreshAll = useCallback(async () => {
    try {
      const [st, sc, pos, notifs] = await Promise.all([
        api.getModeStatus(),
        api.getScanner(timeframe),
        api.getPositions(),
        api.getNotifications(),
      ]);
      setStatus(st);
      setScanner(sc.items);
      setPositions(pos.positions);
      setNotifications(notifs.notifications);
      setBanner(null);
    } catch (err: any) {
      setBanner(err.message || "Unable to connect to backend API. Set your Server URL below.");
    }
  }, [timeframe]);

  const refreshSymbol = useCallback(async () => {
    try {
      const [cRes, sRes] = await Promise.all([
        api.getCandles(selectedSymbol, timeframe),
        api.getSignal(selectedSymbol, timeframe),
      ]);
      setCandles(cRes.candles);
      setDataStatus(cRes.data_status);
      setSignal(sRes);
    } catch {
      // Handled gracefully when backend or broker is disconnected
    }
  }, [selectedSymbol, timeframe]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    refreshSymbol();
  }, [refreshSymbol]);

  const handleSaveServerUrl = async (e: React.FormEvent) => {
    e.preventDefault();
    api.setBaseUrl(serverUrlInput);
    await refreshAll();
    await refreshSymbol();
  };

  const handleSelectMode = async (mode: TradingMode) => {
    setBanner(null);
    try {
      const res = await api.switchMode(mode, true);
      if (mode === "REAL" && res.requires_live_authorization) {
        setRealModalOpen(true);
      }
      await refreshAll();
    } catch (err: any) {
      setBanner(err.message);
    }
  };

  if (!status) {
    return (
      <div className="neon-shell">
        <div className="panel">
          <div className="brand-title" style={{ marginBottom: 8 }}>NEON AI TRADER ULTRA</div>
          <p style={{ fontSize: "0.85rem", color: "#cbd5e1", marginBottom: 12 }}>
            {banner || "Connecting to backend server..."}
          </p>
          <form onSubmit={handleSaveServerUrl} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input
              className="input-field"
              style={{ flex: 1, minWidth: 220, marginTop: 0 }}
              value={serverUrlInput}
              onChange={(e) => setServerUrlInput(e.target.value)}
              placeholder="https://your-server.com or http://192.168.1.10:8000"
            />
            <button type="submit" className="btn btn-demo-active">
              CONNECT SERVER
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="neon-shell">
      <HeaderBar
        status={status}
        onSelectMode={handleSelectMode}
        onEmergencyStop={async () => {
          await api.emergencyStop();
          setBanner("EMERGENCY STOP ACTIVATED: Automation halted and pending orders cancelled.");
          await refreshAll();
        }}
      />

      {banner && (
        <div className="panel" style={{ borderColor: "#ff1e42", color: "#ff8fa3", fontSize: "0.84rem" }}>
          {banner}
        </div>
      )}

      <AutomationControls
        status={status}
        onStartScanner={async () => { await api.toggleScanner("start"); await refreshAll(); }}
        onEnableAuto={async () => { await api.toggleAutoTrading("enable"); await refreshAll(); }}
        onPauseAutomation={async () => { await api.toggleAutoTrading("disable"); await refreshAll(); }}
        onStopNewTrades={async () => { await api.toggleAutoTrading("disable"); await refreshAll(); }}
        onCancelPending={async () => { await api.cancelPendingOrders(); await refreshAll(); }}
        onEmergencyStop={async () => { await api.emergencyStop(); await refreshAll(); }}
        onSelectMode={handleSelectMode}
      />

      <PortfolioOverview status={status} positions={positions} />

      <div className="grid-2col">
        <TradingTerminal
          symbol={selectedSymbol}
          timeframe={timeframe}
          onTimeframeChange={setTimeframe}
          candles={candles}
          dataStatus={dataStatus}
          signal={signal}
        />
        <AiIntelligencePanel signal={signal} />
      </div>

      <MarketScanner
        items={scanner}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={setSelectedSymbol}
      />

      <div className="grid-2col">
        <BacktestLab />
        <AlertsPanel notifications={notifications} />
      </div>

      <RealModeModal
        open={realModalOpen}
        onClose={() => setRealModalOpen(false)}
        onAuthorize={async (payload) => {
          await api.enableRealTrading(payload);
          await refreshAll();
        }}
      />
    </div>
  );
};
export default App;
