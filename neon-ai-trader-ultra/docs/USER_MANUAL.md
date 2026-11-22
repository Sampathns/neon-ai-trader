# User Manual — NEON AI TRADER ULTRA

## 1. Default Safe Startup
On startup, the platform runs in **DEMO MODE** with **Real Trading DISABLED** and **Auto Execution DISABLED**. The Paper Trading Simulator tracks virtual equity ($100,000 default) with realistic fees (6 bps) and slippage (3 bps), and every quote is explicitly labeled `SIMULATED`.

## 2. Switching to REAL MODE (7-Step Protection)
1. Click `[ REAL TRADING ]` in the top command bar. If open DEMO positions exist, you will be warned that they remain under DEMO and are never transferred.
2. Review the Live-Risk Warning.
3. Select your configured live broker (`BINANCE` or `MT5`).
4. Enter the last 4 characters of your intended live account identifier.
5. Backend verifies live broker connectivity, trade permissions (rejecting withdrawal-enabled keys), and active risk configuration.
6. Type `ENABLE REAL TRADING` verbatim and check the risk acknowledgment box.
7. Submit to arm live execution. All live authorization events are written to `audit_logs`.

## 3. Emergency Controls
- `[ EMERGENCY STOP ]`: Immediately halts scanner, disables auto-trading, disarms real trading, and cancels all pending orders in the active mode.
- `[ CANCEL PENDING ORDERS ]`: Cancels all open/pending orders in the active mode.
- Close All Positions: Requires typing `CLOSE ALL POSITIONS` verbatim via the API/modal.

## 4. Backtesting Lab
Select symbol, strategy, and timeframe to run an event-driven backtest including fees, spread, slippage, funding costs, 70/30 out-of-sample walk-forward metrics, and Monte Carlo drawdown percentiles. Historical simulation results never guarantee future performance.
