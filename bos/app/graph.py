"""
BOS LangGraph definition.

This is the single place where all nodes (CEO, managers, workers, approval,
composer) are wired into a hierarchical StateGraph.

Topology:

  START
    |
    v
  ceo_classify ──[ceo_route]──┬─> clarify ────────────> END
                               ├─> general ────────────> END
                               ├─> operations_manager ─┐
                               ├─> compliance_manager ─┤
                               └─> portfolio_manager ──┘
                                                       v
                                       ┌──── fan_out_workers ────┐
                                       |   (parallel workers)    |
                                       └──────────┬──────────────┘
                                                  v
                                          approval_router ──┐
                                            |               |
                                  (no approval)         (needs_approval)
                                            |               v
                                            |        request_approval [INTERRUPT]
                                            |               |
                                            |        (resume with decision)
                                            |               |
                                            └──────► compose_response ──> END
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langgraph.graph import END, START, StateGraph

from .agents.ceo import (
    ceo_classify_node, ceo_clarify_node, ceo_general_node, ceo_route,
)
from .agents.composer import compose_response_node
from .agents.approval import approval_router, request_approval_node
from .agents.managers import (
    compliance_manager_node, operations_manager_node, portfolio_manager_node,
)
from .agents.workers import WORKER_REGISTRY
from .config import APPROVAL_INTENTS, TOOL_POLICY
from .memory.short_term import get_checkpointer
from .security import enforce_tool_policy
from .state import BrokerState

log = logging.getLogger("bos.graph")


# ---------------------------------------------------------------------------
# Worker fan-out / fan-in nodes
# ---------------------------------------------------------------------------
def fan_out_workers_node(state: BrokerState) -> Dict[str, Any]:
    """Invoke every worker listed in `worker_plan` sequentially.

    LangGraph has two ways to do parallelism:
      1. Conditional edges with `Send` (true parallelism via channels).
      2. Sequential calls inside one node (simpler, deterministic, plenty
         fast for Phase 1 workloads).

    We use approach (2) for Phase 1 because (a) our workers are fast
    in-process calls and (b) it makes the state diff trivially auditable.
    Phase 2 can swap to Send-based fan-out without changing the public API.
    """
    trace = list(state.get("trace") or [])
    trace.append("fan_out_workers")

    plan: List[str] = list(state.get("worker_plan") or [])
    intent = state.get("intent", "")

    # GUARDRAIL: For high-risk intents (FR6) ALWAYS include the compliance
    # worker, even if the manager didn't plan it. This guarantees the
    # approval gate fires deterministically and is not dependent on LLM
    # planning decisions (PRD: "hardcoded guardrails if LLM hallucinates").
    if intent in APPROVAL_INTENTS and "compliance_worker" not in plan:
        plan.append("compliance_worker")
        log.info("Guardrail: appended compliance_worker to plan for intent=%s", intent)

    if not plan:
        log.info("fan_out_workers: empty worker_plan, skipping")
        return {"trace": trace, "worker_plan": []}

    # Run each worker, threading state through.
    current: Dict[str, Any] = dict(state)
    current["trace"] = trace
    retry_counts = dict(current.get("retry_count") or {})
    MAX_RETRIES = 2  # PRD: retry maksimal 2 kali sebelum declared failed

    for worker_name in plan:
        node_fn = WORKER_REGISTRY.get(worker_name)
        if node_fn is None:
            log.warning("Unknown worker '%s' in plan, skipping", worker_name)
            continue

        attempt = 0
        last_error: Optional[Exception] = None
        while attempt <= MAX_RETRIES:
            try:
                delta = node_fn(current)
                if delta:
                    current.update(delta)
                last_error = None
                break  # success
            except Exception as e:
                last_error = e
                attempt += 1
                retry_counts[worker_name] = attempt
                log.warning(
                    "Worker %s crashed (attempt %d/%d): %s",
                    worker_name, attempt, MAX_RETRIES + 1, e,
                )
                if attempt <= MAX_RETRIES:
                    # brief backoff before retry
                    import time as _t
                    _t.sleep(0.2 * attempt)

        if last_error is not None:
            # All retries exhausted — record as failed
            log.error("Worker %s permanently failed after %d attempts", worker_name, attempt)
            wo = dict(current.get("worker_outputs") or {})
            wo[worker_name] = {
                "worker": worker_name, "status": "failed",
                "summary": f"crashed after {attempt} attempts: {last_error}",
                "data": {}, "tools_used": [], "error": str(last_error),
                "confidence": 0.0,
            }
            current["worker_outputs"] = wo
            errors = list(current.get("errors") or [])
            errors.append(f"{worker_name}: {last_error}")
            current["errors"] = errors

    current["retry_count"] = retry_counts

    # Post-execution tool policy validation (PRD §12 Tool Permission Matrix)
    # For each worker output, verify that every tool it claims to have used
    # is in the worker's allow-list. Violations are logged + flagged.
    policy_violations: List[str] = []
    for wname, wout in (current.get("worker_outputs") or {}).items():
        for tool in (wout.get("tools_used") or []):
            if not enforce_tool_policy(wname, tool, TOOL_POLICY):
                policy_violations.append(f"{wname} used forbidden tool {tool}")
                # Tag the worker output so the composer can mention it
                wout["policy_violation"] = True
    if policy_violations:
        errs = list(current.get("errors") or [])
        errs.extend(policy_violations)
        current["errors"] = errs
        log.warning("Tool policy violations: %s", policy_violations)

    # Return only the deltas we care about
    return {
        "worker_outputs": current.get("worker_outputs") or {},
        "approval_required": bool(current.get("approval_required")),
        "relevant_policies": current.get("relevant_policies") or [],
        "trace": current.get("trace") or [],
        "errors": current.get("errors") or [],
        "retry_count": current.get("retry_count") or {},
    }


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------
def build_bos_graph(checkpointer=None):
    """Compile and return the BOS LangGraph."""
    g = StateGraph(BrokerState)

    # Nodes
    g.add_node("ceo_classify", ceo_classify_node)
    g.add_node("ceo_general", ceo_general_node)
    g.add_node("ceo_clarify", ceo_clarify_node)
    g.add_node("operations_manager", operations_manager_node)
    g.add_node("compliance_manager", compliance_manager_node)
    g.add_node("portfolio_manager", portfolio_manager_node)
    g.add_node("fan_out_workers", fan_out_workers_node)
    g.add_node("request_approval", request_approval_node)
    g.add_node("compose_response", compose_response_node)

    # Edges: entry -> CEO
    g.add_edge(START, "ceo_classify")

    # CEO routes to one of: clarify, general, *manager
    g.add_conditional_edges(
        "ceo_classify",
        ceo_route,
        {
            "clarify": "ceo_clarify",
            "general": "ceo_general",
            "operations": "operations_manager",
            "compliance": "compliance_manager",
            "portfolio": "portfolio_manager",
        },
    )

    # Clarify / general terminate immediately
    g.add_edge("ceo_clarify", END)
    g.add_edge("ceo_general", END)

    # Managers -> fan-out workers
    g.add_edge("operations_manager", "fan_out_workers")
    g.add_edge("compliance_manager", "fan_out_workers")
    g.add_edge("portfolio_manager", "fan_out_workers")

    # After workers, branch on approval
    g.add_conditional_edges(
        "fan_out_workers",
        approval_router,
        {
            "needs_approval": "request_approval",
            "compose": "compose_response",
        },
    )

    # Approval interrupts then flows to composer on resume
    g.add_edge("request_approval", "compose_response")

    # Composer is the final step
    g.add_edge("compose_response", END)

    checkpointer = checkpointer or get_checkpointer()
    compiled = g.compile(
        checkpointer=checkpointer,
    )
    log.info("BOS graph compiled")
    return compiled


# Module-level lazy singleton
_compiled = None


def get_bos_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_bos_graph()
    return _compiled
