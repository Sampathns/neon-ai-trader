# System Architecture — NEON AI TRADER ULTRA

## 1. Strict Separation of Concerns
The platform strictly separates market intelligence from order execution:
1. **Market Data Engine** (`app/market_data/engine.py`): Validates data freshness, removes duplicate candles, flags gaps, pauses stale symbols, and handles bounded reconnection retries.
2. **AI Analysis & Signal Engine** (`app/analysis/`): Computes technical indicators (RSI, MACD, EMA, SMA, VWAP, BB, ATR, ADX, Stochastic, Ichimoku, Fibonacci, Pivots, S/R), objective market structure (HH/HL/LH/LL, BOS, CHoCH, Supply/Demand, Liquidity, Imbalances), multi-timeframe agreement (`1m`–`1M`), leakage-free walk-forward calibrated ML probabilities, and fundamental/news adapters.
3. **Strategy Engine** (`app/trading/strategies.py`): Seven independently toggleable strategies with conflict resolution (defaults to `HOLD` on opposing consensus).
4. **Risk Management Engine** (`app/risk/engine.py`): Backend-enforced position sizing, risk/trade cap (0.5%), daily/weekly loss limits (2%/5%), drawdown cap (10%), correlation cluster caps, spread/slippage caps, consecutive-loss circuit breaker, and permanent prohibition against martingale/loss-doubling.
5. **Mode Controller** (`app/core/mode_controller.py`): Enforces strict DEMO vs REAL isolation, 7-step live authorization (`ENABLE REAL TRADING`), Emergency STOP, cancel-pending, and confirmed close-all.
6. **Trade Execution Engine** (`app/trading/execution_engine.py`): Idempotency key deduplication, pre-trade validation checklist, broker submission, and order/position reconciliation.
7. **Broker Connectors** (`app/brokers/`): Unified `BrokerConnector` ABC with `PaperBrokerConnector` (DEMO), `MT5Connector` (native Windows + HTTP Bridge), `BinanceConnector` (isolated Testnet vs Live), and expandable `UnconfiguredMarketAdapter` interfaces.
8. **Backtesting Lab** (`app/backtesting/engine.py`): Historical simulator with fees, spread, slippage, funding costs, 70/30 walk-forward OOS split, and Monte Carlo drawdown bands.
9. **Security & Persistence** (`app/core/security.py`, `app/db/`): Fernet encryption at rest, PBKDF2-HMAC-SHA256 password hashing, HMAC-SHA256 tokens, masked account IDs, secret redaction, and immutable audit logs.
