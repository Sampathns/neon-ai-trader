"""Multi-Factor AI Signal Generation Engine with calibrated scoring and WAIT fallback."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.analysis.fundamentals_news import FundamentalAnalyzer, NewsIntelligenceEngine
from app.analysis.indicators import compute_indicators
from app.analysis.market_structure import analyze_market_structure
from app.analysis.ml_pipeline import CalibratedWalkForwardModel
from app.analysis.multi_timeframe import analyze_multi_timeframe
from app.brokers.base import BrokerConnector
from app.core.enums import AssetClass, DataFeedStatus, SignalClassification
from app.market_data.engine import MarketDataEngine


class AISignalEngine:
    """
    Combines 10 structured factors into a calibrated trading signal:
    1. Trend  2. Momentum  3. Market structure  4. Volatility  5. Volume
    6. Multi-timeframe agreement  7. Fundamental context  8. News & sentiment
    9. Liquidity & spread  10. Risk/Reward geometry.
    Outputs WAIT whenever data is stale, incomplete, or evidence is insufficient.
    """

    def __init__(
        self,
        data_engine: MarketDataEngine,
        news_engine: NewsIntelligenceEngine,
        fundamental_analyzer: FundamentalAnalyzer,
    ) -> None:
        self.data_engine = data_engine
        self.news_engine = news_engine
        self.fundamental_analyzer = fundamental_analyzer
        self.ml_model = CalibratedWalkForwardModel()

    def generate_signal(
        self,
        connector: BrokerConnector,
        symbol: str,
        asset_class: AssetClass = AssetClass.CRYPTO,
        timeframe: str = "1h",
    ) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        ticker = connector.get_ticker(symbol)
        ticker_quality = self.data_engine.validate_ticker(ticker)
        df, ohlcv_quality = self.data_engine.fetch_validated_ohlcv(
            connector, symbol, timeframe=timeframe, limit=200
        )

        # Never generate an actionable signal from stale or unavailable data
        if not ticker_quality.is_valid or not ohlcv_quality.is_valid or ticker is None or df.empty:
            reasons = ticker_quality.reasons + ohlcv_quality.reasons
            return {
                "id": str(uuid.uuid4()),
                "symbol": symbol.upper(),
                "asset_class": asset_class.value,
                "classification": SignalClassification.WAIT.value,
                "direction": "NEUTRAL",
                "current_price": ticker.last if ticker else 0.0,
                "entry_zone": [0.0, 0.0],
                "stop_loss": 0.0,
                "take_profit_levels": [0.0, 0.0],
                "risk_reward_ratio": 0.0,
                "relevant_timeframes": [timeframe],
                "supporting_indicators": {},
                "market_regime": "UNKNOWN",
                "market_structure_explanation": "Analysis paused due to stale or unavailable market data.",
                "fundamental_context": self.fundamental_analyzer.analyze(symbol, asset_class),
                "news_context": self.news_engine.get_context(symbol),
                "signal_timestamp": now_iso,
                "data_freshness_seconds": ticker_quality.age_seconds,
                "data_status": DataFeedStatus.UNAVAILABLE.value if ticker is None else DataFeedStatus.DELAYED.value,
                "invalidation_conditions": reasons,
                "confidence_estimate": 0.0,
                "historical_win_rate": 0.0,
                "estimated_probability": 0.5,
                "bullish_factors": [],
                "bearish_factors": [],
                "risk_conditions": reasons,
            }

        indicators = compute_indicators(df)
        structure = analyze_market_structure(df, indicators)
        mtf = analyze_multi_timeframe(connector, self.data_engine, symbol, ["15m", timeframe, "4h", "1d"])
        fundamentals = self.fundamental_analyzer.analyze(symbol, asset_class)
        news = self.news_engine.get_context(symbol)
        prob_up, wf_metrics = self.ml_model.walk_forward_evaluate_and_fit(df)

        bullish_factors: List[str] = []
        bearish_factors: List[str] = []
        risk_conditions: List[str] = []
        score = 0.0  # -100 to +100 composite

        # 1. Trend
        if indicators["trend"] == "BULLISH":
            score += 20.0
            bullish_factors.append("EMA20 > EMA50 > EMA200 bullish trend alignment")
        elif indicators["trend"] == "BEARISH":
            score -= 20.0
            bearish_factors.append("EMA20 < EMA50 < EMA200 bearish trend alignment")

        if indicators["ichimoku"]["above_cloud"]:
            score += 8.0
            bullish_factors.append("Price trading above Ichimoku Cloud")
        elif indicators["ichimoku"]["below_cloud"]:
            score -= 8.0
            bearish_factors.append("Price trading below Ichimoku Cloud")

        # 2. Momentum
        rsi = indicators["rsi_14"]
        if 52 <= rsi <= 68 and indicators["macd_hist"] > 0:
            score += 14.0
            bullish_factors.append(f"Constructive bullish momentum (RSI={rsi:.1f}, MACD hist > 0)")
        elif 32 <= rsi <= 48 and indicators["macd_hist"] < 0:
            score -= 14.0
            bearish_factors.append(f"Constructive bearish momentum (RSI={rsi:.1f}, MACD hist < 0)")
        elif rsi > 75:
            risk_conditions.append(f"Overbought RSI ({rsi:.1f}) increases pullback risk")
            score -= 6.0
        elif rsi < 25:
            risk_conditions.append(f"Oversold RSI ({rsi:.1f}) increases mean-reversion bounce risk")
            score += 6.0

        # 3. Market Structure
        if structure["break_of_structure"] == "BULLISH_BOS":
            score += 12.0
            bullish_factors.append("Bullish Break of Structure confirmed on recent swing high")
        elif structure["break_of_structure"] == "BEARISH_BOS":
            score -= 12.0
            bearish_factors.append("Bearish Break of Structure confirmed on recent swing low")

        # 4. Volatility & 5. Volume
        if indicators["volume_ratio"] >= 1.2:
            if score > 0:
                score += 6.0
                bullish_factors.append(f"Above-average volume confirmation ({indicators['volume_ratio']:.2f}x)")
            elif score < 0:
                score -= 6.0
                bearish_factors.append(f"Above-average selling volume ({indicators['volume_ratio']:.2f}x)")
        if structure["consolidation"]:
            risk_conditions.append("Low-volatility consolidation regime; breakout confirmation preferred")
            score *= 0.65

        # 6. Multi-Timeframe agreement
        if mtf["timeframe_conflict"]:
            risk_conditions.append("Higher-timeframe vs lower-timeframe trend conflict detected")
            score *= 0.6
        elif mtf["higher_timeframe_bias"] == "BULLISH" and score > 0:
            score += 12.0 * mtf["agreement_score"]
            bullish_factors.append(f"Higher-timeframe bullish alignment ({mtf['agreement_score']*100:.0f}%)")
        elif mtf["higher_timeframe_bias"] == "BEARISH" and score < 0:
            score -= 12.0 * mtf["agreement_score"]
            bearish_factors.append(f"Higher-timeframe bearish alignment ({mtf['agreement_score']*100:.0f}%)")

        # 7. Fundamentals & 8. News (only when configured)
        score += float(fundamentals.get("bias_score", 0.0)) * 10.0
        score += float(news.get("sentiment_score", 0.0)) * 10.0

        # 9. Liquidity & Spread
        if ticker.spread_bps > 20.0:
            risk_conditions.append(f"Elevated spread ({ticker.spread_bps:.1f} bps)")
            score *= 0.5

        # ML Walk-Forward Out-of-Sample Calibration Blending
        ml_edge = (prob_up - 0.5) * 40.0
        if wf_metrics.drift_detected:
            risk_conditions.append(f"Feature drift detected (z={wf_metrics.feature_drift_zscore:.2f}); ML weight reduced")
            ml_edge *= 0.3
        score += ml_edge

        # 10. Entry, Stop-Loss, Take-Profit & R/R geometry
        price = ticker.last
        atr = max(indicators["atr_14"], price * 0.002)
        if score >= 18.0:
            direction = "LONG"
            entry_zone = [round(price - 0.25 * atr, 5), round(price + 0.15 * atr, 5)]
            stop_loss = round(price - 1.5 * atr, 5)
            tp1 = round(price + 2.25 * atr, 5)
            tp2 = round(price + 3.5 * atr, 5)
            invalidation = [
                f"Close below stop-loss {stop_loss}",
                f"Bearish CHoCH below demand zone {structure['demand_zone'][0]}",
            ]
        elif score <= -18.0:
            direction = "SHORT"
            entry_zone = [round(price - 0.15 * atr, 5), round(price + 0.25 * atr, 5)]
            stop_loss = round(price + 1.5 * atr, 5)
            tp1 = round(price - 2.25 * atr, 5)
            tp2 = round(price - 3.5 * atr, 5)
            invalidation = [
                f"Close above stop-loss {stop_loss}",
                f"Bullish CHoCH above supply zone {structure['supply_zone'][1]}",
            ]
        else:
            direction = "NEUTRAL"
            entry_zone = [round(price - 0.2 * atr, 5), round(price + 0.2 * atr, 5)]
            stop_loss = round(price - 1.5 * atr, 5)
            tp1 = round(price + 2.25 * atr, 5)
            tp2 = round(price + 3.5 * atr, 5)
            invalidation = ["Insufficient directional edge; wait for clearer structure or MTF alignment."]

        rr = round(abs(tp1 - price) / max(abs(price - stop_loss), 1e-8), 2)

        # Calibrated confidence bounded by out-of-sample Brier skill & factor agreement (never fabricated 99%)
        raw_strength = min(abs(score) / 70.0, 1.0)
        calibration_factor = max(0.35, min(0.9, 1.0 - wf_metrics.brier_score))
        confidence = round(min(0.88, raw_strength * calibration_factor), 3)

        if direction == "LONG" and score >= 42.0 and confidence >= 0.55 and not mtf["timeframe_conflict"]:
            classification = SignalClassification.STRONG_BUY
        elif direction == "LONG" and score >= 18.0:
            classification = SignalClassification.BUY
        elif direction == "SHORT" and score <= -42.0 and confidence >= 0.55 and not mtf["timeframe_conflict"]:
            classification = SignalClassification.STRONG_SELL
        elif direction == "SHORT" and score <= -18.0:
            classification = SignalClassification.SELL
        else:
            classification = SignalClassification.WAIT
            direction = "NEUTRAL"

        est_prob = prob_up if direction != "SHORT" else round(1.0 - prob_up, 4)

        return {
            "id": str(uuid.uuid4()),
            "symbol": symbol.upper(),
            "asset_class": asset_class.value,
            "classification": classification.value,
            "direction": direction,
            "current_price": price,
            "entry_zone": entry_zone,
            "stop_loss": stop_loss,
            "take_profit_levels": [tp1, tp2],
            "risk_reward_ratio": rr,
            "relevant_timeframes": list(mtf["timeframes"].keys()),
            "supporting_indicators": {
                "trend": indicators["trend"],
                "rsi_14": indicators["rsi_14"],
                "macd_hist": indicators["macd_hist"],
                "adx_14": indicators["adx_14"],
                "atr_14": indicators["atr_14"],
                "vwap": indicators["vwap"],
                "volume_ratio": indicators["volume_ratio"],
                "breakout": indicators["breakout"],
                "reversal": indicators["reversal"],
                "pivots": indicators["pivots"],
                "fibonacci": indicators["fibonacci"],
            },
            "market_regime": structure["regime"],
            "market_structure_explanation": structure["explanation"],
            "market_structure": structure,
            "multi_timeframe": mtf,
            "fundamental_context": fundamentals,
            "news_context": news,
            "signal_timestamp": now_iso,
            "data_freshness_seconds": ticker_quality.age_seconds,
            "data_status": ticker_quality.data_status.value,
            "invalidation_conditions": invalidation,
            "confidence_estimate": confidence,
            "historical_win_rate": wf_metrics.historical_win_rate,
            "estimated_probability": est_prob,
            "model_diagnostics": {
                "model_version": wf_metrics.model_version,
                "oos_accuracy": wf_metrics.out_of_sample_accuracy,
                "brier_score": wf_metrics.brier_score,
                "oos_samples": wf_metrics.sample_count,
                "drift_zscore": wf_metrics.feature_drift_zscore,
                "drift_detected": wf_metrics.drift_detected,
            },
            "bullish_factors": bullish_factors,
            "bearish_factors": bearish_factors,
            "risk_conditions": risk_conditions,
        }
