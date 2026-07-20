"""
Audit trail service.

Implements FR7 of the PRD: every action records
  timestamp, agent, reasoning summary, tools, documents, human approval.

Phase 1 uses SQLite. The schema is forward-compatible with PostgreSQL.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Iterator

from .config import Settings, get_settings

log = logging.getLogger("bos.audit")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    agent TEXT NOT NULL,
    event_type TEXT NOT NULL,
    reasoning TEXT,
    tools TEXT,            -- JSON list
    documents TEXT,        -- JSON list
    input_summary TEXT,
    output_summary TEXT,
    human_approval TEXT,   -- JSON {approved, by, at, note} or NULL
    metadata TEXT          -- JSON
);
CREATE INDEX IF NOT EXISTS idx_audit_thread ON audit_events(thread_id);
CREATE INDEX IF NOT EXISTS idx_audit_agent ON audit_events(agent);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(timestamp);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    intent TEXT,
    summary TEXT,
    requested_by TEXT,
    requested_at REAL NOT NULL,
    decided_by TEXT,
    decided_at REAL,
    decision TEXT,         -- 'approved' | 'rejected' | NULL
    note TEXT,
    timeout_seconds INTEGER,
    status TEXT NOT NULL   -- 'pending' | 'approved' | 'rejected' | 'expired'
);
CREATE INDEX IF NOT EXISTS idx_approvals_thread ON approvals(thread_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);

CREATE TABLE IF NOT EXISTS workflows (
    thread_id TEXT PRIMARY KEY,
    user_id TEXT,
    role TEXT,
    intent TEXT,
    manager TEXT,
    workers TEXT,           -- JSON list
    approval_required INTEGER,
    status TEXT,
    created_at REAL,
    updated_at REAL,
    final_response TEXT
);
CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status);
"""


class AuditTrail:
    """Thread-safe SQLite audit log."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.db_path = Path(self.settings.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.executescript(_SCHEMA)
            c.commit()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        # check_same_thread=False because we use our own lock; this lets us
        # share one connection path across worker threads (LangGraph).
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Audit events
    # ------------------------------------------------------------------
    def record_event(
        self,
        *,
        thread_id: str,
        agent: str,
        event_type: str,
        reasoning: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        documents: Optional[List[Any]] = None,
        input_summary: Optional[str] = None,
        output_summary: Optional[str] = None,
        human_approval: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        event_id = str(uuid.uuid4())
        ts = time.time()
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO audit_events
                   (id, thread_id, timestamp, agent, event_type, reasoning,
                    tools, documents, input_summary, output_summary,
                    human_approval, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id, thread_id, ts, agent, event_type, reasoning,
                    json.dumps(tools or [], default=str),
                    json.dumps(documents or [], default=str),
                    input_summary, output_summary,
                    json.dumps(human_approval, default=str) if human_approval else None,
                    json.dumps(metadata or {}, default=str),
                ),
            )
            c.commit()
        log.debug("audit event: agent=%s type=%s thread=%s", agent, event_type, thread_id)
        return event_id

    def list_events(
        self,
        thread_id: Optional[str] = None,
        agent: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        q = "SELECT * FROM audit_events"
        clauses, params = [], []
        if thread_id:
            clauses.append("thread_id = ?"); params.append(thread_id)
        if agent:
            clauses.append("agent = ?"); params.append(agent)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with self._lock, self._conn() as c:
            cur = c.execute(q, params)
            rows = cur.fetchall()
        return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(r: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": r["id"],
            "thread_id": r["thread_id"],
            "timestamp": r["timestamp"],
            "agent": r["agent"],
            "event_type": r["event_type"],
            "reasoning": r["reasoning"],
            "tools": json.loads(r["tools"]) if r["tools"] else [],
            "documents": json.loads(r["documents"]) if r["documents"] else [],
            "input_summary": r["input_summary"],
            "output_summary": r["output_summary"],
            "human_approval": json.loads(r["human_approval"]) if r["human_approval"] else None,
            "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
        }

    # ------------------------------------------------------------------
    # Approvals (HITL)
    # ------------------------------------------------------------------
    def create_approval(
        self,
        *,
        thread_id: str,
        workflow_id: str,
        intent: str,
        summary: str,
        requested_by: str,
        timeout_seconds: int = 1800,
    ) -> str:
        apid = str(uuid.uuid4())
        now = time.time()
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO approvals
                   (id, thread_id, workflow_id, intent, summary,
                    requested_by, requested_at, timeout_seconds, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
                (apid, thread_id, workflow_id, intent, summary,
                 requested_by, now, timeout_seconds),
            )
            c.commit()
        return apid

    def decide_approval(
        self,
        approval_id: str,
        decision: str,
        decided_by: str,
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be 'approved' or 'rejected'")
        now = time.time()
        with self._lock, self._conn() as c:
            cur = c.execute("SELECT status FROM approvals WHERE id = ?", (approval_id,))
            row = cur.fetchone()
            if row is None:
                return None
            if row["status"] != "pending":
                return self.get_approval(approval_id)
            c.execute(
                """UPDATE approvals
                   SET decision = ?, decided_by = ?, decided_at = ?, note = ?, status = ?
                   WHERE id = ?""",
                (decision, decided_by, now, note, decision, approval_id),
            )
            c.commit()
        return self.get_approval(approval_id)

    def expire_stale_approvals(self) -> int:
        now = time.time()
        with self._lock, self._conn() as c:
            cur = c.execute(
                """UPDATE approvals SET status = 'expired'
                   WHERE status = 'pending'
                     AND (? - requested_at) > timeout_seconds""",
                (now,),
            )
            c.commit()
            return cur.rowcount

    def get_approval(self, approval_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._conn() as c:
            cur = c.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
            row = cur.fetchone()
        if not row:
            return None
        return dict(row)

    def list_approvals(self, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        q = "SELECT * FROM approvals"
        params: List[Any] = []
        if status:
            q += " WHERE status = ?"; params.append(status)
        q += " ORDER BY requested_at DESC LIMIT ?"
        params.append(limit)
        with self._lock, self._conn() as c:
            cur = c.execute(q, params)
            return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Workflow tracking
    # ------------------------------------------------------------------
    def upsert_workflow(
        self,
        *,
        thread_id: str,
        user_id: Optional[str] = None,
        role: Optional[str] = None,
        intent: Optional[str] = None,
        manager: Optional[str] = None,
        workers: Optional[List[str]] = None,
        approval_required: Optional[bool] = None,
        status: Optional[str] = None,
        final_response: Optional[str] = None,
    ) -> None:
        now = time.time()
        with self._lock, self._conn() as c:
            cur = c.execute("SELECT thread_id FROM workflows WHERE thread_id = ?", (thread_id,))
            exists = cur.fetchone() is not None
            if exists:
                # Patch non-null fields
                fields = []
                params: List[Any] = []
                for col, val in [
                    ("user_id", user_id), ("role", role), ("intent", intent),
                    ("manager", manager), ("workers", json.dumps(workers) if workers is not None else None),
                    ("approval_required", 1 if approval_required else 0 if approval_required is False else None),
                    ("status", status), ("updated_at", now),
                    ("final_response", final_response),
                ]:
                    if val is not None:
                        fields.append(f"{col} = ?"); params.append(val)
                if not fields:
                    return
                params.append(thread_id)
                c.execute(f"UPDATE workflows SET {', '.join(fields)} WHERE thread_id = ?", params)
            else:
                c.execute(
                    """INSERT INTO workflows
                       (thread_id, user_id, role, intent, manager, workers,
                        approval_required, status, created_at, updated_at,
                        final_response)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (thread_id, user_id, role, intent, manager,
                     json.dumps(workers or []), 1 if approval_required else 0,
                     status or "running", now, now, final_response),
                )
            c.commit()

    def list_workflows(self, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        q = "SELECT * FROM workflows"
        params: List[Any] = []
        if status:
            q += " WHERE status = ?"; params.append(status)
        q += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self._lock, self._conn() as c:
            cur = c.execute(q, params)
            rows = cur.fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["workers"] = json.loads(d["workers"]) if d["workers"] else []
            d["approval_required"] = bool(d["approval_required"])
            out.append(d)
        return out

    def get_workflow(self, thread_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._conn() as c:
            cur = c.execute("SELECT * FROM workflows WHERE thread_id = ?", (thread_id,))
            r = cur.fetchone()
        if not r:
            return None
        d = dict(r)
        d["workers"] = json.loads(d["workers"]) if d["workers"] else []
        d["approval_required"] = bool(d["approval_required"])
        return d


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_singleton: Optional[AuditTrail] = None


def get_audit() -> AuditTrail:
    global _singleton
    if _singleton is None:
        _singleton = AuditTrail()
    return _singleton
