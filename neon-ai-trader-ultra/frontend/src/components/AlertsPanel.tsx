import React from "react";
import type { NotificationItem } from "../types/trading";

interface Props {
  notifications: NotificationItem[];
}

export const AlertsPanel: React.FC<Props> = ({ notifications }) => {
  return (
    <section className="panel">
      <div className="panel-header">
        <span className="panel-title">SYSTEM ALERTS & RISK NOTIFICATIONS</span>
        <span className="badge badge-wait">{notifications.length} recent</span>
      </div>
      {notifications.length === 0 ? (
        <p style={{ fontSize: "0.82rem", color: "#8b93a7" }}>No alerts recorded yet.</p>
      ) : (
        <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: 8 }}>
          {notifications.slice(0, 8).map((n) => (
            <li
              key={n.id}
              style={{
                padding: 8,
                borderRadius: 8,
                background: "rgba(255,255,255,0.03)",
                borderLeft: `3px solid ${n.severity === "CRITICAL" ? "#ff0033" : n.severity === "WARNING" ? "#ffbe0b" : "#00f5ff"}`,
                fontSize: "0.8rem",
              }}
            >
              <div style={{ fontWeight: 700 }}>
                [{n.category}] {n.title}
              </div>
              <div style={{ color: "#cbd5e1" }}>{n.message}</div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};
