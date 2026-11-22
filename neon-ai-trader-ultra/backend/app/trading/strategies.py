"""Modular Strategy Engine supporting 7 independently toggleable strategies with conflict resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.enums import StrategyType


@dataclass
class StrategyDecision:
    strategy: StrategyType
    action: str  # "BUY", "SELL", "HOLD"
    rationale: str
    weight: float


class StrategyEngine:
    """
    Supports:
    - Trend Following
    - Breakout Trading
    - Pullback Trading
    - Momentum Trading
    - Mean Reversion
    - Volatility Strategies
    - Market Structure Strategies
    Resolves incompatible signals cleanly (defaults to HOLD on opposing consensus).
    """

    def __init__(self) -> None:
        self.enabled_strategies: Dict[StrategyType, bool] = {
            StrategyType.TREND_FOLLOWING: True,
            StrategyType.BREAKOUT: True,
            StrategyType.PULLBACK: True,
            StrategyType.MOMENTUM: True,
            StrategyType.MEAN_REVERSION: False,  # Disabled by default to avoid conflicting with trend-following
            StrategyType.VOLATILITY: False,
            StrategyType.MARKET_STRUCTURE: True,
        }

    def toggle_strategy(self, strategy: StrategyType, enabled: bool) -> Dict[str, bool]:
        self.enabled_strategies[strategy] = enabled
        return self.list_strategies()

    def list_strategies(self) -> Dict[str, bool]:
        return {k.value: v for k, v in self.enabled_strategies.items()}

    def evaluate(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        ind = signal.get("supporting_indicators", {})
        ms = signal.get("market_structure", {})
        if not ind:
            return {"action": "HOLD", "winning_strategy": None, "decisions": [], "conflict": False}

        decisions: List[StrategyDecision] = []

        if self.enabled_strategies[StrategyType.TREND_FOLLOWING]:
            if ind.get("trend") == "BULLISH" and ind.get("adx_14", 0) >= 20:
                decisions.append(StrategyDecision(StrategyType.TREND_FOLLOWING, "BUY", "Bullish EMA stack with ADX >= 20", 1.2))
            elif ind.get("trend") == "BEARISH" and ind.get("adx_14", 0) >= 20:
                decisions.append(StrategyDecision(StrategyType.TREND_FOLLOWING, "SELL", "Bearish EMA stack with ADX >= 20", 1.2))

        if self.enabled_strategies[StrategyType.BREAKOUT]:
            if ind.get("breakout") == "BULLISH_BREAKOUT":
                decisions.append(StrategyDecision(StrategyType.BREAKOUT, "BUY", "20-bar high breakout with volume", 1.1))
            elif ind.get("breakout") == "BEARISH_BREAKOUT":
                decisions.append(StrategyDecision(StrategyType.BREAKOUT, "SELL", "20-bar low breakdown with volume", 1.1))

        if self.enabled_strategies[StrategyType.PULLBACK]:
            rsi = ind.get("rsi_14", 50)
            if ind.get("trend") == "BULLISH" and 40 <= rsi <= 52:
                decisions.append(StrategyDecision(StrategyType.PULLBACK, "BUY", "Bullish trend pullback into neutral RSI zone", 1.0))
            elif ind.get("trend") == "BEARISH" and 48 <= rsi <= 60:
                decisions.append(StrategyDecision(StrategyType.PULLBACK, "SELL", "Bearish trend pullback into neutral RSI zone", 1.0))

        if self.enabled_strategies[StrategyType.MOMENTUM]:
            if ind.get("macd_hist", 0) > 0 and ind.get("rsi_14", 50) > 55:
                decisions.append(StrategyDecision(StrategyType.MOMENTUM, "BUY", "Positive MACD histogram & RSI > 55", 1.0))
            elif ind.get("macd_hist", 0) < 0 and ind.get("rsi_14", 50) < 45:
                decisions.append(StrategyDecision(StrategyType.MOMENTUM, "SELL", "Negative MACD histogram & RSI < 45", 1.0))

        if self.enabled_strategies[StrategyType.MEAN_REVERSION]:
            if ind.get("reversal") == "BULLISH_REVERSAL_CANDIDATE":
                decisions.append(StrategyDecision(StrategyType.MEAN_REVERSION, "BUY", "Oversold RSI mean-reversion candidate", 0.9))
            elif ind.get("reversal") == "BEARISH_REVERSAL_CANDIDATE":
                decisions.append(StrategyDecision(StrategyType.MEAN_REVERSION, "SELL", "Overbought RSI mean-reversion candidate", 0.9))

        if self.enabled_strategies[StrategyType.VOLATILITY]:
            if ms.get("volatility_expansion") and ind.get("macd_hist", 0) > 0:
                decisions.append(StrategyDecision(StrategyType.VOLATILITY, "BUY", "Volatility expansion upward", 0.9))
            elif ms.get("volatility_expansion") and ind.get("macd_hist", 0) < 0:
                decisions.append(StrategyDecision(StrategyType.VOLATILITY, "SELL", "Volatility expansion downward", 0.9))

        if self.enabled_strategies[StrategyType.MARKET_STRUCTURE]:
            if ms.get("break_of_structure") == "BULLISH_BOS":
                decisions.append(StrategyDecision(StrategyType.MARKET_STRUCTURE, "BUY", "Bullish Break of Structure", 1.1))
            elif ms.get("break_of_structure") == "BEARISH_BOS":
                decisions.append(StrategyDecision(StrategyType.MARKET_STRUCTURE, "SELL", "Bearish Break of Structure", 1.1))

        buy_weight = sum(d.weight for d in decisions if d.action == "BUY")
        sell_weight = sum(d.weight for d in decisions if d.action == "SELL")

        # Conflict resolution: incompatible simultaneous buy/sell signals require clear dominance or HOLD
        conflict = buy_weight > 0 and sell_weight > 0
        if buy_weight > sell_weight * 1.5 and buy_weight >= 1.1:
            final_action = "BUY"
            winning = next((d.strategy.value for d in decisions if d.action == "BUY"), None)
        elif sell_weight > buy_weight * 1.5 and sell_weight >= 1.1:
            final_action = "SELL"
            winning = next((d.strategy.value for d in decisions if d.action == "SELL"), None)
        else:
            final_action = "HOLD"
            winning = None

        return {
            "action": final_action,
            "winning_strategy": winning,
            "conflict": conflict,
            "buy_weight": round(buy_weight, 2),
            "sell_weight": round(sell_weight, 2),
            "decisions": [
                {"strategy": d.strategy.value, "action": d.action, "rationale": d.rationale, "weight": d.weight}
                for d in decisions
            ],
        }
