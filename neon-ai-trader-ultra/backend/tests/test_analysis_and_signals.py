"""Tests for Technical Indicators, Market Structure, Multi-Timeframe, News Dedup, ML Walk-Forward, and AI Signals."""

import unittest

from app.analysis.fundamentals_news import NewsIntelligenceEngine, NewsItem
from app.analysis.indicators import compute_indicators
from app.analysis.market_structure import analyze_market_structure
from app.core.config import Settings
from app.core.enums import AssetClass, SignalClassification
from app.main import create_app


class TestAnalysisAndSignals(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(settings=Settings(), db_path=":memory:")
        self.c = self.app.state.container
        self.paper = self.c["registry"].get_connector("DEMO", "PAPER")

    def test_technical_indicators_and_market_structure(self) -> None:
        df, quality = self.c["data_engine"].fetch_validated_ohlcv(self.paper, "BTCUSDT", "1h", 180)
        self.assertTrue(quality.is_valid)
        ind = compute_indicators(df)
        for key in ("rsi_14", "macd", "ema_20", "ema_50", "vwap", "bb_upper", "atr_14", "adx_14", "ichimoku", "fibonacci", "pivots"):
            self.assertIn(key, ind)
        self.assertGreaterEqual(ind["rsi_14"], 0.0)
        self.assertLessEqual(ind["rsi_14"], 100.0)

        ms = analyze_market_structure(df, ind)
        self.assertIn("regime", ms)
        self.assertIn("liquidity_zones", ms)

    def test_signal_generation_and_stale_data_forces_wait(self) -> None:
        sig_engine = self.c["signal_engine"]
        sig = sig_engine.generate_signal(self.paper, "BTCUSDT", AssetClass.CRYPTO, "1h")
        self.assertIn(sig["classification"], [s.value for s in SignalClassification])
        self.assertIn("confidence_estimate", sig)
        self.assertIn("historical_win_rate", sig)
        self.assertIn("estimated_probability", sig)
        self.assertEqual(sig["data_status"], "SIMULATED")

        # Stale data must force WAIT with 0 confidence
        self.paper.set_stale_feed_seconds(600)
        stale_sig = sig_engine.generate_signal(self.paper, "BTCUSDT", AssetClass.CRYPTO, "1h")
        self.assertEqual(stale_sig["classification"], SignalClassification.WAIT.value)
        self.assertEqual(stale_sig["confidence_estimate"], 0.0)
        self.paper.set_stale_feed_seconds(None)

    def test_news_deduplication_and_source_requirement(self) -> None:
        news = NewsIntelligenceEngine()
        item1 = NewsItem("BTCUSDT exchange volume rises", "Reuters", "2026-11-22T10:00:00Z", "https://example.com/1", "MARKET", True, 0.4)
        item_dup = NewsItem("BTCUSDT exchange volume rises", "Reuters", "2026-11-22T10:00:00Z", "https://example.com/1", "MARKET", True, 0.4)
        item_unattributed = NewsItem("Rumor", "", "", "", "RUMOR", False, -0.5)
        added = news.ingest([item1, item_dup, item_unattributed])
        self.assertEqual(added, 1)
        ctx = news.get_context("BTCUSDT")
        self.assertTrue(ctx["configured"])
        self.assertEqual(ctx["confirmed_count"], 1)


if __name__ == "__main__":
    unittest.main()
