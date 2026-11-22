"""Tests for Risk Engine, Position Sizing, Daily Loss Limit, Idempotency, Stale Data, Disconnect, and Reconciliation."""

import unittest

from app.brokers.binance_connector import BinanceConnector
from app.core.config import BrokerCredentialConfig, RiskConfig, Settings
from app.core.enums import OrderSide, OrderType
from app.main import create_app
from app.trading.execution_engine import ExecutionError


class TestRiskAndExecution(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(settings=Settings(), db_path=":memory:")
        self.c = self.app.state.container
        self.paper = self.c["registry"].get_connector("DEMO", "PAPER")

    def test_position_sizing_never_increases_after_losses(self) -> None:
        risk = self.c["risk_engine"]
        cfg = RiskConfig()
        qty_0 = risk.calculate_position_size(100000.0, 100.0, 98.0, cfg, consecutive_losses=0)
        qty_1 = risk.calculate_position_size(100000.0, 100.0, 98.0, cfg, consecutive_losses=1)
        qty_2 = risk.calculate_position_size(100000.0, 100.0, 98.0, cfg, consecutive_losses=2)
        self.assertGreater(qty_0, 0)
        self.assertLess(qty_1, qty_0)
        self.assertLess(qty_2, qty_1)

    def test_invalid_stop_loss_and_take_profit_rejected(self) -> None:
        exec_engine = self.c["execution_engine"]
        price = self.paper.get_ticker("BTCUSDT").ask
        with self.assertRaises(ExecutionError):
            exec_engine.submit_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                stop_loss=price * 1.05,  # Invalid: SL above entry for BUY
                take_profit=price * 1.10,
                actor="admin",
            )

    def test_daily_loss_limit_triggers_circuit_breaker(self) -> None:
        exec_engine = self.c["execution_engine"]
        price = self.paper.get_ticker("BTCUSDT").ask
        with self.assertRaises(ExecutionError) as ctx:
            exec_engine.submit_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                stop_loss=round(price * 0.98, 2),
                take_profit=round(price * 1.04, 2),
                actor="admin",
                override_daily_pnl=-2500.0,  # 2.5% loss > 2.0% daily limit
            )
        self.assertIn("Daily loss limit reached", str(ctx.exception))

    def test_duplicate_order_prevention_via_idempotency_key(self) -> None:
        exec_engine = self.c["execution_engine"]
        price = self.paper.get_ticker("ETHUSDT").ask
        r1 = exec_engine.submit_order(
            symbol="ETHUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            stop_loss=round(price * 0.98, 2),
            take_profit=round(price * 1.04, 2),
            idempotency_key="idem-unique-123",
            actor="admin",
        )
        r2 = exec_engine.submit_order(
            symbol="ETHUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            stop_loss=round(price * 0.98, 2),
            take_profit=round(price * 1.04, 2),
            idempotency_key="idem-unique-123",
            actor="admin",
        )
        self.assertFalse(r1["duplicate_prevented"])
        self.assertTrue(r2["duplicate_prevented"])
        self.assertEqual(r1["order"]["id"], r2["order"]["id"])

    def test_stale_data_blocks_order_execution(self) -> None:
        self.paper.set_stale_feed_seconds(180)
        exec_engine = self.c["execution_engine"]
        with self.assertRaises(ExecutionError) as ctx:
            exec_engine.submit_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                stop_loss=60000.0,
                take_profit=75000.0,
                actor="admin",
            )
        self.assertIn("Stale ticker data", str(ctx.exception))
        self.paper.set_stale_feed_seconds(None)

    def test_broker_disconnect_and_bounded_reconnection(self) -> None:
        self.paper.disconnect()
        self.assertEqual(self.paper.health_check()["status"], "DISCONNECTED")
        reconnected = self.c["data_engine"].ensure_connected(self.paper)
        self.assertTrue(reconnected)
        self.assertEqual(self.paper.health_check()["status"], "CONNECTED")

    def test_order_reconciliation_updates_pending_order(self) -> None:
        exec_engine = self.c["execution_engine"]
        price = self.paper.get_ticker("BTCUSDT").ask
        res = exec_engine.submit_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            entry_price=round(price * 0.99, 2),
            stop_loss=round(price * 0.97, 2),
            take_profit=round(price * 1.03, 2),
            actor="admin",
        )
        broker_id = res["order"]["broker_order_id"]
        # Simulate broker filling the limit order asynchronously
        self.paper._orders[broker_id]["status"] = "FILLED"
        self.paper._orders[broker_id]["filled_price"] = round(price * 0.99, 2)
        rec = exec_engine.reconcile_orders(actor="admin")
        self.assertEqual(rec["reconciled_count"], 1)
        updated = self.c["db"].get_order_by_id(res["order"]["id"])
        self.assertEqual(updated["status"], "FILLED")

    def test_binance_rate_limit_safeguard(self) -> None:
        creds = BrokerCredentialConfig(
            broker_name="BINANCE", mode="DEMO", api_key="k", api_secret="s", base_url="https://testnet.binance.vision"
        )
        b = BinanceConnector(creds)
        b._used_weight_1m = 1150  # Exceeds 90% of 1200
        with self.assertRaises(RuntimeError):
            b._check_rate_limit()


if __name__ == "__main__":
    unittest.main()
