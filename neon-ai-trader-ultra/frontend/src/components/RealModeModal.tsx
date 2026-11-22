import React, { useState } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  onAuthorize: (payload: {
    broker_name: string;
    verified_account_last4: string;
    confirmation_phrase: string;
    risk_acknowledged: boolean;
  }) => Promise<void>;
}

export const RealModeModal: React.FC<Props> = ({ open, onClose, onAuthorize }) => {
  const [brokerName, setBrokerName] = useState("BINANCE");
  const [last4, setLast4] = useState("");
  const [phrase, setPhrase] = useState("");
  const [riskAck, setRiskAck] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await onAuthorize({
        broker_name: brokerName,
        verified_account_last4: last4,
        confirmation_phrase: phrase,
        risk_acknowledged: riskAck,
      });
      onClose();
    } catch (err: any) {
      setError(err.message || "Live authorization rejected by backend safety checks.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-card">
        <h2 style={{ color: "#ff1e42", marginBottom: 8, letterSpacing: "0.06em" }}>
          LIVE TRADING AUTHORIZATION REQUIRED
        </h2>
        <p style={{ fontSize: "0.84rem", color: "#cbd5e1", marginBottom: 14 }}>
          Real-money trading carries substantial risk of capital loss. Demo and Real accounts are
          strictly isolated and open positions are never transferred. Complete all backend safety
          checks below to arm live execution.
        </p>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <label style={{ fontSize: "0.8rem" }}>
            Live Broker Connector
            <select
              className="input-field"
              value={brokerName}
              onChange={(e) => setBrokerName(e.target.value)}
            >
              <option value="BINANCE">BINANCE (Live API)</option>
              <option value="MT5">METATRADER 5 (Live Account)</option>
            </select>
          </label>

          <label style={{ fontSize: "0.8rem" }}>
            Verify Intended Live Account (last 4 characters)
            <input
              className="input-field"
              value={last4}
              onChange={(e) => setLast4(e.target.value)}
              placeholder="e.g. 4821"
              required
            />
          </label>

          <label style={{ fontSize: "0.8rem" }}>
            Type exact confirmation phrase: <strong>ENABLE REAL TRADING</strong>
            <input
              className="input-field"
              value={phrase}
              onChange={(e) => setPhrase(e.target.value)}
              placeholder="ENABLE REAL TRADING"
              required
            />
          </label>

          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.8rem" }}>
            <input
              type="checkbox"
              checked={riskAck}
              onChange={(e) => setRiskAck(e.target.checked)}
            />
            I verify my live account, risk limits, and understand real capital is at risk.
          </label>

          {error && (
            <div style={{ color: "#ff5c77", fontSize: "0.8rem", fontFamily: "monospace" }}>
              {error}
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 6 }}>
            <button type="button" className="btn" onClick={onClose}>
              CANCEL (STAY SAFE)
            </button>
            <button type="submit" className="btn btn-emergency" disabled={submitting}>
              {submitting ? "VALIDATING..." : "AUTHORIZE LIVE EXECUTION"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
