"""
Long-term memory: persistent user profiles & preferences (SQLite).

Schema columns mirror the PRD's suggested user_profile:
   user_id, risk_tolerance, preferred_markets, kyc_status, ...
plus additional preference & interaction-tracking fields.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from ..config import Settings, get_settings

log = logging.getLogger("bos.memory.long_term")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    username TEXT,
    role TEXT,
    display_name TEXT,
    risk_tolerance TEXT,
    preferred_markets TEXT,        -- JSON list
    kyc_status TEXT,
    account_type TEXT,
    notes TEXT,
    metadata TEXT,                 -- JSON
    created_at REAL,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS user_facts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    fact_value TEXT,
    confidence REAL,
    source TEXT,
    created_at REAL,
    UNIQUE(user_id, fact_type, fact_value)
);
CREATE INDEX IF NOT EXISTS idx_facts_user ON user_facts(user_id);
"""


class LongTermMemory:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.db_path = self.settings.db_path
        self._lock = threading.Lock()
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._conn() as c:
            c.executescript(_SCHEMA)
            c.commit()

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------
    def upsert_profile(self, profile: Dict[str, Any]) -> None:
        uid = profile["user_id"]
        now = time.time()
        cols = [
            "user_id", "username", "role", "display_name",
            "risk_tolerance", "preferred_markets", "kyc_status",
            "account_type", "notes", "metadata", "updated_at",
        ]
        values = [
            uid,
            profile.get("username"),
            profile.get("role"),
            profile.get("display_name"),
            profile.get("risk_tolerance"),
            json.dumps(profile.get("preferred_markets", [])),
            profile.get("kyc_status"),
            profile.get("account_type"),
            profile.get("notes"),
            json.dumps(profile.get("metadata", {})),
            now,
        ]
        with self._lock, self._conn() as c:
            cur = c.execute("SELECT user_id FROM user_profiles WHERE user_id = ?", (uid,))
            exists = cur.fetchone() is not None
            if exists:
                sets = ", ".join(f"{c2} = ?" for c2 in cols[1:])
                c.execute(
                    f"UPDATE user_profiles SET {sets} WHERE user_id = ?",
                    values[1:] + [uid],
                )
            else:
                placeholders = ", ".join(["?"] * (len(cols) + 1))
                full_cols = cols[:1] + ["created_at"] + cols[1:]
                c.execute(
                    f"INSERT INTO user_profiles ({', '.join(full_cols)}) VALUES ({placeholders})",
                    [uid, now] + values[1:],
                )
            c.commit()

    def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._conn() as c:
            cur = c.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["preferred_markets"] = json.loads(d["preferred_markets"]) if d["preferred_markets"] else []
        d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
        return d

    def list_profiles(self) -> List[Dict[str, Any]]:
        with self._lock, self._conn() as c:
            cur = c.execute("SELECT * FROM user_profiles ORDER BY updated_at DESC")
            rows = cur.fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["preferred_markets"] = json.loads(d["preferred_markets"]) if d["preferred_markets"] else []
            d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
            out.append(d)
        return out

    # ------------------------------------------------------------------
    # Free-form facts
    # ------------------------------------------------------------------
    def add_fact(
        self,
        user_id: str,
        fact_type: str,
        fact_value: str,
        confidence: float = 1.0,
        source: str = "agent",
    ) -> None:
        import uuid
        fid = str(uuid.uuid4())
        now = time.time()
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT OR IGNORE INTO user_facts
                   (id, user_id, fact_type, fact_value, confidence, source, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (fid, user_id, fact_type, fact_value, confidence, source, now),
            )
            c.commit()

    def list_facts(self, user_id: str, fact_type: Optional[str] = None) -> List[Dict[str, Any]]:
        q = "SELECT * FROM user_facts WHERE user_id = ?"
        params: List[Any] = [user_id]
        if fact_type:
            q += " AND fact_type = ?"; params.append(fact_type)
        q += " ORDER BY created_at DESC"
        with self._lock, self._conn() as c:
            cur = c.execute(q, params)
            return [dict(r) for r in cur.fetchall()]


_singleton: Optional[LongTermMemory] = None


def get_long_term_memory() -> LongTermMemory:
    global _singleton
    if _singleton is None:
        _singleton = LongTermMemory()
    return _singleton
