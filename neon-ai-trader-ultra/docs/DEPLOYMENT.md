# Deployment & MT5 Bridge Guide

## 1. Environment Setup
Copy `.env.example` to `.env` and populate strong random values for `NEON_SECRET_KEY` and `NEON_ENCRYPTION_KEY`. Change the default local `admin` password before exposing any network port.

## 2. Docker Compose (Desktop Server / VPS)
```bash
docker compose up -d --build
```
- Backend API & WebSocket: `http://<server-ip>:8000/api/v1`
- Neon Dashboard (mobile-responsive): `http://<server-ip>:3000`

## 3. MetaTrader 5 Bridge (Required for Linux/macOS/Docker Backends)
Because the official `MetaTrader5` Python package only runs natively on Windows alongside the MT5 terminal:
1. Run `backend/mt5_bridge/server.py` on your Windows host with MetaTrader 5 open:
   ```powershell
   set NEON_MT5_BRIDGE_TOKEN=your-strong-shared-secret
   set NEON_MT5_LOGIN=12345678
   set NEON_MT5_PASSWORD=your-demo-or-live-password
   set NEON_MT5_SERVER=YourBroker-Demo
   uvicorn mt5_bridge.server:bridge_app --host 127.0.0.1 --port 8090
   ```
2. Expose it strictly over a private VPN / WireGuard tunnel or TLS reverse proxy, and configure `NEON_MT5_DEMO_BRIDGE_URL` (or `NEON_MT5_LIVE_BRIDGE_URL` for a separate live terminal).

## 4. Binance API Security
- Generate separate API keys for Testnet (`testnet.binance.vision`) and Production (`api.binance.com`).
- Restrict IP access on Binance.
- **NEVER enable withdrawal permissions** — the backend automatically rejects any key reporting `withdraw_allowed=true`.
