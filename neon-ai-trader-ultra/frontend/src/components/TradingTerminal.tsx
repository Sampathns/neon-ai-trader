import React from "react";
import type { Candle, SignalDetail } from "../types/trading";

interface Props {
  symbol: string;
  timeframe: string;
  onTimeframeChange: (tf: string) => void;
  candles: Candle[];
  dataStatus: string;
  signal: SignalDetail | null;
}

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"];

export const TradingTerminal: React.FC<Props> = ({
  symbol,
  timeframe,
  onTimeframeChange,
  candles,
  dataStatus,
  signal,
}) => {
  const visible = candles.slice(-60);
  const width = 820;
  const height = 280;
  const pad = 28;

  const prices = visible.flatMap((c) => [c.high, c.low]);
  if (signal && signal.stop_loss > 0) prices.push(signal.stop_loss);
  if (signal && signal.take_profit_levels?.[0] > 0) prices.push(signal.take_profit_levels[0]);

  const minP = prices.length ? Math.min(...prices) : 0;
  const maxP = prices.length ? Math.max(...prices) : 1;
  const span = Math.max(maxP - minP, 1e-6);

  const yOf = (p: number) => height - pad - ((p - minP) / span) * (height - pad * 2);
  const stepX = visible.length > 1 ? (width - pad * 2) / visible.length : 10;

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <span className="panel-title">TRADING TERMINAL · {symbol}</span>
          <span className="badge badge-purple" style={{ marginLeft: 10 }}>
            FEED: {dataStatus}
          </span>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              className={`btn ${tf === timeframe ? "btn-demo-active" : ""}`}
              style={{ padding: "4px 8px", fontSize: "0.72rem" }}
              onClick={() => onTimeframeChange(tf)}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: "auto", background: "#040409", borderRadius: 8 }}>
        {/* Stop Loss & Take Profit visualization */}
        {signal && signal.stop_loss > 0 && (
          <g>
            <line
              x1={pad}
              x2={width - pad}
              y1={yOf(signal.stop_loss)}
              y2={yOf(signal.stop_loss)}
              stroke="#ff1e42"
              strokeDasharray="5 4"
              strokeWidth={1.3}
            />
            <text x={pad + 4} y={yOf(signal.stop_loss) - 4} fill="#ff1e42" fontSize="10" fontFamily="monospace">
              SL {signal.stop_loss}
            </text>
          </g>
        )}
        {signal && signal.take_profit_levels?.[0] > 0 && (
          <g>
            <line
              x1={pad}
              x2={width - pad}
              y1={yOf(signal.take_profit_levels[0])}
              y2={yOf(signal.take_profit_levels[0])}
              stroke="#00ff9d"
              strokeDasharray="5 4"
              strokeWidth={1.3}
            />
            <text x={pad + 4} y={yOf(signal.take_profit_levels[0]) - 4} fill="#00ff9d" fontSize="10" fontFamily="monospace">
              TP1 {signal.take_profit_levels[0]}
            </text>
          </g>
        )}

        {/* Candlesticks */}
        {visible.map((c, idx) => {
          const x = pad + idx * stepX + stepX * 0.5;
          const bull = c.close >= c.open;
          const color = bull ? "#00f5ff" : "#ff1e42";
          const yTop = yOf(Math.max(c.open, c.close));
          const yBot = yOf(Math.min(c.open, c.close));
          return (
            <g key={c.timestamp}>
              <line x1={x} x2={x} y1={yOf(c.high)} y2={yOf(c.low)} stroke={color} strokeWidth={1.2} />
              <rect
                x={x - Math.max(stepX * 0.3, 2)}
                y={yTop}
                width={Math.max(stepX * 0.6, 4)}
                height={Math.max(yBot - yTop, 1.5)}
                fill={color}
                opacity={0.9}
              />
            </g>
          );
        })}
      </svg>
    </section>
  );
};
