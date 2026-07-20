"""Unit tests for tools. These do NOT require Gemini (deterministic mocks)."""
from __future__ import annotations

from app.tools.calendar import cal_list_events, cal_schedule
from app.tools.compliance import comp_run_aml, comp_run_kyc, comp_validate_policy
from app.tools.crm import crm_create_client, crm_get_client, crm_list_clients
from app.tools.documents import doc_fill_form, doc_list, doc_prepare_pdf
from app.tools.research import research_compare_funds, research_market_news, research_security


# ---------------------------- CRM ----------------------------
def test_crm_seeds_demo_clients():
    r = crm_list_clients()
    assert r.ok
    assert len(r.data["clients"]) >= 3


def test_crm_get_existing_client():
    r = crm_get_client("C-1001")
    assert r.ok
    assert r.data["client"]["full_name"] == "Jane Doe"


def test_crm_get_missing_client_returns_not_found():
    r = crm_get_client("DOES-NOT-EXIST")
    assert not r.ok
    assert "not found" in r.error.lower()


def test_crm_create_then_get_client():
    r = crm_create_client(
        full_name="Test User", email="test@example.com",
        account_type="Individual", risk_tolerance="aggressive",
        preferred_markets=["US-EQ"],
    )
    assert r.ok
    cid = r.data["client_id"]
    g = crm_get_client(cid)
    assert g.ok
    assert g.data["client"]["email"] == "test@example.com"


# ---------------------------- Documents ----------------------------
def test_doc_prepare_account_opening():
    r = doc_prepare_pdf("account_opening", {
        "full_name": "Alice", "account_type": "Individual",
        "risk_tolerance": "moderate", "email": "a@b.c",
        "phone": "555-0100", "kyc_status": "verified",
    })
    assert r.ok
    assert r.data["doc_id"].startswith("DOC-")
    assert "Alice" in r.data["preview"]


def test_doc_prepare_unknown_template_fails():
    r = doc_prepare_pdf("does_not_exist", {})
    assert not r.ok


def test_doc_fill_form_roundtrip():
    r = doc_prepare_pdf("kyc_checklist", {
        "client_id": "C-9999", "reviewer": "compliance",
    })
    assert r.ok
    doc_id = r.data["doc_id"]
    r2 = doc_fill_form(doc_id, {"reviewer": "senior-officer"})
    assert r2.ok


# ---------------------------- Calendar ----------------------------
def test_calendar_schedule_and_list():
    r = cal_schedule(title="KYC Review", attendees=["a@b.c"])
    assert r.ok
    eid = r.data["event"]["event_id"]
    assert eid.startswith("EVT-")
    listing = cal_list_events()
    assert listing.ok
    assert any(e["event_id"] == eid for e in listing.data["events"])


# ---------------------------- Compliance ----------------------------
def test_kyc_passes_with_required_fields():
    r = comp_run_kyc({
        "full_name": "X", "gov_id": "id.pdf",
        "address_proof": "bill.pdf", "dob": "1990-01-01",
    })
    assert r.ok
    assert r.data["kyc_passed"] is True
    assert r.data["missing_fields"] == []


def test_kyc_fails_with_missing_fields():
    r = comp_run_kyc({"full_name": "X"})
    assert r.ok
    assert r.data["kyc_passed"] is False
    assert "gov_id" in r.data["missing_fields"]


def test_aml_low_risk_for_clean_client():
    r = comp_run_aml({"full_name": "Jane Doe", "country": "US"})
    assert r.ok
    assert r.data["aml_cleared"] is True
    assert r.data["risk_score"] < 0.5


def test_aml_flags_sanctioned_name():
    r = comp_run_aml({"full_name": "Bad Actor", "country": "US"})
    assert r.ok
    assert r.data["aml_cleared"] is False
    assert r.data["risk_score"] >= 0.5


def test_policy_blocks_account_opening_without_kyc():
    r = comp_validate_policy("account_opening", {"kyc_passed": False})
    assert r.ok
    assert r.data["allowed"] is False


def test_policy_requires_approval_for_account_opening_with_kyc():
    r = comp_validate_policy("account_opening", {"kyc_passed": True})
    assert r.ok
    assert r.data["allowed"] is True
    assert r.data["requires_human_approval"] is True


def test_policy_auto_approves_small_trade():
    r = comp_validate_policy("trade_execution", {
        "client": {"status": "active"}, "amount": 500,
    })
    assert r.ok
    assert r.data["allowed"] is True
    assert r.data["requires_human_approval"] is False


def test_policy_requires_approval_for_large_trade():
    r = comp_validate_policy("trade_execution", {
        "client": {"status": "active"}, "amount": 5000,
    })
    assert r.ok
    assert r.data["requires_human_approval"] is True


# ---------------------------- Research (deterministic) ----------------------------
def test_research_security_is_deterministic():
    a = research_security("AAPL").data
    b = research_security("AAPL").data
    assert a["price_usd"] == b["price_usd"]
    assert a["symbol"] == "AAPL"


def test_research_market_news_returns_headlines():
    r = research_market_news(topic="tech")
    assert r.ok
    assert len(r.data["news"]) > 0


def test_research_compare_funds():
    r = research_compare_funds(["Fund A", "Fund B"])
    assert r.ok
    assert len(r.data["funds"]) == 2
