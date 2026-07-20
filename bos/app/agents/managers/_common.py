"""
Shared manager helpers.

A manager node does two things:
  1. PLANNING: Given the CEO intent + user message, decide which workers
     to invoke and any per-worker parameters (using Gemini structured
     output). Falls back to a rule-based planner if the LLM call fails.
  2. PRE/POST work: set state hints for workers, then merge worker outputs.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from ..base import _trace, chat_json, summarize_for_audit
from ...audit import get_audit
from ...state import BrokerState

log = logging.getLogger("bos.managers")


def llm_plan_workers(
    *,
    manager: str,
    intent: str,
    user_message: str,
    user_profile: Dict[str, Any],
    allowed_workers: List[str],
    worker_capabilities: Dict[str, str],
) -> Dict[str, Any]:
    """Ask Gemini to produce a worker plan for this manager.

    Returns: {"workers": [{"name": str, "params": {...}}, ...], "reasoning": str}
    On failure returns a rule-based fallback plan.
    """
    sys_prompt = (
        f"You are the {manager.replace('_', ' ').title()} inside a brokerage OS. "
        "Your job is to decide which specialist worker agents should run to satisfy "
        "the user's request, and with what parameters.\n\n"
        f"Available workers under your supervision and their capabilities:\n"
        + json.dumps(worker_capabilities, indent=2)
        + "\n\nRules:\n"
        "- Only choose workers from the list above.\n"
        "- Each chosen worker needs a `name` and an optional `params` dict.\n"
        "- Prefer the smallest sufficient set of workers (1-3).\n"
        "- RESPOND IN JSON: {\"workers\": [{\"name\": \"...\", \"params\": {...}}], \"reasoning\": \"...\"}"
    )
    user_prompt = (
        f"User message: {user_message}\n"
        f"Intent: {intent}\n"
        f"User profile: {json.dumps(user_profile, default=str)[:600]}\n"
    )
    try:
        from ..errors import LLMUnavailable
        try:
            out = chat_json(sys_prompt, user_prompt, temperature=0.1)
        except LLMUnavailable as e:
            raise e
        if out.get("_parse_error") or "workers" not in out:
            raise ValueError("invalid plan")
        # Filter to allowed workers
        valid = []
        for w in out.get("workers", []):
            name = w.get("name")
            if name in allowed_workers:
                valid.append({"name": name, "params": w.get("params", {})})
        if not valid:
            raise ValueError("no valid workers")
        return {"workers": valid, "reasoning": out.get("reasoning", "")}
    except Exception as e:
        log.info("LLM planning failed (%s) - using fallback", e)
        # Deterministic fallback: pick a default worker per manager+intent
        return _rule_based_plan(manager, intent, user_message, allowed_workers)


def _rule_based_plan(
    manager: str, intent: str, user_message: str, allowed_workers: List[str]
) -> Dict[str, Any]:
    """Deterministic fallback planner used when the LLM is unavailable."""
    text = (user_message or "").lower()
    plan: List[Dict[str, Any]] = []

    if manager == "operations":
        if "open" in text or "account" in text or intent in ("account_opening", "account_transfer"):
            plan.append({"name": "document_worker", "params": {
                "op": "prepare",
                "template": "account_opening" if "open" in text else "account_transfer",
                "fields": {
                    "full_name": "New Client",
                    "account_type": "Individual",
                    "risk_tolerance": "moderate",
                    "email": "client@example.com",
                    "phone": "(000) 000-0000",
                    "kyc_status": "verified",
                },
            }})
        elif "schedule" in text or "meeting" in text or intent == "scheduling":
            plan.append({"name": "calendar_worker", "params": {
                "op": "schedule", "title": "Client meeting",
            }})
        elif "client" in text or "lookup" in text:
            plan.append({"name": "crm_worker", "params": {"op": "list"}})
        else:
            plan.append({"name": "crm_worker", "params": {"op": "list"}})

    elif manager == "compliance":
        # Always run compliance_worker for compliance intents so KYC/AML
        # checks are evaluated, plus retrieval_worker for policy questions.
        plan.append({"name": "compliance_worker", "params": {"op": "full"}})
        if any(w in text for w in ("what", "how", "policy", "requirement", "explain", "rule")):
            plan.append({"name": "retrieval_worker", "params": {"query": user_message}})

    elif manager == "portfolio":
        import re
        symbols = re.findall(r"\b[A-Z]{2,6}\b", user_message)
        symbols = [s for s in symbols if s not in {"I", "A", "ME", "KYC", "AML", "PDF", "API"}][:5]
        plan.append({"name": "research_worker", "params": {
            "op": "auto", "symbols": symbols or None,
        }})

    # Filter to allowed workers and ensure at least one
    plan = [p for p in plan if p["name"] in allowed_workers]
    if not plan:
        plan.append({"name": allowed_workers[0], "params": {}})

    return {"workers": plan, "reasoning": f"rule-based fallback plan for manager={manager}"}


def merge_worker_outputs(state: BrokerState, manager_name: str) -> Dict[str, Any]:
    """Produce a combined summary of all worker outputs for this turn."""
    outputs = state.get("worker_outputs") or {}
    parts: List[str] = []
    for name, res in outputs.items():
        status = res.get("status", "?")
        summ = res.get("summary", "")
        parts.append(f"- [{name} / {status}] {summ}")
    merged = "\n".join(parts) if parts else "(no workers ran)"

    get_audit().record_event(
        thread_id=state.get("thread_id", "unknown"),
        agent=manager_name,
        event_type="merge",
        reasoning="merged worker outputs",
        input_summary=", ".join(outputs.keys()) or "(none)",
        output_summary=summarize_for_audit(merged, 320),
    )
    _trace(state, f"{manager_name}_merge")
    return {"short_term_summary": merged}
