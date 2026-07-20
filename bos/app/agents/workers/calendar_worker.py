"""Calendar Worker agent.

Responsibilities (FR4):
  * schedule meetings
  * reminders
  * follow-ups
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from ...audit import get_audit
from ...state import BrokerState
from ...tools.calendar import cal_schedule, cal_list_events, cal_reminder
from ..base import _trace, summarize_for_audit

log = logging.getLogger("bos.workers.calendar")


def calendar_worker_node(state: BrokerState) -> Dict[str, Any]:
    _trace(state, "calendar_worker")
    thread_id = state.get("thread_id", "unknown")
    user_msg = state.get("user_message", "")
    user_profile = state.get("user_profile") or {}

    op = state.get("cal_op", "list")  # list | schedule | reminder
    summary: str = ""
    data: Dict[str, Any] = {}
    tools_used = ["calendar.list_events"]
    errors: str = ""

    try:
        if op == "schedule":
            r = cal_schedule(
                title=state.get("cal_title", "Meeting"),
                when=state.get("cal_when"),
                duration_minutes=int(state.get("cal_duration", 30)),
                attendees=state.get("cal_attendees") or [],
                notes=state.get("cal_notes", ""),
                client_id=user_profile.get("client_id"),
            )
            if not r.ok:
                raise ValueError(r.error)
            data["event"] = r.data["event"]
            summary = (
                f"Scheduled '{data['event']['title']}' at {data['event']['when']} "
                f"({data['event']['duration_minutes']} min)"
            )
            tools_used = ["calendar.schedule"]
            # Auto-set a reminder 1 day before the meeting
            try:
                cal_reminder(event_id=data["event"]["event_id"],
                             message=f"Upcoming: {data['event']['title']}",
                             deliver_in_minutes=60 * 24)
                tools_used.append("calendar.reminder")
            except Exception:
                pass
        elif op == "reminder":
            r = cal_reminder(
                event_id=state.get("cal_event_id"),
                message=state.get("cal_message", "Reminder"),
                deliver_in_minutes=int(state.get("cal_delay_min", 60)),
            )
            data["reminder"] = r.data["reminder"]
            summary = "Created reminder"
            tools_used = ["calendar.reminder"]
        else:
            r = cal_list_events(client_id=user_profile.get("client_id"))
            data["events"] = r.data["events"]
            summary = f"Found {len(data['events'])} upcoming event(s)"
    except Exception as e:
        log.warning("Calendar worker error: %s", e)
        errors = str(e)
        summary = f"Calendar op '{op}' failed: {e}"

    get_audit().record_event(
        thread_id=thread_id,
        agent="calendar_worker",
        event_type="worker_run",
        reasoning=summarize_for_audit(user_msg),
        tools=tools_used,
        input_summary=op,
        output_summary=summarize_for_audit(summary),
        metadata={"data": data, "error": errors},
    )

    result: Dict[str, Any] = {
        "worker": "calendar_worker",
        "status": "failed" if errors else "success",
        "summary": summary,
        "data": data,
        "tools_used": tools_used,
        "error": errors or None,
        "confidence": 0.95 if not errors else 0.3,
    }
    worker_outputs = dict(state.get("worker_outputs") or {})
    worker_outputs["calendar_worker"] = result
    return {"worker_outputs": worker_outputs}
