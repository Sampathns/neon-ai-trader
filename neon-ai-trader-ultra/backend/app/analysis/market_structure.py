"""Objective Market Structure & Regime Classification Engine."""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

from app.core.enums import MarketRegime


def analyze_market_structure(df: pd.DataFrame, indicators: Dict[str, Any]) -> Dict[str, Any]:
    """
    Identify objective price-action structure:
    HH, HL, LH, LL, Break of Structure (BOS), Change of Character (CHoCH),
    Liquidity zones (clustered highs/lows), Supply/Demand zones, Price imbalances,
    Volatility expansion, Consolidation, and Trend exhaustion.
    Never labels ordinary price movement as confirmed institutional activity.
    """
    highs = df["high"].astype(float).values
    lows = df["low"].astype(float).values
    closes = df["close"].astype(float).values

    swing_highs: List[float] = []
    swing_lows: List[float] = []
    window = 3
    for i in range(window, len(df) - window):
        if highs[i] == np.max(highs[i - window : i + window + 1]):
            swing_highs.append(float(highs[i]))
        if lows[i] == np.min(lows[i - window : i + window + 1]):
            swing_lows.append(float(lows[i]))

    structure_tags: List[str] = []
    if len(swing_highs) >= 2:
        structure_tags.append("HH" if swing_highs[-1] > swing_highs[-2] else "LH")
    if len(swing_lows) >= 2:
        structure_tags.append("HL" if swing_lows[-1] > swing_lows[-2] else "LL")

    last_close = float(closes[-1])
    bos = "NONE"
    choch = "NONE"
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        if last_close > swing_highs[-1]:
            bos = "BULLISH_BOS"
            if "LH" in structure_tags:
                choch = "BULLISH_CHOCH"
        elif last_close < swing_lows[-1]:
            bos = "BEARISH_BOS"
            if "HL" in structure_tags:
                choch = "BEARISH_CHOCH"

    # Detect 3-candle price imbalances (Fair Value Gaps)
    imbalances: List[Dict[str, Any]] = []
    for i in range(max(2, len(df) - 30), len(df)):
        if lows[i] > highs[i - 2]:
            imbalances.append(
                {"type": "BULLISH_IMBALANCE", "low": round(float(highs[i - 2]), 5), "high": round(float(lows[i]), 5)}
            )
        elif highs[i] < lows[i - 2]:
            imbalances.append(
                {"type": "BEARISH_IMBALANCE", "low": round(float(highs[i]), 5), "high": round(float(lows[i - 2]), 5)}
            )

    # Supply/demand & liquidity zones derived strictly from observed swing clusters
    demand_zone = (
        [round(min(swing_lows[-2:]), 5), round(max(swing_lows[-2:]), 5)]
        if len(swing_lows) >= 2
        else [round(float(np.min(lows[-20:])), 5), round(float(np.min(lows[-10:])), 5)]
    )
    supply_zone = (
        [round(min(swing_highs[-2:]), 5), round(max(swing_highs[-2:]), 5)]
        if len(swing_highs) >= 2
        else [round(float(np.max(highs[-10:])), 5), round(float(np.max(highs[-20:])), 5)]
    )
    liquidity_zones = {
        "buy_side_resting_above": round(float(np.max(highs[-30:])), 5),
        "sell_side_resting_below": round(float(np.min(lows[-30:])), 5),
    }

    # Regime classification
    adx = indicators["adx_14"]
    bb_width = indicators["bb_width"]
    rsi = indicators["rsi_14"]
    trend = indicators["trend"]

    if bb_width > 0.06 and adx > 28:
        regime = MarketRegime.HIGH_VOLATILITY_EXPANSION
    elif adx >= 22 and trend == "BULLISH":
        regime = MarketRegime.TREND_EXHAUSTION if rsi > 76 else MarketRegime.TRENDING_BULLISH
    elif adx >= 22 and trend == "BEARISH":
        regime = MarketRegime.TREND_EXHAUSTION if rsi < 24 else MarketRegime.TRENDING_BEARISH
    elif bb_width < 0.025 or adx < 18:
        regime = MarketRegime.RANGING_CONSOLIDATION
    else:
        regime = MarketRegime.UNKNOWN

    explanation = (
        f"Observed swings {structure_tags or ['INSUFFICIENT']} with {bos} and {choch}; "
        f"regime classified as {regime.value} (ADX={adx:.1f}, BB width={bb_width:.4f})."
    )

    return {
        "regime": regime.value,
        "structure_tags": structure_tags,
        "break_of_structure": bos,
        "change_of_character": choch,
        "demand_zone": demand_zone,
        "supply_zone": supply_zone,
        "liquidity_zones": liquidity_zones,
        "recent_imbalances": imbalances[-5:],
        "volatility_expansion": bool(bb_width > 0.05),
        "consolidation": bool(bb_width < 0.025 and adx < 18),
        "trend_exhaustion": bool(regime == MarketRegime.TREND_EXHAUSTION),
        "explanation": explanation,
    }
