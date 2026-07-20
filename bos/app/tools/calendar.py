"""
Calendar tool - in-memory scheduling store (Phase 1).

Stands in for Google Calendar / Outlook (Phase 2 integrations).
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from .base import ToolResult

log = logging.getLogger("bos.tools.calendar")


class CalendarTool:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: List[Dict[str, Any]] = []

    def schedule(
        self,
        *,
        title: str,
        when: Optional[str] = None,
        duration_minutes: int = 30,
        attendees: Optional[List[str]] = None,
        notes: str = "",
        client_id: Optional[str] = None,
    ) -> ToolResult:
        eid = f"EVT-{uuid.uuid4().hex[:8].upper()}"
        # If `when` is missing, schedule next business day at 10:00
        if not when:
            import datetime as dt
            tomorrow = dt.date.today() + dt.timedelta(days=1)
            when = tomorrow.strftime("%Y-%m-%d 10:00")
        ev = {
            "event_id": eid,
            "title": title,
            "when": when,
            "duration_minutes": duration_minutes,
            "attendees": attendees or [],
            "notes": notes,
            "client_id": client_id,
            "created_at": time.time(),
        }
        with self._lock:
            self._events.append(ev)
        log.info("scheduled event %s: %s @ %s", eid, title, when)
        return ToolResult(ok=True, data={"event": ev}, tools_used=["calendar.schedule"])

    def list_events(self, client_id: Optional[str] = None, limit: int = 50) -> ToolResult:
        with self._lock:
            evs = list(self._events)
        if client_id:
            evs = [e for e in evs if e.get("client_id") == client_id]
        evs = sorted(evs, key=lambda e: e.get("when", ""), reverse=True)
        return ToolResult(
            ok=True,
            data={"events": evs[:limit]},
            tools_used=["calendar.list_events"],
        )

    def reminder(
        self,
        *,
        event_id: Optional[str] = None,
        message: str,
        deliver_in_minutes: int = 60,
    ) -> ToolResult:
        rid = f"REM-{uuid.uuid4().hex[:6].upper()}"
        reminder = {
            "reminder_id": rid,
            "event_id": event_id,
            "message": message,
            "deliver_at_epoch": time.time() + deliver_in_minutes * 60,
            "created_at": time.time(),
        }
        # In Phase 1 we just record the reminder. Phase 2 will push via Slack/Email.
        return ToolResult(
            ok=True,
            data={"reminder": reminder},
            tools_used=["calendar.reminder"],
        )


_singleton: Optional[CalendarTool] = None


def _inst() -> CalendarTool:
    global _singleton
    if _singleton is None:
        _singleton = CalendarTool()
    return _singleton


def cal_schedule(**kwargs) -> ToolResult:
    return _inst().schedule(**kwargs)


def cal_list_events(client_id: Optional[str] = None, limit: int = 50) -> ToolResult:
    return _inst().list_events(client_id=client_id, limit=limit)


def cal_reminder(**kwargs) -> ToolResult:
    return _inst().reminder(**kwargs)
