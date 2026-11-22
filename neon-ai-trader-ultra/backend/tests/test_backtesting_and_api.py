"""Integration tests for Backtesting Engine and FastAPI REST/WebSocket endpoints."""

import unittest

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class TestBacktestingAndAPI(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(settings=Settings(), db_path=":memory:")
        self.client = TestClient(self.app)
        login_res = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "neon-admin-change-me"},
        )
        self.assertEqual(login_res.status_code, 200)
        self.headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    def test_health_and_mode_status_endpoints(self) -> None:
        r = self.client.get("/api/v1/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["trading_mode"], "DEMO")
        self.assertFalse(r.json()["real_trading_enabled"])

        st = self.client.get("/api/v1/mode/status")
        self.assertEqual(st.status_code, 200)
        self.assertEqual(st.json()["active_broker"], "PAPER")

    def test_scanner_candles_and_signal_endpoints(self) -> None:
        sc = self.client.get("/api/v1/market/scanner?timeframe=1h")
        self.assertEqual(sc.status_code, 200)
        self.assertGreaterEqual(len(sc.json()["items"]), 4)

        cd = self.client.get("/api/v1/market/candles/BTCUSDT?timeframe=1h&limit=80")
        self.assertEqual(cd.status_code, 200)
        self.assertEqual(len(cd.json()["candles"]), 80)

        sg = self.client.get("/api/v1/analysis/signal/BTCUSDT?timeframe=1h")
        self.assertEqual(sg.status_code, 200)
        self.assertIn("strategy_consensus", sg.json())

    def test_order_execution_and_audit_log_via_api(self) -> None:
        sig = self.client.get("/api/v1/analysis/signal/BTCUSDT?timeframe=1h").json()
        px = sig["current_price"]
        # Unauthenticated order must be rejected
        unauth = self.client.post(
            "/api/v1/trading/orders",
            json={"symbol": "BTCUSDT", "side": "BUY", "stop_loss": px * 0.98, "take_profit": px * 1.04},
        )
        self.assertEqual(unauth.status_code, 401)

        # Authenticated DEMO order succeeds
        ok = self.client.post(
            "/api/v1/trading/orders",
            headers=self.headers,
            json={"symbol": "BTCUSDT", "side": "BUY", "stop_loss": px * 0.98, "take_profit": px * 1.04},
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["order"]["status"], "FILLED")

        logs = self.client.get("/api/v1/audit-logs", headers=self.headers)
        self.assertEqual(logs.status_code, 200)
        self.assertGreaterEqual(len(logs.json()["audit_logs"]), 2)

    def test_backtesting_endpoint_returns_full_metrics_and_monte_carlo(self) -> None:
        bt = self.client.post(
            "/api/v1/backtesting/run",
            json={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "strategy": "TREND_FOLLOWING",
                "initial_capital": 100000.0,
                "bars": 250,
                "run_monte_carlo": True,
                "monte_carlo_runs": 100,
            },
        )
        self.assertEqual(bt.status_code, 200)
        metrics = bt.json()["metrics"]
        for key in (
            "net_profit",
            "gross_profit",
            "gross_loss",
            "win_rate",
            "profit_factor",
            "max_drawdown_pct",
            "sharpe_ratio",
            "sortino_ratio",
            "total_trades",
            "trading_fees",
            "walk_forward_oos",
            "disclaimer",
        ):
            self.assertIn(key, metrics)


if __name__ == "__main__":
    unittest.main()
