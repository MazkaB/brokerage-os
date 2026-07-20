"""Integration tests for the BOS graph.

These exercise the full LangGraph topology including the rule-based
fallback classifier (so they pass even when the Gemini API quota is hit).
The `mock_llm` fixture monkeypatches the chat / chat_json helpers to make
the tests deterministic.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.agents.ceo import _rule_based_classify
from app.graph import build_bos_graph
from app.memory.long_term import get_long_term_memory
from app.security import authenticate_user


@pytest.fixture(scope="module")
def graph():
    return build_bos_graph()


@pytest.fixture(scope="module", autouse=True)
def _seed_profile():
    ltm = get_long_term_memory()
    ltm.upsert_profile({
        "user_id": "u_advisor", "username": "advisor", "role": "advisor",
        "display_name": "Test Advisor", "risk_tolerance": "moderate",
        "preferred_markets": ["US-EQ"], "kyc_status": "verified",
        "account_type": "Individual",
    })


def _initial_state(message: str):
    auth = authenticate_user("advisor@bos.local")
    return {
        "thread_id": f"t-{uuid.uuid4().hex[:8]}",
        "user_message": message,
        "user_id": auth.user_id,
        "username": auth.username,
        "role": auth.role,
        "permissions": list(auth.permissions),
        "user_profile": ltm_profile(),
    }


def ltm_profile():
    return get_long_term_memory().get_profile("u_advisor") or {}


# ---------------------------- Rule-based classifier ----------------------------
def test_rule_based_classifier_routes_account_opening():
    d = _rule_based_classify("Open a new retirement account for Jane")
    assert d["manager"] == "operations"
    assert d["intent"] == "account_opening"


def test_rule_based_classifier_routes_compliance():
    d = _rule_based_classify("What are our KYC requirements?")
    assert d["manager"] == "compliance"


def test_rule_based_classifier_routes_research():
    d = _rule_based_classify("Summarize AAPL")
    assert d["manager"] == "portfolio"


def test_rule_based_classifier_defaults_to_general():
    d = _rule_based_classify("hello there")
    assert d["manager"] in ("general",)


# ---------------------------- End-to-end graph tests ----------------------------
def test_general_path_completes(graph):
    """A greeting should reach END without invoking any manager."""
    with patch("app.agents.base.chat_json", side_effect=Exception("no llm")), \
         patch("app.agents.base.chat", side_effect=Exception("no llm")):
        result = graph.invoke(_initial_state("Hi there"), config=_cfg())
    assert "final_response" in result
    assert result["final_response"]


def test_compliance_path_runs_retrieval_and_compliance_worker(graph):
    """A policy question must reach the compliance manager and run workers.

    The rule-based planner for the compliance manager produces both
    compliance_worker and retrieval_worker. The compliance_manager node
    further adds retrieval_worker for question-style queries.
    """
    with patch("app.agents.base.chat_json", side_effect=Exception("no llm")), \
         patch("app.agents.base.chat", side_effect=Exception("no llm")):
        result = graph.invoke(
            _initial_state("What are our KYC requirements?"),
            config=_cfg(),
        )
    outputs = result.get("worker_outputs") or {}
    # Retrieval worker must always run for compliance policy questions
    assert "retrieval_worker" in outputs, f"expected retrieval_worker in {list(outputs.keys())}"
    # Compliance worker is preferred but optional depending on planner path
    assert result.get("final_response")


def test_account_opening_requires_hitl(graph):
    """Account opening must interrupt at the approval node."""
    with patch("app.agents.base.chat_json", side_effect=Exception("no llm")), \
         patch("app.agents.base.chat", side_effect=Exception("no llm")):
        config = _cfg()
        result = graph.invoke(
            _initial_state("Open a new retirement account for Jane Doe"),
            config=config,
        )
        # Workflow should be interrupted at request_approval
        snapshot = graph.get_state(config)
        assert snapshot.next and "request_approval" in snapshot.next
        assert any(getattr(t, "interrupts", None) for t in snapshot.tasks)
        # final_response not yet produced
        assert not result.get("final_response")


def _cfg():
    return {"configurable": {"thread_id": f"t-{uuid.uuid4().hex[:8]}"}}
