import React from "react";
import type { ScannerItem } from "../types/trading";

interface Props {
  items: ScannerItem[];
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
}

export const MarketScanner: React.FC<Props> = ({ items, selectedSymbol, onSelectSymbol }) => {
  const badgeClass = (cls: string) => {
    if (cls.includes("BUY")) return "badge badge-buy";
    if (cls.includes("SELL")) return "badge badge-sell";
    return "badge badge-wait";
  };

  return (
    <section className="panel">
      <div className="panel-header">
        <span className="panel-title">GLOBAL AI MARKET SCANNER</span>
        <span style={{ fontSize: "0.75rem", color: "#8b93a7" }}>
          {items.length} instruments scanned
        </span>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table className="neon-table">
          <thead>
            <tr>
              <th>Market</th>
              <th>Symbol</th>
              <th>Price</th>
              <th>Volume</th>
              <th>Trend</th>
              <th>AI Signal</th>
              <th>Conf.</th>
              <th>R/R</th>
              <th>Feed</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr
                key={item.symbol}
                onClick={() => onSelectSymbol(item.symbol)}
                style={{
                  cursor: "pointer",
                  background: item.symbol === selectedSymbol ? "rgba(157, 78, 221, 0.16)" : undefined,
                }}
              >
                <td>{item.market}</td>
                <td style={{ color: "#00f5ff", fontWeight: 700 }}>{item.symbol}</td>
                <td>{item.current_price}</td>
                <td>{item.volume_24h.toLocaleString()}</td>
                <td>{item.trend}</td>
                <td>
                  <span className={badgeClass(item.classification)}>{item.classification}</span>
                </td>
                <td>{(item.confidence_estimate * 100).toFixed(1)}%</td>
                <td>{item.risk_reward_ratio.toFixed(2)}</td>
                <td>{item.data_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
};
