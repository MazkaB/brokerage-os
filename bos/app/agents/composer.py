"""
Final response composer.

Takes the merged worker outputs + relevant policies + (optional) approval
decision and produces the final user-facing response via Gemini.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from ..audit import get_audit
from ..security import mask_pii
from ..state import BrokerState
from .base import _trace, chat, summarize_for_audit

log = logging.getLogger("bos.composer")


COMPOSE_SYSTEM_PROMPT = """You are the final-response composer for a Brokerage Operating System.
You will receive:
  - the user's original message,
  - the workflow trace,
  - structured outputs from specialist worker agents,
  - (optionally) relevant policy/KB excerpts,
  - (optionally) a human approval decision.

Write a concise, professional response addressed to a financial advisor.
Rules:
  - Be specific and grounded in the worker data; cite numbers/tools where relevant.
  - If approval was rejected or expired, clearly tell the user the action was not taken and why.
  - List concrete next steps when applicable.
  - Do NOT give personalized investment advice.
  - Use Markdown formatting (headings, bullets, bold) but keep it short.
"""


def compose_response_node(state: BrokerState) -> Dict[str, Any]:
    _trace(state, "compose_response")
    thread_id = state.get("thread_id", "unknown")

    worker_outputs = state.get("worker_outputs") or {}
    policies = state.get("relevant_policies") or []
    approval = state.get("approval") or {}
    intent = state.get("intent", "")

    payload = {
        "user_message": state.get("user_message", ""),
        "intent": intent,
        "manager": state.get("manager"),
        "worker_outputs": {
            name: {
                "status": r.get("status"),
                "summary": r.get("summary"),
                "data": r.get("data"),
                "citations": r.get("citations"),
                "error": r.get("error"),
            }
            for name, r in worker_outputs.items()
        },
        "relevant_policies": [{"source": p.get("source"), "text": p.get("text", "")[:300]} for p in policies],
        "approval": approval,
        "trace": state.get("trace", []),
    }

    user_prompt = (
        f"Compose the final response to the user. Workflow payload (JSON):\n"
        f"{json.dumps(payload, default=str)[:6000]}"
    )

    try:
        text = chat(COMPOSE_SYSTEM_PROMPT, user_prompt, temperature=0.3)
    except Exception as e:
        log.warning("Composer LLM failed (%s) - fallback to worker summaries", e)
        # Deterministic fallback so the workflow still completes
        lines = [f"### {intent.replace('_',' ').title()}"]
        for name, r in worker_outputs.items():
            lines.append(f"- **{name}**: {r.get('summary','(no output)')}")
        if approval:
            dec = approval.get("decision", "pending")
            lines.append(f"\n**Approval**: {dec}")
        if policies:
            lines.append("\n**Relevant policy excerpts**:")
            for p in policies[:3]:
                lines.append(f"- {p.get('source','?')}: {p.get('text','')[:200]}")
        text = "\n".join(lines)

    # Strip trailing whitespace; the API does newline normalization
    text = text.strip()

    # Aggregate citations
    citations = []
    for r in worker_outputs.values():
        citations.extend(r.get("citations") or [])

    audit = get_audit()
    audit.record_event(
        thread_id=thread_id,
        agent="composer",
        event_type="compose",
        reasoning="composed final response from worker outputs",
        input_summary=summarize_for_audit(state.get("user_message", "")),
        output_summary=summarize_for_audit(text),
        documents=citations,
        human_approval=approval or None,
        metadata={"intent": intent, "worker_count": len(worker_outputs)},
    )
    audit.upsert_workflow(
        thread_id=thread_id,
        status="completed",
        final_response=text,
    )

    return {
        "final_response": text,
        "citations": citations,
        "trace": _trace(state, "compose_response"),
    }
