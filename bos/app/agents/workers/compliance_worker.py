"""Compliance Worker agent.

Responsibilities (FR4):
  * KYC verification
  * AML screening
  * policy validation

Also decides whether the workflow needs HITL approval based on policy.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from ...audit import get_audit
from ...config import APPROVAL_INTENTS
from ...state import BrokerState
from ...tools.compliance import comp_run_kyc, comp_run_aml, comp_validate_policy
from ..base import _trace, summarize_for_audit

log = logging.getLogger("bos.workers.compliance")


def compliance_worker_node(state: BrokerState) -> Dict[str, Any]:
    _trace(state, "compliance_worker")
    thread_id = state.get("thread_id", "unknown")
    user_msg = state.get("user_message", "")
    user_profile = state.get("user_profile") or {}
    intent = state.get("intent", "")

    op = state.get("comp_op", "full")  # full | kyc | aml | policy
    summary: str = ""
    data: Dict[str, Any] = {}
    tools_used: list = []
    errors: str = ""
    requires_approval = False

    try:
        kyc_data = state.get("kyc_data") or {
            "full_name": user_profile.get("full_name", "Unknown"),
            "gov_id": user_profile.get("gov_id", "id-proof.pdf"),
            "address_proof": user_profile.get("address_proof", "utility-bill.pdf"),
            "dob": user_profile.get("dob", "1985-01-01"),
            "country": user_profile.get("country", "US"),
        }

        if op in ("full", "kyc"):
            r = comp_run_kyc(kyc_data)
            data["kyc"] = r.data
            tools_used.append("compliance.run_kyc")
        if op in ("full", "aml"):
            r = comp_run_aml(kyc_data)
            data["aml"] = r.data
            tools_used.append("compliance.run_aml")

        if op in ("full", "policy"):
            payload = {
                "kyc_passed": data.get("kyc", {}).get("kyc_passed", True),
                "client": user_profile,
                "amount": state.get("amount", 0),
            }
            r = comp_validate_policy(intent or "general", payload)
            data["policy"] = r.data
            requires_approval = bool(r.data.get("requires_human_approval"))
            tools_used.append("compliance.validate_policy")

        # Also gate by global approval intent list
        if intent in APPROVAL_INTENTS:
            requires_approval = True

        summary = (
            f"KYC: {data.get('kyc', {}).get('kyc_passed')}, "
            f"AML risk: {data.get('aml', {}).get('risk_score')}, "
            f"approval_required: {requires_approval}"
        )
    except Exception as e:
        log.warning("Compliance worker error: %s", e)
        errors = str(e)
        summary = f"Compliance op '{op}' failed: {e}"

    get_audit().record_event(
        thread_id=thread_id,
        agent="compliance_worker",
        event_type="worker_run",
        reasoning=summarize_for_audit(user_msg),
        tools=tools_used,
        input_summary=str({"op": op, "intent": intent}),
        output_summary=summarize_for_audit(summary),
        metadata={"data": data, "error": errors, "requires_approval": requires_approval},
    )

    result: Dict[str, Any] = {
        "worker": "compliance_worker",
        "status": "failed" if errors else "success",
        "summary": summary,
        "data": data,
        "tools_used": tools_used,
        "error": errors or None,
        "confidence": 0.9 if not errors else 0.3,
        "requires_approval": requires_approval,
    }
    worker_outputs = dict(state.get("worker_outputs") or {})
    worker_outputs["compliance_worker"] = result
    # Promote approval-required flag to top-level state so the router can act on it
    delta: Dict[str, Any] = {"worker_outputs": worker_outputs}
    if requires_approval:
        delta["approval_required"] = True
    return delta
