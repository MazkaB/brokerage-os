"""Research Worker agent.

Responsibilities (FR4):
  * summarize market news
  * analyze securities
  * compare funds

Uses Gemini to turn raw tool output into a concise investor-friendly
summary. The numbers themselves always come from the (mock) tool layer,
NOT from the LLM, to keep hallucination risk low (PRD KPI: <2%).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from ...audit import get_audit
from ...state import BrokerState
from ...tools.research import research_market_news, research_security, research_compare_funds
from ..base import _trace, chat, summarize_for_audit

log = logging.getLogger("bos.workers.research")


def research_worker_node(state: BrokerState) -> Dict[str, Any]:
    _trace(state, "research_worker")
    thread_id = state.get("thread_id", "unknown")
    user_msg = state.get("user_message", "")

    op = state.get("research_op", "auto")  # auto | news | security | compare
    topic = state.get("research_topic")
    symbols: Optional[List[str]] = state.get("research_symbols")
    funds: Optional[List[str]] = state.get("research_funds")

    # Auto-detect symbols in the user message (simple CAP+ regex)
    if not symbols and op in ("auto", "security"):
        import re
        symbols = re.findall(r"\b[A-Z]{2,6}\b", user_msg)
        symbols = [s for s in symbols if s not in {"I", "A", "ME", "KYC", "AML", "PDF", "API"}][:5]

    summary: str = ""
    data: Dict[str, Any] = {}
    tools_used: List[str] = []
    citations: List[str] = []
    errors: str = ""

    try:
        if op in ("auto", "news"):
            r = research_market_news(topic=topic or (symbols[0] if symbols else None))
            data["news"] = r.data["news"]
            tools_used += r.tools_used
            citations += r.citations
        if op in ("auto", "security") and symbols:
            secs = []
            for sym in symbols:
                r = research_security(sym)
                if r.ok:
                    secs.append(r.data)
                    citations += r.citations
            data["securities"] = secs
            tools_used.append("research.security")
        if op in ("auto", "compare") and funds:
            r = research_compare_funds(funds)
            data["funds"] = r.data["funds"]
            tools_used += r.tools_used
            citations += r.citations

        # Use LLM to produce a concise summary grounded in tool data
        try:
            sys_prompt = (
                "You are a brokerage research analyst. Summarize the provided data in 3-5 concise bullet points. "
                "Only use the provided data. Do not invent numbers. "
                "Avoid giving personalized investment advice."
            )
            user_prompt = (
                f"User question: {user_msg}\n\n"
                f"Research data (JSON):\n{json.dumps(data, default=str)[:4000]}"
            )
            llm_summary = chat(sys_prompt, user_prompt, temperature=0.2)
            summary = llm_summary.strip()
        except Exception as e:
            log.warning("Research LLM summary failed: %s", e)
            summary = f"Retrieved research data for {symbols or topic} (LLM summary unavailable)"
    except Exception as e:
        log.warning("Research worker error: %s", e)
        errors = str(e)
        summary = f"Research op '{op}' failed: {e}"

    get_audit().record_event(
        thread_id=thread_id,
        agent="research_worker",
        event_type="worker_run",
        reasoning=summarize_for_audit(user_msg),
        tools=tools_used,
        documents=citations,
        input_summary=str({"op": op, "symbols": symbols, "topic": topic}),
        output_summary=summarize_for_audit(summary),
        metadata={"data": data, "error": errors},
    )

    result: Dict[str, Any] = {
        "worker": "research_worker",
        "status": "failed" if errors else "success",
        "summary": summary,
        "data": data,
        "tools_used": tools_used,
        "citations": citations,
        "error": errors or None,
        "confidence": 0.85 if not errors else 0.3,
    }
    worker_outputs = dict(state.get("worker_outputs") or {})
    worker_outputs["research_worker"] = result
    return {"worker_outputs": worker_outputs}
