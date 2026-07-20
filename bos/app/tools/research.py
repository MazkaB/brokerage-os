"""
Research tool - deterministic mock market-data feed (Phase 1).

Stands in for Bloomberg / Yahoo Finance / SEC Filings / News APIs (Phase 2).
All values are deterministic given the same input for reproducible tests.
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, List, Optional

from .base import ToolResult

log = logging.getLogger("bos.tools.research")


def _seed_float(symbol: str, salt: str = "") -> float:
    h = hashlib.sha256(f"{symbol}{salt}".encode()).hexdigest()
    # Map first 8 hex chars to 0..1
    return int(h[:8], 16) / 0xFFFFFFFF


_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "JPM", "BAC", "XOM"]
_FUND_NAMES = ["Stable Growth Fund", "Aggressive Tech Fund", "Bond Income Fund", "ESG Balanced Fund"]


class ResearchTool:
    def market_news(self, topic: Optional[str] = None, limit: int = 5) -> ToolResult:
        rng = topic or "markets"
        headlines = [
            f"{rng} sentiment steady amid rate-decision anticipation",
            f"Volatility index moves on {rng} sector rotation",
            f"Analysts revise outlook for {rng} baskets",
            f"Earnings season preview: {rng} in focus",
            f"Liquidity conditions normalize across {rng}",
        ][:limit]
        news = [
            {"headline": h, "source": "BOS Mock Wire", "ts": time.time() - i * 600}
            for i, h in enumerate(headlines)
        ]
        return ToolResult(
            ok=True,
            data={"news": news, "topic": rng},
            tools_used=["research.market_news"],
            citations=["mock://market_news"],
        )

    def security(self, symbol: str) -> ToolResult:
        s = (symbol or "").upper().strip()
        if not s:
            return ToolResult(ok=False, error="symbol required")
        base = 50.0 + _seed_float(s, "px") * 450.0      # 50 .. 500
        change = (_seed_float(s, "ch") - 0.5) * 6.0      # -3% .. +3%
        price = round(base * (1 + change / 100.0), 2)
        pe = round(8 + _seed_float(s, "pe") * 35, 2)
        mcap = round(5 + _seed_float(s, "mcap") * 495, 2)  # in $B
        return ToolResult(
            ok=True,
            data={
                "symbol": s,
                "price_usd": price,
                "change_pct": round(change, 2),
                "pe_ratio": pe,
                "market_cap_b": mcap,
                "rating": ("buy" if change > 0.5 else "sell" if change < -0.5 else "hold"),
                "as_of": time.time(),
                "source": "BOS Mock Market Data",
            },
            tools_used=["research.security"],
            citations=["mock://security/" + s],
        )

    def compare_funds(self, funds: Optional[List[str]] = None) -> ToolResult:
        names = funds or _FUND_NAMES[:3]
        rows = []
        for name in names:
            base_score = _seed_float(name, "score")
            rows.append({
                "fund": name,
                "ytd_return_pct": round((base_score - 0.4) * 30, 2),
                "expense_ratio": round(0.1 + _seed_float(name, "exp") * 0.9, 2),
                "risk_band": "low" if base_score > 0.66 else "medium" if base_score > 0.33 else "high",
                "sharpe": round(0.4 + base_score * 1.8, 2),
            })
        return ToolResult(
            ok=True,
            data={"funds": rows},
            tools_used=["research.compare_funds"],
            citations=["mock://funds"],
        )


_singleton: Optional[ResearchTool] = None


def _inst() -> ResearchTool:
    global _singleton
    if _singleton is None:
        _singleton = ResearchTool()
    return _singleton


def research_market_news(topic: Optional[str] = None, limit: int = 5) -> ToolResult:
    return _inst().market_news(topic=topic, limit=limit)


def research_security(symbol: str) -> ToolResult:
    return _inst().security(symbol)


def research_compare_funds(funds: Optional[List[str]] = None) -> ToolResult:
    return _inst().compare_funds(funds=funds)
