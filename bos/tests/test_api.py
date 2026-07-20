"""API smoke tests using FastAPI TestClient.

These do not require a running server. They use the in-process TestClient
which boots the full FastAPI app.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app()
    # TestClient triggers lifespan startup
    with TestClient(app) as c:
        yield c


API_KEY = "bos-local-dev-key-CHANGE-ME"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


def test_admin_health(client):
    r = client.get("/api/admin/health", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


def test_admin_health_requires_api_key(client):
    r = client.get("/api/admin/health")
    assert r.status_code == 401


def test_admin_agents_topology(client):
    r = client.get("/api/admin/agents", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert "ceo" in body["topology"]
    assert "crm_worker" in body["workers"]


def test_admin_clients_returns_seed(client):
    r = client.get("/api/admin/clients", headers=HEADERS)
    assert r.status_code == 200
    assert len(r.json()["clients"]) >= 3


def test_admin_users_returns_demo_dir(client):
    r = client.get("/api/admin/users", headers=HEADERS)
    assert r.status_code == 200
    usernames = [u["username"] for u in r.json()["users"]]
    assert "advisor@bos.local" in usernames


def test_approvals_list(client):
    r = client.get("/api/approvals", headers=HEADERS)
    assert r.status_code == 200
    assert "approvals" in r.json()


def test_chat_endpoint_requires_auth(client):
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 401


def test_chat_endpoint_completes_with_fallback(client):
    """Even if the LLM is unavailable, the chat endpoint must return a 200
    response composed from the rule-based fallback path."""
    with patch("app.agents.base.chat", side_effect=Exception("no llm")), \
         patch("app.agents.base.chat_json", side_effect=Exception("no llm")):
        r = client.post(
            "/api/chat",
            headers=HEADERS,
            json={"message": "Show my recent clients", "username": "advisor@bos.local"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["manager"] == "operations"
    assert body["final_response"]
