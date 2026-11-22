# NEON AI TRADER ULTRA

**Intelligence First. Execution Second. Risk Always.**

A modular, full-stack autonomous multi-market AI trading platform built with Python 3 / FastAPI and React / TypeScript.

## Initial System State (Safe by Default)
- **Trading Mode**: `DEMO`
- **Real Trading**: `DISABLED` (requires explicit 7-step backend authorization with `ENABLE REAL TRADING`)
- **Auto Execution**: `DISABLED`
- **Risk Engine**: `MANDATORY` (0.5% risk/trade, 2% daily loss limit, 10% max drawdown, no martingale)
- **Emergency STOP**: `ENABLED`

## Quick Start (Local Development)

### 1. Backend
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend
```bash
cd frontend
npm install
npm run dev
```

### 3. Run Automated Tests
```bash
cd backend
python3 -m unittest discover -s tests -v
```

### 4. Docker Deployment
```bash
cp .env.example .env
docker compose up --build
```

## Documentation
- [System Architecture](docs/ARCHITECTURE.md)
- [Deployment & MT5 Bridge Guide](docs/DEPLOYMENT.md)
- [User Manual & Live Authorization](docs/USER_MANUAL.md)
