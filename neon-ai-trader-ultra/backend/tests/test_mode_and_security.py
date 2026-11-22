"""Tests for DEMO/REAL isolation, 7-step live authorization, security vault, and Emergency STOP."""

import unittest

from app.brokers.base import BrokerConnector, BrokerOrderResult, ContractSpec, TickerQuote
from app.brokers.binance_connector import BinanceConnector
from app.core.config import BrokerCredentialConfig, Settings
from app.core.enums import ConnectionStatus, OrderSide, OrderType, TradingMode
from app.core.mode_controller import LIVE_CONFIRMATION_PHRASE, ModeSwitchError
from app.core.security import SecretVault, mask_account_id, redact_secrets, verify_access_token, create_access_token
from app.main import create_app


class MockLiveBroker(BrokerConnector):
    broker_name = "BINANCE"
    trading_mode = "REAL"

    def __init__(self, account_id: str = "LIVE-ACC-9876", withdraw_allowed: bool = False) -> None:
        self.account_id = account_id
        self.withdraw_allowed = withdraw_allowed
        self.connected = True

    def connect(self):
        self.connected = True
        return self.health_check()

    def disconnect(self):
        self.connected = False

    def health_check(self):
        return {"broker": self.broker_name, "mode": self.trading_mode, "status": ConnectionStatus.CONNECTED.value}

    def get_account_info(self):
        return {
            "broker": self.broker_name,
            "mode": self.trading_mode,
            "account_id_masked": mask_account_id(self.account_id),
            "balance": 50000.0,
            "equity": 50000.0,
            "available_margin": 50000.0,
            "used_margin": 0.0,
            "permissions": {"trade_allowed": True, "withdraw_allowed": self.withdraw_allowed},
        }

    def list_symbols(self): return []
    def get_ticker(self, symbol): return None
    def get_ohlcv(self, symbol, timeframe="1h", limit=200): return []
    def get_order_book(self, symbol, depth=10): return {}
    def place_order(self, **kwargs): return BrokerOrderResult("LIVE-1", "FILLED", 100.0, 1.0)
    def cancel_order(self, broker_order_id): return True
    def get_order_status(self, broker_order_id): return {"status": "FILLED"}
    def close_position(self, position_id): return True


class TestModeAndSecurity(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(settings=Settings(), db_path=":memory:")
        self.c = self.app.state.container

    def test_initial_safe_state_is_demo_and_real_disabled(self) -> None:
        state = self.c["db"].get_mode_state()
        self.assertEqual(state["current_mode"], "DEMO")
        self.assertFalse(state["real_trading_enabled"])
        self.assertFalse(state["auto_trading_enabled"])

    def test_secret_vault_encryption_masking_and_redaction(self) -> None:
        vault = SecretVault("unit-test-master-secret")
        ct = vault.encrypt("my-super-secret-api-key")
        self.assertNotIn("my-super-secret-api-key", ct)
        self.assertEqual(vault.decrypt(ct), "my-super-secret-api-key")
        self.assertEqual(mask_account_id("ACCT-12345678"), "*********5678")
        self.assertIn("api_key=[REDACTED]", redact_secrets("error api_key=abc123xyz"))

        token = create_access_token("admin", "admin", "jwt-secret")
        payload = verify_access_token(token, "jwt-secret")
        self.assertEqual(payload["sub"], "admin")

    def test_credential_isolation_blocks_cross_mode_binance_endpoint(self) -> None:
        bad_demo = BrokerCredentialConfig(
            broker_name="BINANCE",
            mode="DEMO",
            api_key="k",
            api_secret="s",
            base_url="https://api.binance.com",
        )
        conn = BinanceConnector(bad_demo)
        health = conn.connect()
        self.assertEqual(health["status"], ConnectionStatus.DISCONNECTED.value)
        self.assertIn("Isolation violation", health["reason"])

    def test_unauthorized_live_execution_is_rejected(self) -> None:
        ctrl = self.c["mode_controller"]
        ctrl.switch_mode(TradingMode.REAL, actor="admin", broker_name="BINANCE", acknowledge_open_positions=True)
        with self.assertRaises(ModeSwitchError):
            ctrl.assert_execution_allowed("REAL")

    def test_mode_switch_warns_when_open_positions_exist_and_never_transfers(self) -> None:
        exec_engine = self.c["execution_engine"]
        paper = self.c["registry"].get_connector("DEMO", "PAPER")
        price = paper.get_ticker("BTCUSDT").ask
        exec_engine.submit_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            stop_loss=round(price * 0.98, 2),
            take_profit=round(price * 1.04, 2),
            actor="admin",
        )
        ctrl = self.c["mode_controller"]
        res = ctrl.switch_mode(TradingMode.REAL, actor="admin", acknowledge_open_positions=False)
        self.assertFalse(res["switched"])
        self.assertIn("NEVER automatically duplicated or transferred", res["warning"])

        # Even after acknowledging, REAL mode must have 0 positions (strict isolation)
        ctrl.switch_mode(TradingMode.REAL, actor="admin", acknowledge_open_positions=True)
        self.assertEqual(len(self.c["db"].list_positions("REAL")), 0)
        self.assertEqual(len(self.c["db"].list_positions("DEMO")), 1)

    def test_seven_step_live_authorization_and_withdrawal_key_rejection(self) -> None:
        ctrl = self.c["mode_controller"]
        # Reject key with withdrawal permissions
        self.c["registry"].register_connector("REAL", "BINANCE", MockLiveBroker("LIVE-ACC-9876", withdraw_allowed=True))
        ctrl.switch_mode(TradingMode.REAL, actor="admin", broker_name="BINANCE", acknowledge_open_positions=True)
        with self.assertRaises(ModeSwitchError):
            ctrl.enable_real_trading("BINANCE", "9876", LIVE_CONFIRMATION_PHRASE, True, actor="admin")

        # Register safe trade-only live broker
        self.c["registry"].register_connector("REAL", "BINANCE", MockLiveBroker("LIVE-ACC-9876", withdraw_allowed=False))
        # Wrong phrase rejected
        with self.assertRaises(ModeSwitchError):
            ctrl.enable_real_trading("BINANCE", "9876", "YES", True, actor="admin")
        # Valid 7-step authorization succeeds
        auth = ctrl.enable_real_trading("BINANCE", "9876", LIVE_CONFIRMATION_PHRASE, True, actor="admin")
        self.assertTrue(auth["authorized"])
        self.assertTrue(self.c["db"].get_mode_state()["real_trading_enabled"])

    def test_emergency_stop_halts_all_execution_and_cancels_pending(self) -> None:
        exec_engine = self.c["execution_engine"]
        paper = self.c["registry"].get_connector("DEMO", "PAPER")
        price = paper.get_ticker("BTCUSDT").ask
        exec_engine.submit_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            entry_price=round(price * 0.99, 2),
            stop_loss=round(price * 0.97, 2),
            take_profit=round(price * 1.03, 2),
            actor="admin",
        )
        res = self.c["mode_controller"].trigger_emergency_stop(actor="admin")
        self.assertTrue(res["emergency_stop_active"])
        self.assertEqual(res["cancelled_orders"], 1)
        with self.assertRaises(ModeSwitchError):
            self.c["mode_controller"].assert_execution_allowed("DEMO")


if __name__ == "__main__":
    unittest.main()
