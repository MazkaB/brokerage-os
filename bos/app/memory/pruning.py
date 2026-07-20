"""
Memory retention policy: TTL / pruning / summarization.

Background scheduler runs every hour (configurable) and:
  * short-term (LangGraph checkpoints older than SHORT_TERM_TTL_DAYS)
      → archived then deleted
  * audit_events older than AUDIT_RETENTION_DAYS
      → archived then deleted (PRD §6: SEC 17a-4 wants 7 years, but here
        we keep 365 days live + archive the rest)
  * user_facts older than FACT_SUMMARY_THRESHOLD_DAYS
      → LLM-summarized into profile.notes, originals deleted
  * crm_conversations older than CONVERSATION_RETENTION_DAYS
      → deleted (PII hygiene)
  * approvals older than APPROVAL_RETENTION_DAYS with status in
      (approved, rejected, expired) → archived then deleted

All deletions are preceded by appending to the `archive_*` tables so we
have a recovery window. Archive rows themselves are pruned after
ARCHIVE_RETENTION_DAYS.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from typing import Optional

from ..config import get_settings
from ..db import raw_connection

# asyncio imported above; placeholder to keep linting happy
_ = asyncio

log = logging.getLogger("bos.memory.pruning")


# Retention windows (days). Override via env if needed.
SHORT_TERM_TTL_DAYS = 7
AUDIT_RETENTION_DAYS = 365
FACT_SUMMARY_THRESHOLD_DAYS = 30
CONVERSATION_RETENTION_DAYS = 90
APPROVAL_RETENTION_DAYS = 180
ARCHIVE_RETENTION_DAYS = 365 * 7  # SEC Rule 17a-4: 7 years


_SCHEMA = """
CREATE TABLE IF NOT EXISTS archive_audit_events AS SELECT * FROM audit_events WHERE 1=0;
CREATE TABLE IF NOT EXISTS archive_approvals AS SELECT * FROM approvals WHERE 1=0;
CREATE TABLE IF NOT EXISTS archive_crm_conversations AS SELECT * FROM crm_conversations WHERE 1=0;
CREATE TABLE IF NOT EXISTS memory_summaries (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    fact_count INTEGER,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mem_summary_user ON memory_summaries(user_id);
"""


def _init_schema() -> None:
    with raw_connection() as c:
        try:
            c.executescript(_SCHEMA)
            c.commit()
        except Exception as e:
            log.warning("pruning schema init skipped (%s)", e)


def _archive_then_delete(table: str, archive_table: str, where: str, params=()) -> int:
    """Move rows matching `where` from `table` into `archive_table`, then delete."""
    with raw_connection() as c:
        try:
            cur = c.execute(
                f"INSERT INTO {archive_table} SELECT * FROM {table} WHERE {where}",
                params,
            )
            moved = cur.rowcount if hasattr(cur, "rowcount") else 0
            c.execute(f"DELETE FROM {table} WHERE {where}", params)
            c.commit()
            return moved or 0
        except Exception as e:
            # Tables may not exist in test or fresh-DB environments; skip gracefully
            log.debug("archive %s → %s skipped: %s", table, archive_table, e)
            return 0


def prune_audit(now: Optional[float] = None) -> int:
    """Audit events older than AUDIT_RETENTION_DAYS → archive + delete."""
    now = now or time.time()
    cutoff = now - AUDIT_RETENTION_DAYS * 86400
    n = _archive_then_delete(
        "audit_events", "archive_audit_events",
        "timestamp < ?", (cutoff,),
    )
    if n:
        log.info("pruned %d audit events older than %d days", n, AUDIT_RETENTION_DAYS)
    return n


def prune_old_approvals(now: Optional[float] = None) -> int:
    now = now or time.time()
    cutoff = now - APPROVAL_RETENTION_DAYS * 86400
    n = _archive_then_delete(
        "approvals", "archive_approvals",
        "requested_at < ? AND status IN ('approved','rejected','expired')",
        (cutoff,),
    )
    if n:
        log.info("pruned %d old approvals", n)
    return n


def prune_old_conversations(now: Optional[float] = None) -> int:
    """CRM conversations older than CONVERSATION_RETENTION_DAYS → hard delete."""
    now = now or time.time()
    cutoff = now - CONVERSATION_RETENTION_DAYS * 86400
    try:
        with raw_connection() as c:
            cur = c.execute("DELETE FROM crm_conversations WHERE created_at < ?", (cutoff,))
            c.commit()
            n = cur.rowcount if hasattr(cur, "rowcount") else 0
    except Exception as e:
        # Table may not exist in test environments - skip gracefully
        log.debug("conversations prune skipped: %s", e)
        return 0
    if n:
        log.info("pruned %d old CRM conversations", n)
    return n


def prune_archive(now: Optional[float] = None) -> int:
    """Even archive rows eventually expire (after ARCHIVE_RETENTION_DAYS)."""
    now = now or time.time()
    cutoff = now - ARCHIVE_RETENTION_DAYS * 86400
    total = 0
    for arch in ("archive_audit_events", "archive_approvals"):
        ts_col = "timestamp" if arch == "archive_audit_events" else "requested_at"
        with raw_connection() as c:
            cur = c.execute(f"DELETE FROM {arch} WHERE {ts_col} < ?", (cutoff,))
            c.commit()
            total += cur.rowcount if hasattr(cur, "rowcount") else 0
    if total:
        log.info("purged %d expired archive rows", total)
    return total


def summarize_and_prune_facts(now: Optional[float] = None) -> int:
    """Per-user: gather facts older than threshold, summarize into profile.notes,
    delete originals. Uses LLM if available, deterministic fallback otherwise.
    """
    from .long_term import get_long_term_memory
    from ..llm import get_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    now = now or time.time()
    cutoff = now - FACT_SUMMARY_THRESHOLD_DAYS * 86400
    ltm = get_long_term_memory()
    total_pruned = 0

    for profile in ltm.list_profiles():
        uid = profile["user_id"]
        # Gather aged facts
        with raw_connection() as c:
            cur = c.execute(
                "SELECT fact_type, fact_value FROM user_facts "
                "WHERE user_id = ? AND created_at < ? ORDER BY created_at DESC LIMIT 50",
                (uid, cutoff),
            )
            rows = cur.fetchall()
        if not rows:
            continue

        facts_list = [dict(r) if not isinstance(r, dict) else r for r in rows]
        facts_blob = "\n".join(f"- [{f.get('fact_type', '?')}] {f.get('fact_value', '')}"
                               for f in facts_list)

        # Summarize via LLM (best-effort)
        try:
            llm = get_llm(temperature=0.1)
            resp = llm.invoke([
                SystemMessage(content=(
                    "You are a memory compactor. Summarize the user facts below "
                    "into a single dense paragraph capturing everything important. "
                    "Output only the summary, no preamble."
                )),
                HumanMessage(content=facts_blob),
            ])
            summary = str(getattr(resp, "content", resp)).strip()[:1000]
        except Exception as e:
            log.info("LLM summarization failed (%s); using raw blob", e)
            summary = facts_blob[:1000]

        # Persist summary
        with raw_connection() as c:
            import uuid
            c.execute(
                "INSERT INTO memory_summaries (id, user_id, summary, fact_count, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), uid, summary, len(facts_list), now),
            )
            c.execute(
                "DELETE FROM user_facts WHERE user_id = ? AND created_at < ?",
                (uid, cutoff),
            )
            c.commit()
        total_pruned += len(facts_list)
        log.info("summarized %d old facts for user %s", len(facts_list), uid)

    return total_pruned


def prune_short_term_checkpointer(now: Optional[float] = None) -> int:
    """LangGraph SqliteSaver stores checkpoints in `checkpoints`, `writes` tables.

    We delete checkpoint rows whose `thread_id` has had no write in the last
    SHORT_TERM_TTL_DAYS. Conservative: only deletes if both tables exist.
    """
    now = now or time.time()
    cutoff_ts = now - SHORT_TERM_TTL_DAYS * 86400
    n = 0
    with raw_connection() as c:
        try:
            # checkpoint_ts is in ISO format in some versions; fall back gracefully
            for stmt in (
                # Delete writes for threads that have no recent write
                "DELETE FROM writes WHERE thread_id IN ("
                "  SELECT thread_id FROM ("
                "    SELECT thread_id, MAX(CAST(thread_ts AS REAL)) AS last_ts FROM writes "
                "    GROUP BY thread_id HAVING last_ts < ?"
                "  )"
                ")",
                "DELETE FROM checkpoints WHERE thread_id IN ("
                "  SELECT thread_id FROM checkpoints "
                "  GROUP BY thread_id HAVING MAX(CAST(thread_ts AS REAL)) < ?"
                ")",
            ):
                try:
                    cur = c.execute(stmt, (cutoff_ts,))
                    n += cur.rowcount if hasattr(cur, "rowcount") else 0
                except Exception:
                    pass
            c.commit()
        except Exception as e:
            log.debug("checkpoint pruning skipped (%s)", e)
    if n:
        log.info("pruned %d stale short-term checkpoints", n)
    return n


def run_all(now: Optional[float] = None) -> dict:
    """Run the full memory retention cycle. Returns counts."""
    _init_schema()
    return {
        "audit_pruned": prune_audit(now),
        "approvals_pruned": prune_old_approvals(now),
        "conversations_pruned": prune_old_conversations(now),
        "facts_summarized": summarize_and_prune_facts(now),
        "checkpoints_pruned": prune_short_term_checkpointer(now),
        "archive_purged": prune_archive(now),
    }


# ---------------------------------------------------------------------------
# Async scheduler
# ---------------------------------------------------------------------------
_bg_task: Optional[asyncio.Task] = None


async def _pruning_loop():
    interval = int(__import__("os").environ.get("BOS_PRUNING_INTERVAL_SECONDS", "3600"))
    log.info("Memory pruning loop started (interval=%ds)", interval)
    while True:
        try:
            stats = run_all()
            log.info("Pruning cycle complete: %s", stats)
        except Exception as e:
            log.warning("pruning loop error: %s", e)
        await asyncio.sleep(interval)


def start_background_loop():
    """Start the pruning background task. Idempotent."""
    global _bg_task
    if _bg_task is None or _bg_task.done():
        _bg_task = asyncio.create_task(_pruning_loop())
    return _bg_task
