"""Retrieval Worker agent.

Responsibilities (FR4):
  RAG-backed lookup over organizational knowledge base:
   * CRM, PDFs, regulations, KB, emails

This worker is the only one whose underlying tool is fully functional
(Chroma + Gemini embeddings) in Phase 1.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from ...audit import get_audit
from ...state import BrokerState
from ...tools.retrieval import retrieval_search
from ..base import _trace, summarize_for_audit

log = logging.getLogger("bos.workers.retrieval")


def retrieval_worker_node(state: BrokerState) -> Dict[str, Any]:
    _trace(state, "retrieval_worker")
    thread_id = state.get("thread_id", "unknown")
    user_msg = state.get("user_message", "")

    # Build the query: explicit override > intent-derived > raw user message
    query = state.get("retrieval_query") or user_msg or ""
    k = int(state.get("retrieval_k", 5))
    doc_type = state.get("retrieval_doc_type")

    summary: str = ""
    data: Dict[str, Any] = {}
    citations = []
    tools_used = ["retrieval.search"]
    errors: str = ""

    try:
        r = retrieval_search(query, k=k, doc_type=doc_type)
        data["results"] = r.data.get("results", [])
        data["count"] = r.data.get("count", 0)
        citations = r.citations
        if data["count"] == 0:
            summary = "No relevant policy/KB documents found"
        else:
            summary = f"Retrieved {data['count']} relevant document(s) from organizational KB"
    except Exception as e:
        log.warning("Retrieval worker error: %s", e)
        errors = str(e)
        summary = f"Retrieval failed: {e}"

    # Surface relevant policies into state for the final response composer
    relevant_policies = [
        {"source": r["source"], "text": r["text"][:400], "score": r.get("score")}
        for r in data.get("results", [])
    ]

    get_audit().record_event(
        thread_id=thread_id,
        agent="retrieval_worker",
        event_type="worker_run",
        reasoning=summarize_for_audit(query),
        tools=tools_used,
        documents=citations,
        input_summary=query[:200],
        output_summary=summarize_for_audit(summary),
        metadata={"count": data.get("count"), "error": errors},
    )

    result: Dict[str, Any] = {
        "worker": "retrieval_worker",
        "status": "failed" if errors else "success",
        "summary": summary,
        "data": data,
        "tools_used": tools_used,
        "citations": citations,
        "error": errors or None,
        "confidence": 0.9 if not errors else 0.3,
    }
    worker_outputs = dict(state.get("worker_outputs") or {})
    worker_outputs["retrieval_worker"] = result
    return {
        "worker_outputs": worker_outputs,
        "relevant_policies": relevant_policies,
    }
