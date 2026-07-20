"""
Base agent utilities shared by every BOS agent.

Each agent is implemented as a *node function* with the signature
    fn(state: BrokerState) -> dict
that returns a state delta. The CEO/manager/worker nodes are stitched
together in `app/graph.py`.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from ..llm import get_llm
from ..security import mask_pii
from ..state import BrokerState

log = logging.getLogger("bos.agents")


def _trace(state: BrokerState, node: str) -> list:
    """Append a node name to the human-readable trace list and return the
    updated list, so callers can include it in their state delta.

    Usage in a node:
        return {"final_response": text, "trace": _trace(state, "my_node")}
    """
    tr = list(state.get("trace") or [])
    if not tr or tr[-1] != node:
        tr.append(node)
    state["trace"] = tr  # mutate in place for siblings that share state
    return tr


def chat(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    """Synchronous one-shot LLM call. Returns the model's text output.

    On failure (quota, network, auth) raises LLMUnavailable so callers can
    fall back to deterministic logic instead of crashing the workflow.
    Records token usage + latency to the metrics store.
    """
    import time as _time
    from .errors import LLMUnavailable
    from ..metrics import get_metrics
    try:
        llm = get_llm(temperature=temperature)
        msgs = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        t0 = _time.time()
        resp = llm.invoke(msgs)
        latency_ms = int((_time.time() - t0) * 1000)
        # Capture usage metadata for cost/token tracking
        meta = getattr(resp, "usage_metadata", None) or {}
        model_name = getattr(llm, "model_name", "") or getattr(llm, "model", "")
        try:
            get_metrics().record(
                node="chat", model=str(model_name),
                prompt_tokens=int(meta.get("input_tokens", 0)),
                completion_tokens=int(meta.get("output_tokens", 0)),
                latency_ms=latency_ms, success=True,
            )
        except Exception:
            pass
        text = getattr(resp, "content", str(resp))
        return text if isinstance(text, str) else str(text)
    except Exception as e:
        log.warning("chat() LLM call failed: %s", e)
        try:
            get_metrics().record(node="chat", success=False, error=str(e)[:200])
        except Exception:
            pass
        raise LLMUnavailable(str(e)) from e


def chat_json(system_prompt: str, user_prompt: str, temperature: float = 0.1) -> Dict[str, Any]:
    """LLM call whose output is parsed as JSON.

    On failure raises LLMUnavailable so callers can fall back.
    """
    import json
    import re
    from .errors import LLMUnavailable

    llm = get_llm(temperature=temperature)
    sys2 = system_prompt.rstrip()
    if "RESPOND IN JSON" not in sys2.upper():
        sys2 += "\n\nYou MUST respond with a single valid JSON object and nothing else. No markdown, no commentary."
    msgs = [
        SystemMessage(content=sys2),
        HumanMessage(content=user_prompt),
    ]
    try:
        resp = llm.invoke(msgs)
    except Exception as e:
        log.warning("chat_json() LLM call failed: %s", e)
        raise LLMUnavailable(str(e)) from e
    text = getattr(resp, "content", str(resp))
    if not isinstance(text, str):
        text = str(text)
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else text
    try:
        return json.loads(candidate)
    except Exception:
        m = re.search(r"\{.*\}", candidate, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception as e:
                log.warning("JSON parse failed (%s). Raw: %s", e, candidate[:300])
        return {"_parse_error": True, "_raw": candidate[:500]}


def summarize_for_audit(text: str, max_len: int = 280) -> str:
    """Short, PII-masked text snippet for audit logs."""
    if not text:
        return ""
    snippet = text.strip().replace("\n", " ")
    if len(snippet) > max_len:
        snippet = snippet[:max_len] + "..."
    return mask_pii(snippet)
