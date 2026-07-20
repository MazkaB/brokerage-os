"""
Compliance Manager agent.

Owns: Compliance Worker (KYC/AML/Policy), Retrieval Worker (regulations lookup).
Intents typically routed here: compliance_review, kyc_verification,
aml_screening, policy_question, account_opening (co-reviewed).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from ...audit import get_audit
from ...state import BrokerState
from ..base import _trace, summarize_for_audit
from ._common import llm_plan_workers, merge_worker_outputs

log = logging.getLogger("bos.managers.compliance")

WORKER_CAPABILITIES = {
    "compliance_worker": "KYC verification, AML screening, policy validation",
    "retrieval_worker": "RAG search over regulations, compliance manuals, SOPs",
}


def compliance_manager_node(state: BrokerState) -> Dict[str, Any]:
    _trace(state, "compliance_manager")
    thread_id = state.get("thread_id", "unknown")
    user_msg = state.get("user_message", "")
    user_profile = state.get("user_profile") or {}
    intent = state.get("intent", "")

    plan = llm_plan_workers(
        manager="compliance",
        intent=intent,
        user_message=user_msg,
        user_profile=user_profile,
        allowed_workers=list(WORKER_CAPABILITIES.keys()),
        worker_capabilities=WORKER_CAPABILITIES,
    )

    state_updates: Dict[str, Any] = {"worker_plan": [w["name"] for w in plan["workers"]]}

    # POLICY GUARDRAIL: If user is asking about a policy / requirement /
    # regulation question, ALWAYS include the retrieval_worker so the
    # composer has grounded KB text to cite. This reduces hallucination.
    question_patterns = ("what", "how", "policy", "requirement", "rule",
                         "explain", "guideline", "regulation", "kyc", "aml")
    if (any(p in user_msg.lower() for p in question_patterns)
            and "retrieval_worker" not in state_updates["worker_plan"]):
        state_updates["worker_plan"].append("retrieval_worker")
        state_updates["retrieval_query"] = user_msg
    for w in plan["workers"]:
        params = w.get("params") or {}
        if w["name"] == "compliance_worker":
            if params.get("op"):
                state_updates["comp_op"] = params["op"]
            if params.get("kyc_data"):
                state_updates["kyc_data"] = params["kyc_data"]
        elif w["name"] == "retrieval_worker":
            if params.get("query"):
                state_updates["retrieval_query"] = params["query"]
            if params.get("doc_type"):
                state_updates["retrieval_doc_type"] = params["doc_type"]

    get_audit().record_event(
        thread_id=thread_id,
        agent="compliance_manager",
        event_type="plan",
        reasoning=plan.get("reasoning", ""),
        tools=[w["name"] for w in plan["workers"]],
        input_summary=summarize_for_audit(user_msg),
        output_summary=f"planned workers: {state_updates['worker_plan']}",
        metadata={"plan": plan},
    )

    return {**state_updates, "trace": _trace(state, "compliance_manager")}
