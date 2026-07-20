"""
SQLAlchemy-backed storage layer with a dialect switcher.

Enables BOS to run on either SQLite (Phase 1, default) or PostgreSQL
(Phase 2, production) by changing a single env var:

    BOS_DB_URL=postgresql+psycopg2://user:pass@host:5432/bos

If BOS_DB_URL is not set, falls back to BOS_DB_PATH (SQLite file).
This preserves full backward compatibility with Phase 1 deployments.

The legacy modules (`audit.py`, `crm.py`, `long_term.py`) still use raw
SQL with parameterized queries — they call `raw_connection()` which
returns a wrapper that quacks like `sqlite3.Connection` on either backend.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from .config import Settings, get_settings

log = logging.getLogger("bos.db")


def _resolve_db_url(settings: Optional[Settings] = None) -> tuple[str, str]:
    """Return (sqlalchemy_url, dialect) for the configured backend.

    Priority:
      1. BOS_DB_URL env var                       → use as-is (Postgres, MySQL, etc)
      2. BOS_DB_PATH / settings.db_path           → SQLite file (Phase 1 compat)
    """
    settings = settings or get_settings()
    url = os.environ.get("BOS_DB_URL") or getattr(settings, "db_url", "")
    if url:
        dialect = url.split(":", 1)[0].split("+", 1)[0]
        return url, dialect
    db_path = settings.db_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}", "sqlite"


_engine: Optional[Engine] = None
_engine_lock = threading.Lock()


def get_engine() -> Engine:
    """Return a process-wide SQLAlchemy Engine."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                url, dialect = _resolve_db_url()
                kwargs = {"future": True}
                if dialect == "sqlite":
                    kwargs["connect_args"] = {"check_same_thread": False}
                else:
                    kwargs["pool_size"] = 10
                    kwargs["max_overflow"] = 20
                    kwargs["pool_pre_ping"] = True
                _engine = create_engine(url, **kwargs)
                log.info("DB engine ready: dialect=%s url=%s", dialect, _sanitize_url(url))
    return _engine


def _sanitize_url(url: str) -> str:
    if "@" in url and "://" in url:
        prefix, rest = url.split("://", 1)
        _, host = rest.split("@", 1)
        return f"{prefix}://***@{host}"
    return url


@contextmanager
def raw_connection():
    """Yield a connection-like object compatible with sqlite3.Connection API.

    The legacy modules call `conn.execute(sql, params)` and `conn.commit()`,
    and use `conn.row_factory = sqlite3.Row`. This wrapper preserves that
    interface on both SQLite and PostgreSQL (via SQLAlchemy DBAPI).

    Note: for Postgres, `%s` placeholders must be used instead of `?`.
    The wrapper auto-converts `?` → `%s` for cross-dialect compatibility.
    """
    engine = get_engine()
    conn = engine.raw_connection()
    try:
        yield _RowProxy(conn)
    finally:
        try:
            conn.close()
        except Exception:
            pass


class _RowProxy:
    """Normalize sqlite3 vs SQLAlchemy-DBAPI connection semantics."""

    def __init__(self, conn):
        # Unwrap SQLAlchemy's _ConnectionFairy to reach the real DBAPI conn
        self._conn = getattr(conn, "dbapi_connection", conn) or conn
        if hasattr(conn, "connection"):
            try:
                self._conn = conn.connection.connection
            except Exception:
                pass
        if isinstance(self._conn, sqlite3.Connection):
            self._conn.row_factory = sqlite3.Row

    @staticmethod
    def _convert_sql(sql: str) -> str:
        """Convert ? placeholders to %s for non-sqlite backends."""
        # sqlite3 uses ?; psycopg/sqlite-via-SQLAlchemy use %s (psycopg) or ? (sqlite).
        # SQLAlchemy raw_connection() returns the underlying DBAPI connection.
        # For sqlite3 it's a sqlite3.Connection (?, fine). For psycopg it needs %s.
        # We detect by checking if the connection is sqlite3.
        return sql  # conversion happens in execute() based on conn type

    def executescript(self, sql: str):
        cursor = self._conn.cursor()
        try:
            if hasattr(cursor, "executescript"):
                cursor.executescript(sql)
            else:
                # PostgreSQL: split on ';' for DDL script execution
                for stmt in sql.split(";"):
                    stmt = stmt.strip()
                    if stmt and not stmt.startswith("--"):
                        cursor.execute(stmt)
            self._conn.commit()
        finally:
            cursor.close()

    def execute(self, sql, params=()):
        cursor = self._conn.cursor()
        # Convert ? to %s for psycopg-style backends (NOT for sqlite3)
        if not isinstance(self._conn, sqlite3.Connection):
            sql = sql.replace("?", "%s")
        cursor.execute(sql, params)
        return cursor

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def is_postgres() -> bool:
    try:
        _, dialect = _resolve_db_url()
        return dialect in ("postgresql",)
    except Exception:
        return False


def reset_engine_for_tests() -> None:
    global _engine
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
            _engine = None
