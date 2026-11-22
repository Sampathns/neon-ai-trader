"""Fundamental & News Intelligence Adapters (zero fabrication; source + timestamp mandatory)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.enums import AssetClass


@dataclass
class NewsItem:
    title: str
    source: str
    published_at: str
    url: str
    category: str
    is_confirmed_fact: bool
    sentiment_score: float  # -1.0 to +1.0 derived from external provider or lexical classifier
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            norm = f"{self.title.strip().lower()}|{self.source.strip().lower()}"
            self.fingerprint = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


class NewsIntelligenceEngine:
    """
    Ingests verified external news items, deduplicates stories, distinguishes
    confirmed facts from speculation, and never fabricates headlines or sentiment.
    """

    def __init__(self) -> None:
        self._seen_fingerprints: set[str] = set()
        self._items: List[NewsItem] = []

    def ingest(self, items: List[NewsItem]) -> int:
        added = 0
        for item in items:
            if not item.source or not item.published_at:
                continue  # Reject unattributed or untimestamped items
            if item.fingerprint in self._seen_fingerprints:
                continue
            self._seen_fingerprints.add(item.fingerprint)
            self._items.append(item)
            added += 1
        return added

    def get_context(self, symbol: str) -> Dict[str, Any]:
        sym = symbol.upper()
        matched = [
            it
            for it in self._items
            if sym in it.title.upper() or sym[:3] in it.title.upper()
        ]
        if not matched:
            return {
                "configured": False,
                "status": "NO_VERIFIED_NEWS_FEED_CONFIGURED",
                "sentiment_score": 0.0,
                "confirmed_count": 0,
                "speculation_count": 0,
                "items": [],
                "note": "No verified live news feed configured; neutral weight applied (no fabricated headlines).",
            }

        avg_sentiment = sum(it.sentiment_score for it in matched) / len(matched)
        return {
            "configured": True,
            "status": "ACTIVE",
            "sentiment_score": round(avg_sentiment, 3),
            "confirmed_count": sum(1 for it in matched if it.is_confirmed_fact),
            "speculation_count": sum(1 for it in matched if not it.is_confirmed_fact),
            "items": [
                {
                    "title": it.title,
                    "source": it.source,
                    "published_at": it.published_at,
                    "url": it.url,
                    "category": it.category,
                    "is_confirmed_fact": it.is_confirmed_fact,
                    "sentiment_score": it.sentiment_score,
                }
                for it in matched[-10:]
            ],
        }


class FundamentalAnalyzer:
    """
    Asset-class-aware fundamental context adapter.
    Returns explicit unconfigured status when external economic/fundamental APIs
    are not supplied rather than inventing earnings, CPI, or central-bank figures.
    """

    def __init__(self) -> None:
        self._external_snapshots: Dict[str, Dict[str, Any]] = {}

    def register_snapshot(self, symbol: str, snapshot: Dict[str, Any]) -> None:
        self._external_snapshots[symbol.upper()] = snapshot

    def analyze(self, symbol: str, asset_class: AssetClass) -> Dict[str, Any]:
        snap = self._external_snapshots.get(symbol.upper())
        if snap:
            return {
                "configured": True,
                "asset_class": asset_class.value,
                "bias_score": float(snap.get("bias_score", 0.0)),
                "metrics": snap.get("metrics", {}),
                "source": snap.get("source", "EXTERNAL_PROVIDER"),
                "as_of": snap.get("as_of"),
            }

        expected_drivers = {
            AssetClass.FOREX: ["Central bank policy rates", "CPI inflation", "Employment/NFP", "GDP growth"],
            AssetClass.CRYPTO: ["Exchange liquidity", "Regulatory announcements", "Funding rates", "On-chain volume"],
            AssetClass.EQUITIES: ["Earnings", "Revenue growth", "Free cash flow", "Valuation multiples"],
            AssetClass.METALS: ["Real yields", "USD strength", "Central bank reserves", "Inflation expectations"],
            AssetClass.INDICES: ["Macro growth", "Monetary policy", "Aggregate corporate earnings"],
        }.get(asset_class, ["Macro supply & demand"])

        return {
            "configured": False,
            "asset_class": asset_class.value,
            "bias_score": 0.0,
            "expected_drivers": expected_drivers,
            "note": "External fundamental data provider not configured; neutral 0.0 score applied.",
        }
