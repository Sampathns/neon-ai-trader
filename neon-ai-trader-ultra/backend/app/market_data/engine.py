"""Market Data Reliability Engine: freshness checks, gap/duplicate detection, bounded retries."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.brokers.base import BrokerConnector, TickerQuote
from app.core.enums import DataFeedStatus


@dataclass
class DataQualityReport:
    is_valid: bool
    data_status: DataFeedStatus
    age_seconds: float
    duplicate_count: int = 0
    missing_candles: int = 0
    reasons: List[str] = field(default_factory=list)


class MarketDataEngine:
    """Validates market data integrity before any AI signal or order can be generated."""

    TIMEFRAME_SECONDS: Dict[str, int] = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
        "1w": 604800,
        "1M": 2592000,
    }

    def __init__(self, max_data_age_seconds: int = 60, max_reconnect_retries: int = 3) -> None:
        self.max_data_age_seconds = max_data_age_seconds
        self.max_reconnect_retries = max_reconnect_retries
        self.paused_symbols: Dict[str, str] = {}

    def _parse_iso(self, ts: str) -> datetime:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def ensure_connected(self, connector: BrokerConnector) -> bool:
        """Attempt bounded reconnection with exponential backoff."""
        health = connector.health_check()
        if health.get("status") == "CONNECTED":
            return True
        for attempt in range(self.max_reconnect_retries):
            res = connector.connect()
            if res.get("status") == "CONNECTED":
                return True
            time.sleep(min(0.05 * (2**attempt), 0.5))
        return False

    def validate_ticker(self, ticker: Optional[TickerQuote]) -> DataQualityReport:
        if ticker is None:
            return DataQualityReport(
                is_valid=False,
                data_status=DataFeedStatus.UNAVAILABLE,
                age_seconds=float("inf"),
                reasons=["Ticker data is unavailable."],
            )
        now = datetime.now(timezone.utc)
        ts = self._parse_iso(ticker.timestamp)
        age = max(0.0, (now - ts).total_seconds())
        reasons: List[str] = []
        if age > self.max_data_age_seconds:
            reasons.append(
                f"Stale ticker data ({age:.1f}s > max {self.max_data_age_seconds}s)."
            )
        if ticker.bid <= 0 or ticker.ask <= 0 or ticker.ask < ticker.bid:
            reasons.append("Invalid bid/ask quote values.")
        return DataQualityReport(
            is_valid=len(reasons) == 0,
            data_status=ticker.data_status if len(reasons) == 0 else DataFeedStatus.DELAYED,
            age_seconds=round(age, 2),
            reasons=reasons,
        )

    def fetch_validated_ohlcv(
        self,
        connector: BrokerConnector,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 200,
    ) -> Tuple[pd.DataFrame, DataQualityReport]:
        """Fetch OHLCV candles, deduplicate, detect missing bars, and enforce freshness."""
        raw = connector.get_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not raw:
            self.paused_symbols[symbol] = "No OHLCV candles returned by connector."
            return pd.DataFrame(), DataQualityReport(
                is_valid=False,
                data_status=DataFeedStatus.UNAVAILABLE,
                age_seconds=float("inf"),
                reasons=["No OHLCV data available from broker connector."],
            )

        df = pd.DataFrame(raw)
        original_len = len(df)
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        dup_count = original_len - len(df)

        timestamps = [self._parse_iso(t) for t in df["timestamp"].tolist()]
        expected_step = self.TIMEFRAME_SECONDS.get(timeframe, 3600)
        missing = 0
        for i in range(1, len(timestamps)):
            gap = (timestamps[i] - timestamps[i - 1]).total_seconds()
            if gap > expected_step * 1.5:
                missing += int(round(gap / expected_step)) - 1

        now = datetime.now(timezone.utc)
        age = max(0.0, (now - timestamps[-1]).total_seconds())
        # Allow up to timeframe duration + max_data_age_seconds for completed candles
        max_candle_age = max(self.max_data_age_seconds, expected_step + self.max_data_age_seconds)
        reasons: List[str] = []
        if age > max_candle_age:
            reasons.append(f"Stale OHLCV feed ({age:.1f}s old).")
        if len(df) < 50:
            reasons.append(f"Insufficient candle history ({len(df)} < 50 required).")

        status_str = raw[-1].get("data_status", DataFeedStatus.SIMULATED.value)
        try:
            feed_status = DataFeedStatus(status_str)
        except ValueError:
            feed_status = DataFeedStatus.SIMULATED

        is_valid = len(reasons) == 0
        if is_valid:
            self.paused_symbols.pop(symbol, None)
        else:
            self.paused_symbols[symbol] = "; ".join(reasons)

        return df, DataQualityReport(
            is_valid=is_valid,
            data_status=feed_status if is_valid else DataFeedStatus.DELAYED,
            age_seconds=round(age, 2),
            duplicate_count=dup_count,
            missing_candles=missing,
            reasons=reasons,
        )
