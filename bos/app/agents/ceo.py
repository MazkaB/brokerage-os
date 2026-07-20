"""
CEO Agent (Supervisor).

Responsibilities (FR2):
  * Understand request
  * Identify workflow / intent
  * Allocate manager agent
  * Resolve conflicts / escalate failures
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Literal

from ..audit import get_audit
from ..llm import get_llm
from ..security import mask_pii
from ..state import BrokerState
from .base import _trace, chat_json, summarize_for_audit

log = logging.getLogger("bos.ceo")


# Allowed manager targets. Each must exist in MANAGER_REGISTRY.
ALLOWED_MANAGERS = ["operations", "compliance", "portfolio", "clarify", "general"]


INTENT_PROMPT = """You are the CEO supervisor of a brokerage operating system.
Your job: read the user's message + context and produce a routing decision.

Decide:
  - `intent`: a short snake_case label for what the user wants.
  - `manager`: which manager should own this workflow. Must be one of:
      "operations"  -> client/CRM, account opening/transfer, document prep, scheduling
      "compliance"  -> KYC, AML, policy/regulation questions, compliance review
      "portfolio"   -> market research, security analysis, fund comparison, portfolio review
      "clarify"     -> user's request is ambiguous and you must ask a clarifying question
      "general"     -> greeting, smalltalk, help
  - `confidence`: float 0..1 for your routing certainty
  - `clarification_question`: if `manager`=="clarify", the question to ask
  - `reasoning`: one-sentence rationale

Examples:
  Q: "Open a new retirement account for Jane"
     -> {"intent":"account_opening","manager":"operations","confidence":0.95}
  Q: "Is this client KYC compliant?"
     -> {"intent":"kyc_verification","manager":"compliance","confidence":0.93}
  Q: "Summarize AAPL and TSLA"
     -> {"intent":"security_analysis","manager":"portfolio","confidence":0.95}
  Q: "Hello"
     -> {"intent":"greeting","manager":"general","confidence":0.99}
  Q: "Do the thing"
     -> {"intent":"unclear","manager":"clarify","confidence":0.4,
         "clarification_question":"Could you describe what you'd like me to do?"}

RESPOND IN JSON ONLY:
  {"intent": "...", "manager": "...", "confidence": 0.0,
   "clarification_question": "...", "reasoning": "..."}
"""


def ceo_classify_node(state: BrokerState) -> Dict[str, Any]:
    """CEO node #1: classify intent + route to a manager."""
    _trace(state, "ceo_classify")
    thread_id = state.get("thread_id", "unknown")
    user_msg = state.get("user_message", "")
    user_profile = state.get("user_profile") or {}

    # Build the user-prompt with context
    context = {
        "user_id": state.get("user_id"),
        "username": state.get("username"),
        "role": state.get("role"),
        "client_id": user_profile.get("client_id"),
        "account_type": user_profile.get("account_type"),
        "risk_tolerance": user_profile.get("risk_tolerance"),
        "recent_summary": (state.get("short_term_summary") or "")[:600],
    }
    user_prompt = (
        f"User message: {user_msg}\n\n"
        f"Context: {json.dumps(context, default=str)}\n"
    )

    try:
        decision = chat_json(INTENT_PROMPT, user_prompt, temperature=0.1)
        if decision.get("_parse_error") or decision.get("manager") not in ALLOWED_MANAGERS:
            raise ValueError("invalid LLM output")
        used_fallback = False
    except Exception as e:
        # Fallback to deterministic keyword-based classifier when the LLM
        # is unavailable (quota, network, auth) or returns garbage. This
        # is the PRD's "hardcoded guardrails" requirement.
        log.warning("CEO LLM unavailable (%s) - using rule-based classifier", e)
        decision = _rule_based_classify(user_msg)
        used_fallback = True

    intent = decision.get("intent", "general")
    manager = decision.get("manager", "general")
    confidence = float(decision.get("confidence", 0.5))
    needs_clarification = manager == "clarify"
    clarification = decision.get("clarification_question")

    get_audit().record_event(
        thread_id=thread_id,
        agent="ceo",
        event_type="classify",
        reasoning=decision.get("reasoning", ""),
        input_summary=summarize_for_audit(user_msg),
        output_summary=f"intent={intent} manager={manager} confidence={confidence:.2f} fallback={used_fallback}",
        metadata={"decision": decision, "context": context, "fallback": used_fallback},
    )

    return {
        "intent": intent,
        "intent_confidence": confidence,
        "manager": manager,
        "active_manager": manager,
        "intent_needs_clarification": needs_clarification,
        "clarification_question": clarification,
        "trace": _trace(state, "ceo_classify"),
        # FIX BUG-1 (state pollution across turns on same thread):
        # LangGraph checkpointer persists per-thread state across invocations,
        # so transient approval / worker state from a previous turn leaks
        # into the new turn and can cause false-positive approval gates.
        # Explicitly reset these here at the start of every new classification.
        "approval_required": False,
        "approval": None,
        "worker_outputs": {},
        "worker_plan": [],
        "worker_errors": {},
        "relevant_policies": [],
        "retry_count": {},
        "errors": [],
    }


# ---------------------------------------------------------------------------
# Rule-based fallback classifier (no LLM required)
# ---------------------------------------------------------------------------
def _rule_based_classify(user_msg: str) -> Dict[str, Any]:
    """Deterministic keyword-based intent classifier.

    Used when the LLM is unavailable. Covers the main intents the system
    is designed to handle. Returns the same shape as the LLM classifier.
    """
    text = (user_msg or "").lower()
    rules = [
        (("open", "open a new", "new account", "retirement account", "account opening"), "account_opening", "operations"),
        (("transfer", "move my", "acats"), "account_transfer", "operations"),
        (("schedule", "meeting", "appointment", "calendar"), "scheduling", "operations"),
        (("client", "crm", "lookup"), "client_lookup", "operations"),
        (("form", "document", "pdf", "generate"), "document_preparation", "operations"),
        (("kyc", "aml", "compliance", "policy", "requirement", "regulation", "rule"), "compliance_review", "compliance"),
        (("research", "analyze", "summarize", "summary of", "fund", "compare", "market"), "market_research", "portfolio"),
        (("price", "stock", "security", "ticker"), "security_analysis", "portfolio"),
    ]
    for keywords, intent, manager in rules:
        if any(k in text for k in keywords):
            return {
                "intent": intent, "manager": manager, "confidence": 0.7,
                "reasoning": f"rule-based match for {intent}",
            }
    # Ticker symbol detection (e.g. "Summarize AAPL")
    import re
    symbols = re.findall(r"\b[A-Z]{2,6}\b", user_msg or "")
    if symbols and not any(w in text for w in ("kyc", "aml")):
        return {"intent": "security_analysis", "manager": "portfolio",
                "confidence": 0.7, "reasoning": "rule-based: ticker symbol detected"}
    # Greeting detection
    if any(w in text for w in ("hello", "hi ", "hey", "help", "what can you do")):
        return {"intent": "greeting", "manager": "general", "confidence": 0.8,
                "reasoning": "rule-based: greeting/help"}
    # Default to general
    return {"intent": "general", "manager": "general", "confidence": 0.5,
            "reasoning": "rule-based: no keyword matched"}


def ceo_route(state: BrokerState) -> str:
    """Conditional edge after classification.

    Implements PRD conditional routing: if confidence < CLARIFY_THRESHOLD
    and intent isn't a trivial greeting, escalate to the clarification
    agent instead of guessing. This is the "hardcoded guardrail" the PRD
    requires against LLM-hallucinated routing.

    Note: we use a conservative threshold (0.5) because rule-based fallbacks
    intentionally report confidence 0.5-0.8 — those are deterministic and
    should not be falsely sent to clarify.
    """
    CLARIFY_THRESHOLD = 0.5
    if state.get("intent_needs_clarification"):
        return "clarify"
    confidence = float(state.get("intent_confidence") or 0.0)
    intent = state.get("intent") or "general"
    manager = state.get("manager") or "general"
    # Greetings / general chat are safe at any confidence
    if manager in ("general",):
        return "general"
    # Routing decisions below threshold must be clarified
    if confidence < CLARIFY_THRESHOLD and intent != "greeting":
        log.info(
            "CEO routing to clarify (confidence=%.2f < %.2f, intent=%s)",
            confidence, CLARIFY_THRESHOLD, intent,
        )
        return "clarify"
    if manager in ("operations", "compliance", "portfolio"):
        return manager
    return "general"


def ceo_general_node(state: BrokerState) -> Dict[str, Any]:
    """Handle greetings / general chat directly without a manager."""
    from .base import chat
    _trace(state, "ceo_general")
    thread_id = state.get("thread_id", "unknown")
    user_msg = state.get("user_message", "")
    user_profile = state.get("user_profile") or {}

    sys_prompt = (
        "You are the CEO of a Brokerage Operating System. The user sent a general "
        "message (greeting, smalltalk, help request). Answer briefly and helpfully. "
        "If they ask what you can do, mention: account opening, account transfer, "
        "client lookups, KYC/AML checks, compliance questions, scheduling, and "
        "market research / security analysis."
    )
    try:
        text = chat(sys_prompt, f"User message: {user_msg}\nUser: {user_profile.get('username', 'user')}")
    except Exception as e:
        log.warning("CEO general chat LLM unavailable: %s", e)
        text = (
            "Hello! I'm the **Brokerage Operating System**. "
            "I can help you with:\n"
            "- **Account opening & transfers** (Operations)\n"
            "- **KYC / AML / policy questions** (Compliance)\n"
            "- **Market research & security analysis** (Portfolio)\n"
            "- **Scheduling & document generation**\n\n"
            "_Note: response composed from fallback template (LLM unavailable)._"
        )

    get_audit().record_event(
        thread_id=thread_id,
        agent="ceo",
        event_type="general_response",
        input_summary=summarize_for_audit(user_msg),
        output_summary=summarize_for_audit(text),
    )
    return {"final_response": text, "worker_plan": [], "trace": _trace(state, "ceo_general")}


def ceo_clarify_node(state: BrokerState) -> Dict[str, Any]:
    """Ask the user a clarifying question and stop the workflow."""
    _trace(state, "ceo_clarify")
    thread_id = state.get("thread_id", "unknown")
    q = state.get("clarification_question") or (
        "Could you provide more details about what you'd like to do?"
    )
    get_audit().record_event(
        thread_id=thread_id,
        agent="ceo",
        event_type="clarify",
        input_summary=summarize_for_audit(state.get("user_message", "")),
        output_summary=summarize_for_audit(q),
    )
    return {"final_response": q, "worker_plan": [], "trace": _trace(state, "ceo_clarify")}
