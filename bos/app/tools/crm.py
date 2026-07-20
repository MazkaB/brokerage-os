"""
CRM tool - in-process SQLite-backed mock CRM (Phase 1).

Stands in for Salesforce / HubSpot / Dynamics (Phase 2 integrations).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from ..config import get_settings
from .base import ToolResult

log = logging.getLogger("bos.tools.crm")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS crm_clients (
    client_id TEXT PRIMARY KEY,
    full_name TEXT,
    email TEXT,
    phone TEXT,
    account_type TEXT,
    kyc_status TEXT,
    risk_tolerance TEXT,
    preferred_markets TEXT,   -- JSON
    status TEXT,
    created_at REAL,
    updated_at REAL,
    metadata TEXT
);
CREATE INDEX IF NOT EXISTS idx_crm_email ON crm_clients(email);

CREATE TABLE IF NOT EXISTS crm_conversations (
    id TEXT PRIMARY KEY,
    client_id TEXT,
    thread_id TEXT,
    direction TEXT,        -- inbound | outbound
    channel TEXT,
    summary TEXT,
    payload TEXT,          -- JSON
    created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_conv_client ON crm_conversations(client_id);
CREATE INDEX IF NOT EXISTS idx_conv_thread ON crm_conversations(thread_id);
"""


class CRMTool:
    """SQLite-backed mock CRM. Thread-safe singleton."""

    def __init__(self) -> None:
        self.db_path = get_settings().db_path
        self._lock = threading.Lock()
        self._init_schema()
        self._seed()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._conn() as c:
            c.executescript(_SCHEMA)
            c.commit()

    def _seed(self) -> None:
        # Seed a few demo clients if empty
        with self._lock, self._conn() as c:
            cur = c.execute("SELECT COUNT(*) AS n FROM crm_clients")
            if cur.fetchone()["n"] == 0:
                now = time.time()
                seeds = [
                    ("C-1001", "Jane Doe", "jane.doe@example.com", "+1-202-555-0143",
                     "Individual", "verified", "moderate", json.dumps(["US-EQ", "US-BOND"]),
                     "active"),
                    ("C-1002", "John Smith", "john.smith@example.com", "+1-202-555-0177",
                     "Retirement", "verified", "conservative", json.dumps(["US-BOND"]),
                     "active"),
                    ("C-1003", "Acme Corp", "treasury@acme.example", "+1-415-555-0188",
                     "Corporate", "pending", "aggressive", json.dumps(["INTL-EQ"]),
                     "active"),
                ]
                for s in seeds:
                    c.execute(
                        """INSERT INTO crm_clients
                           (client_id, full_name, email, phone, account_type,
                            kyc_status, risk_tolerance, preferred_markets,
                            status, created_at, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (*s, now, now),
                    )
                c.commit()
                log.info("CRM seeded with %d demo clients", len(seeds))

    # --- public ops ---
    def get_client(self, client_id: str) -> ToolResult:
        with self._lock, self._conn() as c:
            cur = c.execute("SELECT * FROM crm_clients WHERE client_id = ?", (client_id,))
            row = cur.fetchone()
        if not row:
            return ToolResult(ok=False, error=f"client {client_id} not found")
        d = dict(row)
        d["preferred_markets"] = json.loads(d["preferred_markets"]) if d["preferred_markets"] else []
        return ToolResult(ok=True, data={"client": d}, tools_used=["crm.get_client"])

    def create_client(self, **fields) -> ToolResult:
        client_id = fields.get("client_id") or f"C-{uuid.uuid4().hex[:6].upper()}"
        now = time.time()
        markets = json.dumps(fields.get("preferred_markets", []))
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO crm_clients
                   (client_id, full_name, email, phone, account_type, kyc_status,
                    risk_tolerance, preferred_markets, status, created_at, updated_at, metadata)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    client_id, fields.get("full_name"), fields.get("email"),
                    fields.get("phone"), fields.get("account_type", "Individual"),
                    fields.get("kyc_status", "pending"), fields.get("risk_tolerance", "moderate"),
                    markets, fields.get("status", "active"), now, now,
                    json.dumps(fields.get("metadata", {})),
                ),
            )
            c.commit()
        log.info("CRM created client %s", client_id)
        return ToolResult(ok=True, data={"client_id": client_id}, tools_used=["crm.create_client"])

    def update_client(self, client_id: str, **fields) -> ToolResult:
        if not fields:
            return ToolResult(ok=False, error="no fields to update")
        now = time.time()
        # serialize preferred_markets if provided
        if "preferred_markets" in fields and isinstance(fields["preferred_markets"], list):
            fields["preferred_markets"] = json.dumps(fields["preferred_markets"])
        sets = ", ".join(f"{k} = ?" for k in fields.keys()) + ", updated_at = ?"
        params = list(fields.values()) + [now, client_id]
        with self._lock, self._conn() as c:
            cur = c.execute(f"UPDATE crm_clients SET {sets} WHERE client_id = ?", params)
            c.commit()
            if cur.rowcount == 0:
                return ToolResult(ok=False, error=f"client {client_id} not found")
        return self.get_client(client_id)

    def list_clients(self, limit: int = 100) -> ToolResult:
        with self._lock, self._conn() as c:
            cur = c.execute("SELECT * FROM crm_clients ORDER BY updated_at DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
        clients = []
        for r in rows:
            d = dict(r)
            d["preferred_markets"] = json.loads(d["preferred_markets"]) if d["preferred_markets"] else []
            clients.append(d)
        return ToolResult(ok=True, data={"clients": clients}, tools_used=["crm.list_clients"])

    def record_conversation(
        self,
        *,
        client_id: Optional[str],
        thread_id: str,
        direction: str = "inbound",
        channel: str = "web",
        summary: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        cid = str(uuid.uuid4())
        now = time.time()
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO crm_conversations
                   (id, client_id, thread_id, direction, channel, summary, payload, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (cid, client_id, thread_id, direction, channel, summary,
                 json.dumps(payload or {}), now),
            )
            c.commit()
        return ToolResult(ok=True, data={"conversation_id": cid}, tools_used=["crm.record_conversation"])


# ---------------------------------------------------------------------------
# Singleton + module-level convenience functions (used by Worker agents)
# ---------------------------------------------------------------------------
_singleton: Optional[CRMTool] = None


def _inst() -> CRMTool:
    global _singleton
    if _singleton is None:
        _singleton = CRMTool()
    return _singleton


def crm_get_client(client_id: str) -> ToolResult:
    return _inst().get_client(client_id)


def crm_create_client(**fields) -> ToolResult:
    return _inst().create_client(**fields)


def crm_update_client(client_id: str, **fields) -> ToolResult:
    return _inst().update_client(client_id, **fields)


def crm_record_conversation(**kwargs) -> ToolResult:
    return _inst().record_conversation(**kwargs)


def crm_list_clients(limit: int = 100) -> ToolResult:
    return _inst().list_clients(limit=limit)
