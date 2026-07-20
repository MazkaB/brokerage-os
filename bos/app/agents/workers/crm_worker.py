"""CRM Worker agent.

Responsibilities (FR4):
  * create clients
  * update contacts
  * record conversations
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from ...audit import get_audit
from ...state import BrokerState
from ...tools.crm import crm_get_client, crm_create_client, crm_update_client, crm_record_conversation, crm_list_clients
from ..base import _trace, summarize_for_audit

log = logging.getLogger("bos.workers.crm")


def crm_worker_node(state: BrokerState) -> Dict[str, Any]:
    _trace(state, "crm_worker")
    thread_id = state.get("thread_id", "unknown")
    user_msg = state.get("user_message", "")
    user_profile = state.get("user_profile") or {}

    summary: str = ""
    data: Dict[str, Any] = {}
    tools_used = ["crm.list_clients"]
    errors: str = ""

    # Default action: look up clients (Phase 1 simplification - the manager
    # passes an explicit `crm_op` in state to override behavior).
    op = state.get("crm_op", "list")
    try:
        if op == "get":
            client_id = state.get("crm_client_id") or user_profile.get("client_id")
            if not client_id:
                raise ValueError("client_id required for get op")
            r = crm_get_client(client_id)
            if not r.ok:
                raise ValueError(r.error or "lookup failed")
            data["client"] = r.data["client"]
            summary = f"Retrieved client {client_id}"
            tools_used.append("crm.get_client")
        elif op == "create":
            fields = state.get("crm_fields") or {}
            r = crm_create_client(**fields)
            if not r.ok:
                raise ValueError(r.error or "create failed")
            data["client_id"] = r.data["client_id"]
            summary = f"Created new client {r.data['client_id']}"
            tools_used.append("crm.create_client")
        elif op == "update":
            client_id = state.get("crm_client_id") or user_profile.get("client_id")
            fields = state.get("crm_fields") or {}
            if not client_id:
                raise ValueError("client_id required for update op")
            r = crm_update_client(client_id, **fields)
            if not r.ok:
                raise ValueError(r.error or "update failed")
            data["client"] = r.data["client"]
            summary = f"Updated client {client_id}"
            tools_used.append("crm.update_client")
        else:  # list
            r = crm_list_clients()
            data["clients"] = r.data["clients"]
            summary = f"Listed {len(r.data['clients'])} clients"
    except Exception as e:
        log.warning("CRM worker error: %s", e)
        errors = str(e)
        summary = f"CRM op '{op}' failed: {e}"

    # Always record the conversation in the CRM for auditability
    try:
        crm_record_conversation(
            client_id=user_profile.get("client_id"),
            thread_id=thread_id,
            direction="inbound",
            channel="web",
            summary=user_msg[:240],
        )
        tools_used.append("crm.record_conversation")
    except Exception:
        pass

    get_audit().record_event(
        thread_id=thread_id,
        agent="crm_worker",
        event_type="worker_run",
        reasoning=summarize_for_audit(user_msg),
        tools=tools_used,
        input_summary=op,
        output_summary=summarize_for_audit(summary),
        metadata={"data": data, "error": errors},
    )

    result: Dict[str, Any] = {
        "worker": "crm_worker",
        "status": "failed" if errors else "success",
        "summary": summary,
        "data": data,
        "tools_used": tools_used,
        "error": errors or None,
        "confidence": 0.95 if not errors else 0.3,
    }
    worker_outputs = dict(state.get("worker_outputs") or {})
    worker_outputs["crm_worker"] = result
    return {"worker_outputs": worker_outputs}
