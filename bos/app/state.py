"""
Global LangGraph state schema for the Brokerage OS.

This is the single source of truth that flows through every node in the
hierarchical graph (CEO -> Manager -> Worker). It is intentionally explicit
so the engineer reading this can immediately tell what data is available
at any node.
"""
from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional

# typing_extensions.TypedDict is required for Python < 3.12 (pydantic + langgraph).
from typing_extensions import TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


# ---------------------------------------------------------------------------
# Worker-level contracts (FR4 + Agent Contracts from the PRD)
# Each worker agent returns a dict shaped like these.
# ---------------------------------------------------------------------------
class WorkerResult(TypedDict, total=False):
    worker: str
    status: Literal["success", "failed", "skipped"]
    summary: str
    data: Dict[str, Any]
    confidence: float
    citations: List[str]
    tools_used: List[str]
    error: Optional[str]


# ---------------------------------------------------------------------------
# Approval record stored in state during HITL
# ---------------------------------------------------------------------------
class ApprovalRecord(TypedDict, total=False):
    approval_id: str
    intent: str
    summary: str
    requested_by: str
    requested_at: float
    decided_by: Optional[str]
    decided_at: Optional[float]
    decision: Optional[Literal["approved", "rejected", "expired"]]
    note: Optional[str]


# ---------------------------------------------------------------------------
# Top-level state (BrokerState) - the global state of the LangGraph.
# ---------------------------------------------------------------------------
class BrokerState(TypedDict, total=False):
    """Global state threaded through every node of the BOS graph."""

    # --- Conversation ---
    messages: Annotated[List[AnyMessage], add_messages]
    user_message: str                       # latest raw user message
    thread_id: str

    # --- Identity ---
    user_id: str
    username: str
    role: str
    permissions: List[str]

    # --- CEO layer ---
    intent: Optional[str]
    intent_confidence: float
    intent_needs_clarification: bool
    clarification_question: Optional[str]
    manager: Optional[str]                  # 'operations' | 'compliance' | 'portfolio' | 'clarify'

    # --- Manager layer ---
    worker_plan: List[str]                  # list of worker names to execute in parallel
    active_manager: Optional[str]

    # --- Worker layer ---
    worker_outputs: Dict[str, WorkerResult]  # key: worker name
    worker_errors: Dict[str, str]
    retry_count: Dict[str, int]

    # --- Approval / HITL ---
    approval_required: bool
    approval: Optional[ApprovalRecord]

    # --- Memory / context ---
    user_profile: Dict[str, Any]
    relevant_policies: List[Dict[str, Any]]
    short_term_summary: Optional[str]

    # --- Output ---
    final_response: Optional[str]
    citations: List[str]
    next_node: Optional[str]
    errors: List[str]
    trace: List[str]                        # human-readable sequence of visited nodes
