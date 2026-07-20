"""
Bloomberg adapter (Phase 2).

Wraps the Bloomberg Data License API (BQL) for securities reference data,
historical pricing, and news. Falls back to the deterministic mock when
no API key is configured.

Setup:
    Set environment variables:
      BLOOMBERG_API_KEY, BLOOMBERG_API_SECRET
      BLOOMBERG_ACCOUNT_ID

The Bloomberg Data License uses signed HMAC requests. This module handles
the auth dance; callers just pass ticker symbols.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any, Dict, List, Optional

from .base import ToolResult

log = logging.getLogger("bos.tools.bloomberg")


def is_configured() -> bool:
    return all(os.environ.get(k) for k in (
        "BLOOMBERG_API_KEY", "BLOOMBERG_API_SECRET", "BLOOMBERG_ACCOUNT_ID",
    ))


def _signed_request(payload: dict) -> Optional[dict]:
    """Send a signed BQL request to Bloomberg Data License."""
    if not is_configured():
        return None
    try:
        import httpx
        api_key = os.environ["BLOOMBERG_API_KEY"]
        api_secret = os.environ["BLOOMBERG_API_SECRET"]
        timestamp = str(int(time.time()))
        body = str(payload).encode()
        signature = hmac.new(
            api_secret.encode(), body + timestamp.encode(), hashlib.sha256
        ).hexdigest()
        r = httpx.post(
            "https://api.bloomberg.com/e/data-license/v2/bql",
            headers={
                "X-BBG-API-Key": api_key,
                "X-BBG-API-Signature": signature,
                "X-BBG-API-Timestamp": timestamp,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("Bloomberg API call failed: %s", e)
        return None


def get_security(symbol: str) -> ToolResult:
    """Get reference data + last price for a ticker."""
    if not is_configured():
        return _mock_get_security(symbol)
    response = _signed_request({
        "account": os.environ["BLOOMBERG_ACCOUNT_ID"],
        "fields": ["PX_LAST", "VOLUME", "MARKET_CAP", "PE_RATIO", "GROWTH_5YR"],
        "securities": [symbol],
    })
    if not response or "data" not in response:
        return _mock_get_security(symbol)
    try:
        item = response["data"][0]
        return ToolResult(
            ok=True,
            data={
                "symbol": symbol,
                "price_usd": float(item.get("PX_LAST", 0)),
                "volume": int(item.get("VOLUME", 0)),
                "market_cap_b": float(item.get("MARKET_CAP", 0)) / 1e9,
                "pe_ratio": float(item.get("PE_RATIO", 0)),
                "growth_5y_pct": float(item.get("GROWTH_5YR", 0)),
                "source": "bloomberg",
                "as_of": time.time(),
            },
            tools_used=["bloomberg.get_security"],
            citations=["bloomberg://" + symbol],
        )
    except (KeyError, IndexError) as e:
        return _mock_get_security(symbol)


def get_historical(symbol: str, days: int = 30) -> ToolResult:
    """Historical daily closes for the last N days."""
    if not is_configured():
        return _mock_get_historical(symbol, days)
    response = _signed_request({
        "account": os.environ["BLOOMBERG_ACCOUNT_ID"],
        "fields": ["PX_LAST(dates=range('-%dd','0d'))" % days],
        "securities": [symbol],
    })
    if not response:
        return _mock_get_historical(symbol, days)
    # Transform: list of {date, close}
    series = response.get("data", {}).get("PX_LAST", [])
    return ToolResult(
        ok=True,
        data={"symbol": symbol, "series": series, "source": "bloomberg"},
        tools_used=["bloomberg.get_historical"],
        citations=["bloomberg://history/" + symbol],
    )


def get_news(query: str, limit: int = 10) -> ToolResult:
    """Get news headlines matching a query."""
    if not is_configured():
        return _mock_get_news(query, limit)
    # Bloomberg has a separate News API; this is illustrative
    response = _signed_request({"query": query, "limit": limit, "type": "news"})
    if not response:
        return _mock_get_news(query, limit)
    headlines = [{"headline": h, "ts": ts, "source": "bloomberg"}
                 for h, ts in response.get("news", [])]
    return ToolResult(
        ok=True, data={"news": headlines},
        tools_used=["bloomberg.get_news"],
        citations=["bloomberg://news/" + query],
    )


# ---------------------------------------------------------------------------
# Mock fallbacks (deterministic, same shape as real API output)
# ---------------------------------------------------------------------------
def _mock_get_security(symbol: str) -> ToolResult:
    """Deterministic mock matching the Bloomberg response shape."""
    from .research import research_security
    return research_security(symbol)


def _mock_get_historical(symbol: str, days: int = 30) -> ToolResult:
    from .research import _seed_float
    series = []
    base = time.time() - days * 86400
    for i in range(days):
        drift = _seed_float(f"{symbol}{i}", "hist")
        series.append({"date": time.strftime("%Y-%m-%d", time.gmtime(base + i * 86400)),
                       "close": round(100 + drift * 400, 2)})
    return ToolResult(
        ok=True, data={"symbol": symbol, "series": series, "source": "mock"},
        tools_used=["bloomberg.get_historical"],
    )


def _mock_get_news(query: str, limit: int = 10) -> ToolResult:
    from .research import research_market_news
    return research_market_news(query, limit=limit)
