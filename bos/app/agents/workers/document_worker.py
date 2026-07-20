"""Document Worker agent.

Responsibilities (FR4):
  * prepare PDFs / forms
  * fill forms
  * extract information
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from ...audit import get_audit
from ...state import BrokerState
from ...tools.documents import doc_prepare_pdf, doc_fill_form, doc_extract_info, doc_list
from ..base import _trace, summarize_for_audit

log = logging.getLogger("bos.workers.document")


def document_worker_node(state: BrokerState) -> Dict[str, Any]:
    _trace(state, "document_worker")
    thread_id = state.get("thread_id", "unknown")
    user_msg = state.get("user_message", "")

    op = state.get("doc_op", "list")
    summary: str = ""
    data: Dict[str, Any] = {}
    tools_used = ["document.list"]
    errors: str = ""

    try:
        if op == "prepare":
            template = state.get("doc_template", "account_opening")
            fields = state.get("doc_fields") or {}
            r = doc_prepare_pdf(template, fields)
            if not r.ok:
                raise ValueError(r.error)
            data["doc_id"] = r.data["doc_id"]
            data["preview"] = r.data.get("preview", "")
            summary = f"Prepared {template} doc {r.data['doc_id']}"
            tools_used.append("document.prepare_pdf")
        elif op == "fill":
            doc_id = state.get("doc_id")
            fields = state.get("doc_fields") or {}
            if not doc_id:
                raise ValueError("doc_id required for fill op")
            r = doc_fill_form(doc_id, fields)
            if not r.ok:
                raise ValueError(r.error)
            data["doc_id"] = r.data["doc_id"]
            summary = f"Filled form {doc_id}"
            tools_used.append("document.fill_form")
        elif op == "extract":
            doc_id = state.get("doc_id")
            if not doc_id:
                raise ValueError("doc_id required for extract op")
            r = doc_extract_info(doc_id)
            if not r.ok:
                raise ValueError(r.error)
            data.update(r.data)
            summary = f"Extracted info from {doc_id}"
            tools_used.append("document.extract_info")
        else:  # list
            r = doc_list()
            data["documents"] = r.data["documents"]
            summary = f"Listed {len(r.data['documents'])} documents"
    except Exception as e:
        log.warning("Document worker error: %s", e)
        errors = str(e)
        summary = f"Doc op '{op}' failed: {e}"

    get_audit().record_event(
        thread_id=thread_id,
        agent="document_worker",
        event_type="worker_run",
        reasoning=summarize_for_audit(user_msg),
        tools=tools_used,
        input_summary=str({"op": op, "template": state.get("doc_template")}),
        output_summary=summarize_for_audit(summary),
        metadata={"data": data, "error": errors},
    )

    result: Dict[str, Any] = {
        "worker": "document_worker",
        "status": "failed" if errors else "success",
        "summary": summary,
        "data": data,
        "tools_used": tools_used,
        "error": errors or None,
        "confidence": 0.95 if not errors else 0.3,
    }
    worker_outputs = dict(state.get("worker_outputs") or {})
    worker_outputs["document_worker"] = result
    return {"worker_outputs": worker_outputs}
