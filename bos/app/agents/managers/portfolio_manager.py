"""
Portfolio Manager agent.

Owns: Research Worker, Retrieval Worker (for research/KB context).
Intents typically routed here: market_research, security_analysis,
fund_comparison, portfolio_review.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from ...audit import get_audit
from ...state import BrokerState
from ..base import _trace, summarize_for_audit
from ._common import llm_plan_workers, merge_worker_outputs

log = logging.getLogger("bos.managers.portfolio")

WORKER_CAPABILITIES = {
    "research_worker": "market news, security analysis, fund comparison",
    "retrieval_worker": "RAG search over investment guidelines, market research notes",
}


def portfolio_manager_node(state: BrokerState) -> Dict[str, Any]:
    _trace(state, "portfolio_manager")
    thread_id = state.get("thread_id", "unknown")
    user_msg = state.get("user_message", "")
    user_profile = state.get("user_profile") or {}
    intent = state.get("intent", "")

    plan = llm_plan_workers(
        manager="portfolio",
        intent=intent,
        user_message=user_msg,
        user_profile=user_profile,
        allowed_workers=list(WORKER_CAPABILITIES.keys()),
        worker_capabilities=WORKER_CAPABILITIES,
    )

    state_updates: Dict[str, Any] = {"worker_plan": [w["name"] for w in plan["workers"]]}
    for w in plan["workers"]:
        params = w.get("params") or {}
        if w["name"] == "research_worker":
            if params.get("op"):
                state_updates["research_op"] = params["op"]
            if params.get("symbols"):
                state_updates["research_symbols"] = params["symbols"]
            if params.get("topic"):
                state_updates["research_topic"] = params["topic"]
            if params.get("funds"):
                state_updates["research_funds"] = params["funds"]
        elif w["name"] == "retrieval_worker":
            if params.get("query"):
                state_updates["retrieval_query"] = params["query"]
            if params.get("doc_type"):
                state_updates["retrieval_doc_type"] = params["doc_type"]

    get_audit().record_event(
        thread_id=thread_id,
        agent="portfolio_manager",
        event_type="plan",
        reasoning=plan.get("reasoning", ""),
        tools=[w["name"] for w in plan["workers"]],
        input_summary=summarize_for_audit(user_msg),
        output_summary=f"planned workers: {state_updates['worker_plan']}",
        metadata={"plan": plan},
    )

    return {**state_updates, "trace": _trace(state, "portfolio_manager")}
