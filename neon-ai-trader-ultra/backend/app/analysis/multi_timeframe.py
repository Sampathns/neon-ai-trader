"""Multi-Timeframe Intelligence Engine (1m to 1M) with HTF context and conflict detection."""

from __future__ import annotations

from typing import Any, Dict, List

from app.analysis.indicators import compute_indicators
from app.brokers.base import BrokerConnector
from app.market_data.engine import MarketDataEngine


ALL_TIMEFRAMES: List[str] = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"]
HIGHER_TIMEFRAMES: List[str] = ["4h", "1d", "1w", "1M"]
LOWER_TIMEFRAMES: List[str] = ["1m", "5m", "15m", "30m", "1h"]


def analyze_multi_timeframe(
    connector: BrokerConnector,
    data_engine: MarketDataEngine,
    symbol: str,
    timeframes: List[str] | None = None,
) -> Dict[str, Any]:
    """
    Evaluate trend and momentum across multiple timeframes, separate HTF context
    from LTF entry timing, and explicitly flag inter-timeframe conflicts.
    """
    selected = timeframes or ["15m", "1h", "4h", "1d"]
    per_tf: Dict[str, Dict[str, Any]] = {}
    bullish_htf = 0
    bearish_htf = 0
    bullish_ltf = 0
    bearish_ltf = 0

    for tf in selected:
        df, quality = data_engine.fetch_validated_ohlcv(connector, symbol, timeframe=tf, limit=120)
        if df.empty or len(df) < 35:
            per_tf[tf] = {"trend": "UNAVAILABLE", "valid": False, "reasons": quality.reasons}
            continue
        ind = compute_indicators(df)
        trend = ind["trend"]
        per_tf[tf] = {
            "trend": trend,
            "rsi_14": ind["rsi_14"],
            "adx_14": ind["adx_14"],
            "macd_hist": ind["macd_hist"],
            "valid": quality.is_valid,
            "data_status": quality.data_status.value,
        }
        if tf in HIGHER_TIMEFRAMES:
            if trend == "BULLISH":
                bullish_htf += 1
            elif trend == "BEARISH":
                bearish_htf += 1
        else:
            if trend == "BULLISH":
                bullish_ltf += 1
            elif trend == "BEARISH":
                bearish_ltf += 1

    htf_bias = (
        "BULLISH" if bullish_htf > bearish_htf else ("BEARISH" if bearish_htf > bullish_htf else "NEUTRAL")
    )
    ltf_bias = (
        "BULLISH" if bullish_ltf > bearish_ltf else ("BEARISH" if bearish_ltf > bullish_ltf else "NEUTRAL")
    )

    conflict = htf_bias != "NEUTRAL" and ltf_bias != "NEUTRAL" and htf_bias != ltf_bias
    valid_count = sum(1 for v in per_tf.values() if v.get("trend") in ("BULLISH", "BEARISH", "NEUTRAL"))
    aligned_count = sum(1 for v in per_tf.values() if v.get("trend") == htf_bias and htf_bias != "NEUTRAL")
    agreement_score = round(aligned_count / max(valid_count, 1), 3)

    return {
        "timeframes": per_tf,
        "higher_timeframe_bias": htf_bias,
        "lower_timeframe_bias": ltf_bias,
        "timeframe_conflict": conflict,
        "agreement_score": agreement_score,
        "summary": (
            f"HTF bias is {htf_bias}, LTF entry bias is {ltf_bias}. "
            + ("CONFLICT detected between higher and lower timeframes." if conflict else "Timeframes aligned or neutral.")
        ),
    }
