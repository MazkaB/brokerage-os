"""
LLM token + cost metrics tracking.

Captures usage metadata from every Vertex AI LLM call so we can report on:
  * Token consumption (prompt, completion, total)
  * Estimated cost ($)
  * Per-call latency
  * Per-node attribution

Persists to SQLite for the admin dashboard charts.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from .config import Settings, get_settings

log = logging.getLogger("bos.metrics")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_usage (
    id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    node TEXT,
    thread_id TEXT,
    model TEXT,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    success INTEGER DEFAULT 1,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON llm_usage(ts);
CREATE INDEX IF NOT EXISTS idx_usage_node ON llm_usage(node);
"""


# Rough per-1K-token pricing for cost estimation. Update as Vertex pricing changes.
# Source: Google Cloud Vertex AI pricing page (general availability).
_PRICING_PER_1K = {
    "gemini-2.5-flash": {"input": 0.000075, "output": 0.00030},
    "gemini-2.0-flash": {"input": 0.000075, "output": 0.00030},
    "gemini-2.5-pro":   {"input": 0.00125,  "output": 0.00500},
    "gemini-1.5-flash": {"input": 0.000075, "output": 0.00030},
    "gemini-1.5-pro":   {"input": 0.00125,  "output": 0.00500},
    "text-embedding-004": {"input": 0.0000125, "output": 0.0},
}
_DEFAULT_PRICING = {"input": 0.0001, "output": 0.0005}


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p = _PRICING_PER_1K.get(model, _DEFAULT_PRICING)
    return (prompt_tokens / 1000.0) * p["input"] + (completion_tokens / 1000.0) * p["output"]


class MetricsRecorder:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.db_path = self.settings.db_path
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn() as c:
            c.executescript(_SCHEMA)
            c.commit()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def record(
        self,
        *,
        node: str,
        thread_id: Optional[str] = None,
        model: str = "",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: int = 0,
        success: bool = True,
        error: Optional[str] = None,
    ) -> str:
        total = prompt_tokens + completion_tokens
        cost = estimate_cost_usd(model, prompt_tokens, completion_tokens)
        rid = str(uuid.uuid4())
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO llm_usage
                   (id, ts, node, thread_id, model, prompt_tokens, completion_tokens,
                    total_tokens, latency_ms, cost_usd, success, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rid, time.time(), node, thread_id, model,
                 prompt_tokens, completion_tokens, total,
                 latency_ms, cost, 1 if success else 0, error),
            )
            c.commit()
        return rid

    def summary(self, since_seconds: int = 86400) -> Dict[str, Any]:
        """Aggregate metrics for the last N seconds (default 24h)."""
        cutoff = time.time() - since_seconds
        with self._lock, self._conn() as c:
            cur = c.execute(
                """SELECT
                    COUNT(*) AS calls,
                    SUM(prompt_tokens) AS p_tok,
                    SUM(completion_tokens) AS c_tok,
                    SUM(total_tokens) AS t_tok,
                    SUM(cost_usd) AS cost,
                    AVG(latency_ms) AS avg_lat,
                    SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS errors
                   FROM llm_usage WHERE ts >= ?""",
                (cutoff,),
            )
            row = cur.fetchone()
        return {
            "window_seconds": since_seconds,
            "calls": row["calls"] or 0,
            "prompt_tokens": row["p_tok"] or 0,
            "completion_tokens": row["c_tok"] or 0,
            "total_tokens": row["t_tok"] or 0,
            "cost_usd": round(row["cost"] or 0.0, 6),
            "avg_latency_ms": int(row["avg_lat"] or 0),
            "errors": row["errors"] or 0,
        }

    def timeseries(self, since_seconds: int = 3600, bucket_seconds: int = 60) -> list:
        """Bucketed metrics for charting. Returns list of {ts, calls, tokens, cost}."""
        cutoff = time.time() - since_seconds
        with self._lock, self._conn() as c:
            cur = c.execute(
                f"""SELECT
                    (CAST(ts AS INTEGER) / ?) * ? AS bucket,
                    COUNT(*) AS calls,
                    SUM(total_tokens) AS tokens,
                    SUM(cost_usd) AS cost
                   FROM llm_usage WHERE ts >= ?
                   GROUP BY bucket ORDER BY bucket""",
                (bucket_seconds, bucket_seconds, cutoff),
            )
            return [dict(r) for r in cur.fetchall()]


_singleton: Optional[MetricsRecorder] = None


def get_metrics() -> MetricsRecorder:
    global _singleton
    if _singleton is None:
        _singleton = MetricsRecorder()
    return _singleton
