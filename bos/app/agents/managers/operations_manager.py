"""
Operations Manager agent.

Owns: CRM Worker, Document Worker, Calendar Worker.
Intents typically routed here: account_opening, account_transfer,
client_lookup, scheduling, document_preparation.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from ...audit import get_audit
from ...state import BrokerState
from ..base import _trace, summarize_for_audit
from ._common import llm_plan_workers, merge_worker_outputs

log = logging.getLogger("bos.managers.operations")

WORKER_CAPABILITIES = {
    "crm_worker": "client lookup, create, update, conversation log",
    "document_worker": "prepare account-opening/transfer/KYC forms, fill forms, extract info",
    "calendar_worker": "schedule meetings, set reminders, list events",
}


def operations_manager_node(state: BrokerState) -> Dict[str, Any]:
    _trace(state, "operations_manager")
    thread_id = state.get("thread_id", "unknown")
    user_msg = state.get("user_message", "")
    user_profile = state.get("user_profile") or {}
    intent = state.get("intent", "")

    # 1. Plan
    plan = llm_plan_workers(
        manager="operations",
        intent=intent,
        user_message=user_msg,
        user_profile=user_profile,
        allowed_workers=list(WORKER_CAPABILITIES.keys()),
        worker_capabilities=WORKER_CAPABILITIES,
    )

    # 2. Translate plan params into state hints for the workers.
    #    The actual worker execution happens in the main graph (parallel fan-out).
    state_updates: Dict[str, Any] = {"worker_plan": [w["name"] for w in plan["workers"]]}
    for w in plan["workers"]:
        params = w.get("params") or {}
        if w["name"] == "crm_worker":
            if params.get("op"):
                state_updates["crm_op"] = params["op"]
            if params.get("client_id"):
                state_updates["crm_client_id"] = params["client_id"]
            if params.get("fields"):
                state_updates["crm_fields"] = params["fields"]
        elif w["name"] == "document_worker":
            if params.get("op"):
                state_updates["doc_op"] = params["op"]
            if params.get("template"):
                state_updates["doc_template"] = params["template"]
            if params.get("fields"):
                state_updates["doc_fields"] = params["fields"]
        elif w["name"] == "calendar_worker":
            if params.get("op"):
                state_updates["cal_op"] = params["op"]
            for k in ("title", "when", "duration", "attendees", "notes", "event_id", "message", "delay_min"):
                if k in params:
                    state_updates[f"cal_{k}"] = params[k]

    get_audit().record_event(
        thread_id=thread_id,
        agent="operations_manager",
        event_type="plan",
        reasoning=plan.get("reasoning", ""),
        tools=[w["name"] for w in plan["workers"]],
        input_summary=summarize_for_audit(user_msg),
        output_summary=f"planned workers: {state_updates['worker_plan']}",
        metadata={"plan": plan},
    )

    return {**state_updates, "trace": _trace(state, "operations_manager")}
