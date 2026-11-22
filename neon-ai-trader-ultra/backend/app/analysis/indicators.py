"""Comprehensive Technical Indicator Suite using vectorized Pandas & NumPy."""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd


def compute_indicators(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Compute full technical analysis metrics:
    RSI, MACD, EMA(20/50/200), SMA(20/50), VWAP, Bollinger Bands, ATR, ADX,
    Stochastic, Ichimoku Cloud, Fibonacci retracements, Pivot points,
    Support/Resistance, Volume analysis, Breakout & Reversal detection.
    """
    if df.empty or len(df) < 30:
        raise ValueError("At least 30 candles are required to compute technical indicators.")

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)

    # Moving averages
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=min(200, len(df)), adjust=False).mean()
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(min(50, len(df))).mean()

    # RSI (14)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)

    # MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal

    # VWAP
    typical_price = (high + low + close) / 3.0
    cum_vol = volume.cumsum().replace(0, np.nan)
    vwap = ((typical_price * volume).cumsum() / cum_vol).fillna(close)

    # Bollinger Bands (20, 2)
    bb_mid = sma20
    bb_std = close.rolling(20).std().fillna(0.0)
    bb_upper = bb_mid + 2.0 * bb_std
    bb_lower = bb_mid - 2.0 * bb_std
    bb_width = ((bb_upper - bb_lower) / bb_mid.replace(0, np.nan)).fillna(0.0)

    # ATR (14)
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean().bfill()

    # ADX (14)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_di = 100.0 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / 14, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100.0 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / 14, adjust=False).mean() / atr.replace(0, np.nan)
    dx = (100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0.0)
    adx = dx.ewm(alpha=1 / 14, adjust=False).mean().fillna(0.0)

    # Stochastic (14, 3)
    lowest_14 = low.rolling(14).min()
    highest_14 = high.rolling(14).max()
    stoch_k = (100.0 * (close - lowest_14) / (highest_14 - lowest_14).replace(0, np.nan)).fillna(50.0)
    stoch_d = stoch_k.rolling(3).mean().fillna(50.0)

    # Ichimoku Cloud
    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2.0
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2.0
    senkou_a = ((tenkan + kijun) / 2.0).iloc[-1]
    senkou_b = ((high.rolling(min(52, len(df))).max() + low.rolling(min(52, len(df))).min()) / 2.0).iloc[-1]

    # Fibonacci retracements over last 50 bars
    recent_high = float(high.tail(50).max())
    recent_low = float(low.tail(50).min())
    fib_span = max(recent_high - recent_low, 1e-8)
    fib_levels = {
        "0.236": round(recent_high - 0.236 * fib_span, 5),
        "0.382": round(recent_high - 0.382 * fib_span, 5),
        "0.500": round(recent_high - 0.500 * fib_span, 5),
        "0.618": round(recent_high - 0.618 * fib_span, 5),
        "0.786": round(recent_high - 0.786 * fib_span, 5),
    }

    # Standard Pivot Points (from prior bar)
    p_high = float(high.iloc[-2])
    p_low = float(low.iloc[-2])
    p_close = float(close.iloc[-2])
    pivot = (p_high + p_low + p_close) / 3.0
    r1 = 2.0 * pivot - p_low
    s1 = 2.0 * pivot - p_high
    r2 = pivot + (p_high - p_low)
    s2 = pivot - (p_high - p_low)

    # Support & Resistance levels (rolling local extrema)
    support_levels: List[float] = sorted({round(float(low.tail(20).min()), 5), round(recent_low, 5), round(s1, 5)})
    resistance_levels: List[float] = sorted({round(float(high.tail(20).max()), 5), round(recent_high, 5), round(r1, 5)})

    # Volume analysis
    vol_sma20 = float(volume.rolling(20).mean().iloc[-1] or 1.0)
    vol_ratio = float(volume.iloc[-1]) / vol_sma20

    # Breakout & Reversal detection
    last_close = float(close.iloc[-1])
    prev_20_high = float(high.iloc[-21:-1].max())
    prev_20_low = float(low.iloc[-21:-1].min())
    breakout = "NONE"
    if last_close > prev_20_high and vol_ratio >= 1.1:
        breakout = "BULLISH_BREAKOUT"
    elif last_close < prev_20_low and vol_ratio >= 1.1:
        breakout = "BEARISH_BREAKOUT"

    reversal = "NONE"
    if float(rsi.iloc[-1]) < 30.0 and float(macd_hist.iloc[-1]) > float(macd_hist.iloc[-2]):
        reversal = "BULLISH_REVERSAL_CANDIDATE"
    elif float(rsi.iloc[-1]) > 70.0 and float(macd_hist.iloc[-1]) < float(macd_hist.iloc[-2]):
        reversal = "BEARISH_REVERSAL_CANDIDATE"

    # Trend classification
    if float(ema20.iloc[-1]) > float(ema50.iloc[-1]) > float(ema200.iloc[-1]):
        trend = "BULLISH"
    elif float(ema20.iloc[-1]) < float(ema50.iloc[-1]) < float(ema200.iloc[-1]):
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"

    return {
        "price": round(last_close, 5),
        "trend": trend,
        "rsi_14": round(float(rsi.iloc[-1]), 2),
        "macd": round(float(macd_line.iloc[-1]), 5),
        "macd_signal": round(float(macd_signal.iloc[-1]), 5),
        "macd_hist": round(float(macd_hist.iloc[-1]), 5),
        "ema_20": round(float(ema20.iloc[-1]), 5),
        "ema_50": round(float(ema50.iloc[-1]), 5),
        "ema_200": round(float(ema200.iloc[-1]), 5),
        "sma_20": round(float(sma20.iloc[-1]), 5),
        "sma_50": round(float(sma50.iloc[-1]), 5),
        "vwap": round(float(vwap.iloc[-1]), 5),
        "bb_upper": round(float(bb_upper.iloc[-1]), 5),
        "bb_mid": round(float(bb_mid.iloc[-1]), 5),
        "bb_lower": round(float(bb_lower.iloc[-1]), 5),
        "bb_width": round(float(bb_width.iloc[-1]), 5),
        "atr_14": round(float(atr.iloc[-1]), 5),
        "adx_14": round(float(adx.iloc[-1]), 2),
        "stoch_k": round(float(stoch_k.iloc[-1]), 2),
        "stoch_d": round(float(stoch_d.iloc[-1]), 2),
        "ichimoku": {
            "tenkan": round(float(tenkan.iloc[-1]), 5),
            "kijun": round(float(kijun.iloc[-1]), 5),
            "senkou_a": round(float(senkou_a), 5),
            "senkou_b": round(float(senkou_b), 5),
            "above_cloud": bool(last_close > max(float(senkou_a), float(senkou_b))),
            "below_cloud": bool(last_close < min(float(senkou_a), float(senkou_b))),
        },
        "fibonacci": fib_levels,
        "pivots": {
            "pivot": round(pivot, 5),
            "r1": round(r1, 5),
            "r2": round(r2, 5),
            "s1": round(s1, 5),
            "s2": round(s2, 5),
        },
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "volume_ratio": round(vol_ratio, 2),
        "breakout": breakout,
        "reversal": reversal,
    }
