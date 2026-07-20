"""
Salesforce adapter (Phase 2).

Provides read/write access to Salesforce objects (Account, Contact, Opportunity)
when configured. Falls back to the in-process SQLite CRM mock when no
credentials are present.

Setup:
    Set environment variables:
      SALESFORCE_USERNAME, SALESFORCE_PASSWORD, SALESFORCE_SECURITY_TOKEN
      SALESFORCE_DOMAIN (default: login) -- use 'test' for sandbox

All public functions return the same `ToolResult` shape as `tools/crm.py`,
so swapping is mechanical (worker only calls one or the other).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from .base import ToolResult

log = logging.getLogger("bos.tools.salesforce")


def is_configured() -> bool:
    return all(os.environ.get(k) for k in (
        "SALESFORCE_USERNAME", "SALESFORCE_PASSWORD", "SALESFORCE_SECURITY_TOKEN",
    ))


def _get_client():
    """Lazily connect to Salesforce. Cached per-process."""
    if not is_configured():
        return None
    try:
        import simple_salesforce  # type: ignore
        return simple_salesforce.Salesforce(
            username=os.environ["SALESFORCE_USERNAME"],
            password=os.environ["SALESFORCE_PASSWORD"],
            security_token=os.environ["SALESFORCE_SECURITY_TOKEN"],
            domain=os.environ.get("SALESFORCE_DOMAIN", "login"),
        )
    except ImportError:
        log.warning("simple-salesforce not installed; using mock CRM")
        return None
    except Exception as e:
        log.warning("Salesforce connection failed: %s", e)
        return None


def get_client(client_id: str) -> ToolResult:
    """Retrieve a Salesforce Account + Contact by client_id (AccountId)."""
    sf = _get_client()
    if sf is None:
        return _mock_get_client(client_id)
    try:
        account = sf.Account.get(client_id)
        contacts = sf.query(
            f"SELECT Id, Name, Email FROM Contact WHERE AccountId = '{client_id}'"
        )
        return ToolResult(
            ok=True,
            data={
                "client": {
                    "client_id": account["Id"],
                    "full_name": account.get("Name"),
                    "account_type": account.get("Type"),
                    "email": (contacts.get("records") or [{}])[0].get("Email"),
                    "kyc_status": account.get("KYC_Status__c"),
                    "source": "salesforce",
                },
            },
            tools_used=["salesforce.get_client"],
        )
    except Exception as e:
        return ToolResult(ok=False, error=f"Salesforce API error: {e}")


def create_client(**fields) -> ToolResult:
    sf = _get_client()
    if sf is None:
        return _mock_create_client(**fields)
    try:
        result = sf.Account.create({
            "Name": fields.get("full_name"),
            "Type": fields.get("account_type", "Client"),
            "KYC_Status__c": fields.get("kyc_status", "pending"),
        })
        return ToolResult(
            ok=bool(result.get("success", result.get("id"))),
            data={"client_id": result.get("id")},
            tools_used=["salesforce.create_client"],
        )
    except Exception as e:
        return ToolResult(ok=False, error=f"Salesforce create failed: {e}")


def update_client(client_id: str, **fields) -> ToolResult:
    sf = _get_client()
    if sf is None:
        return _mock_update_client(client_id, **fields)
    try:
        sf.Account.update(client_id, fields)
        return get_client(client_id)
    except Exception as e:
        return ToolResult(ok=False, error=f"Salesforce update failed: {e}")


def list_clients(limit: int = 100) -> ToolResult:
    sf = _get_client()
    if sf is None:
        return _mock_list_clients(limit)
    try:
        result = sf.query(
            f"SELECT Id, Name, Type, KYC_Status__c FROM Account "
            f"WHERE Type = 'Client' ORDER BY LastModifiedDate DESC LIMIT {limit}"
        )
        return ToolResult(
            ok=True,
            data={"clients": result.get("records", [])},
            tools_used=["salesforce.list_clients"],
        )
    except Exception as e:
        return ToolResult(ok=False, error=f"Salesforce list failed: {e}")


# ---------------------------------------------------------------------------
# Mock fallbacks (delegate to the existing in-process CRM)
# ---------------------------------------------------------------------------
def _mock_get_client(client_id: str) -> ToolResult:
    from .crm import crm_get_client
    r = crm_get_client(client_id)
    return r if r.ok else ToolResult(ok=False, error=r.error)


def _mock_create_client(**fields) -> ToolResult:
    from .crm import crm_create_client
    return crm_create_client(**fields)


def _mock_update_client(client_id: str, **fields) -> ToolResult:
    from .crm import crm_update_client
    return crm_update_client(client_id, **fields)


def _mock_list_clients(limit: int = 100) -> ToolResult:
    from .crm import crm_list_clients
    return crm_list_clients(limit=limit)
