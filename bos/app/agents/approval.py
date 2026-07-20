"""
Human-in-the-loop approval node.

Implements FR6: configurable approval gates. Uses LangGraph's `interrupt`
primitive to pause the graph until a human approves/rejects via the
/api/approval/{id}/decision endpoint.

Flow:
   workers_done -> approval_router
       |-- (no approval needed) -> compose_response
       |-- (approval needed)    -> request_approval -> [INTERRUPT]
                                    resume(decision) -> compose_response
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict

from langgraph.types import interrupt

from ..audit import get_audit
from ..config import APPROVAL_INTENTS, get_settings
from ..state import BrokerState
from .base import _trace, summarize_for_audit

log = logging.getLogger("bos.approval")


def approval_router(state: BrokerState) -> str:
    """Conditional edge: do we need human approval before responding?"""
    return "needs_approval" if state.get("approval_required") else "compose"


def request_approval_node(state: BrokerState) -> Dict[str, Any]:
    """Pause the graph and wait for a human decision."""
    _trace(state, "request_approval")
    thread_id = state.get("thread_id", "unknown")
    settings = get_settings()

    intent = state.get("intent", "high_risk_operation")
    worker_outputs = state.get("worker_outputs") or {}

    # Build a human-readable summary of what the workflow wants to do
    summary_parts = []
    for name, res in worker_outputs.items():
        if res.get("status") == "success":
            summary_parts.append(f"- {name}: {res.get('summary','')}")
    action_summary = "\n".join(summary_parts) or f"Workflow intent: {intent}"

    # Persist an approval record so admins can decide via the dashboard
    audit = get_audit()
    approval_id = audit.create_approval(
        thread_id=thread_id,
        workflow_id=thread_id,  # in v1, one workflow per thread
        intent=intent,
        summary=action_summary,
        requested_by=state.get("user_id", "unknown"),
        timeout_seconds=settings.approval_timeout_seconds,
    )
    audit.upsert_workflow(
        thread_id=thread_id,
        approval_required=True,
        status="awaiting_approval",
    )
    audit.record_event(
        thread_id=thread_id,
        agent="approval_node",
        event_type="interrupt",
        reasoning=f"intent={intent} requires human approval",
        input_summary=summarize_for_audit(state.get("user_message", "")),
        output_summary=f"approval_id={approval_id}",
        metadata={"approval_id": approval_id, "intent": intent},
    )

    # The value passed to interrupt() becomes the "interrupt value" the caller
    # sees. The human-supplied decision will be the return value when resumed.
    payload = {
        "approval_id": approval_id,
        "intent": intent,
        "summary": action_summary,
        "timeout_seconds": settings.approval_timeout_seconds,
        "message": (
            f"This action requires compliance/advisor approval before proceeding. "
            f"Approval request `{approval_id}` created. Awaiting decision."
        ),
    }
    decision = interrupt(payload)

    # After resume, `decision` is whatever was passed to Command(resume=...)
    log.info("Approval %s decision: %s", approval_id, decision)
    return {
        "approval": {
            "approval_id": approval_id,
            "decision": decision.get("decision") if isinstance(decision, dict) else decision,
            "decided_by": decision.get("decided_by") if isinstance(decision, dict) else "human",
            "note": decision.get("note") if isinstance(decision, dict) else None,
            "decided_at": time.time(),
        },
        "trace": _trace(state, "request_approval"),
    }
