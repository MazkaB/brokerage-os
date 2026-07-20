"""Unit tests for security layer (RBAC + PII masking + auth)."""
from __future__ import annotations

from app.security import (
    authenticate_api_key, authenticate_user, detect_pii,
    enforce_tool_policy, list_demo_users, mask_pii, redact, safe_dict,
    validate_agent_output,
)


# ---------------------------- Auth ----------------------------
def test_valid_api_key_returns_admin():
    ctx = authenticate_api_key("bos-local-dev-key-CHANGE-ME")
    assert ctx.is_authenticated
    assert ctx.role == "admin"
    assert ctx.has_permission("anything")


def test_invalid_api_key_returns_anonymous():
    ctx = authenticate_api_key("wrong-key")
    assert not ctx.is_authenticated
    assert not ctx.has_permission("client.read")


def test_demo_users_have_correct_roles():
    users = {u["username"]: u for u in list_demo_users()}
    assert users["advisor@bos.local"]["role"] == "advisor"
    assert users["compliance@bos.local"]["role"] == "compliance"
    assert users["admin@bos.local"]["role"] == "admin"


def test_compliance_role_has_approve_permission():
    ctx = authenticate_user("compliance@bos.local")
    assert ctx.has_permission("approval.approve")
    assert not ctx.has_permission("agent.override")


def test_manager_role_has_override_permission():
    ctx = authenticate_user("manager@bos.local")
    assert ctx.has_permission("agent.override")
    assert ctx.has_permission("approval.approve")


# ---------------------------- PII ----------------------------
def test_email_is_detected_and_masked():
    text = "Contact me at john.doe@example.com please."
    findings = detect_pii(text)
    assert any(f["type"] == "email" for f in findings)
    masked = mask_pii(text)
    assert "john.doe@example.com" not in masked
    assert "@example.com" in masked


def test_ssn_is_fully_masked():
    text = "My SSN is 123-45-6789."
    masked = mask_pii(text)
    assert "123-45-6789" not in masked
    assert "***-**-****" in masked


def test_phone_keeps_last_four():
    text = "Call +1-202-555-0143"
    masked = mask_pii(text)
    assert "0143" in masked
    assert "+1-202-555-0143" not in masked


def test_credit_card_masked():
    text = "Card 4111 1111 1111 1111"
    masked = mask_pii(text)
    assert "4111 1111 1111 1111" not in masked
    assert "1111" in masked  # last 4


def test_redact_does_not_leak_secret():
    out = redact("super-secret-api-key-12345")
    assert "super-secret" not in out
    assert out.startswith("redacted:")


def test_safe_dict_redacts_known_secret_keys():
    d = {"api_key": "abc", "user": "x", "nested": {"token": "t"}}
    out = safe_dict(d)
    assert out["api_key"].startswith("redacted:")
    assert out["user"] == "x"
    assert out["nested"]["token"].startswith("redacted:")


# ---------------------------- Tool policy ----------------------------
def test_tool_policy_allows_allowed_tool():
    policy = {"research_worker": {"allowed": ["research.security"], "forbidden": ["crm.update"]}}
    assert enforce_tool_policy("research_worker", "research.security", policy) is True


def test_tool_policy_blocks_forbidden_tool():
    policy = {"research_worker": {"allowed": ["research.security"], "forbidden": ["crm.update"]}}
    assert enforce_tool_policy("research_worker", "crm.update", policy) is False


def test_tool_policy_blocks_unlisted_tool():
    policy = {"research_worker": {"allowed": ["research.security"]}}
    assert enforce_tool_policy("research_worker", "calendar.schedule", policy) is False


# ---------------------------- Output validation ----------------------------
def test_validate_agent_output_returns_missing_keys():
    missing = validate_agent_output({"summary": "x"}, ["summary", "data", "confidence"])
    assert set(missing) == {"data", "confidence"}


def test_validate_agent_output_passes_when_complete():
    missing = validate_agent_output({"summary": "x", "data": {}, "confidence": 0.9},
                                    ["summary", "data", "confidence"])
    assert missing == []
