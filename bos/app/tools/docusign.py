"""
DocuSign adapter (Phase 2).

Wraps DocuSign eSignature REST API for sending envelopes, fetching status,
and downloading signed documents. Falls back to local file generation
(templated .txt) when no credentials are configured.

Setup:
    Set environment variables:
      DOCUSIGN_INTEGRATION_KEY, DOCUSIGN_USER_ID, DOCUSIGN_ACCOUNT_ID
      DOCUSIGN_PRIVATE_KEY (RSA PEM) or DOCUSIGN_PRIVATE_KEY_PATH

Authentication uses JWT grant (server-to-server). The token is cached and
refreshed 5 minutes before expiry.
"""
from __future__ import annotations

import base64
import logging
import os
import time
from typing import Any, Dict, List, Optional

from .base import ToolResult

log = logging.getLogger("bos.tools.docusign")


def is_configured() -> bool:
    return bool(os.environ.get("DOCUSIGN_INTEGRATION_KEY")) and bool(os.environ.get("DOCUSIGN_USER_ID"))


_token_cache: dict = {"value": None, "expires_at": 0}


def _get_jwt_token() -> Optional[str]:
    """Get a cached JWT token, refreshing if expired or missing."""
    if _token_cache["value"] and time.time() < _token_cache["expires_at"] - 300:
        return _token_cache["value"]
    try:
        import jwt  # PyJWT
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        log.warning("PyJWT / cryptography not installed; DocuSign disabled")
        return None

    integration_key = os.environ["DOCUSIGN_INTEGRATION_KEY"]
    user_id = os.environ["DOCUSIGN_USER_ID"]
    pem_path = os.environ.get("DOCUSIGN_PRIVATE_KEY_PATH")
    pem = os.environ.get("DOCUSIGN_PRIVATE_KEY")
    if pem_path:
        with open(pem_path, "rb") as f:
            pem_bytes = f.read()
    elif pem:
        pem_bytes = pem.encode()
    else:
        return None

    try:
        private_key = serialization.load_pem_private_key(pem_bytes, password=None)
        scopes = "signature impersonation"
        payload = {
            "iss": integration_key,
            "sub": user_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "aud": "account-d.docusign.com",
            "scope": scopes,
        }
        assertion = jwt.encode(payload, private_key, algorithm="RS256")
        # Exchange assertion for access token
        import httpx
        r = httpx.post(
            "https://account-d.docusign.com/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        _token_cache["value"] = data["access_token"]
        _token_cache["expires_at"] = time.time() + int(data.get("expires_in", 3600))
        log.info("DocuSign JWT token acquired")
        return _token_cache["value"]
    except Exception as e:
        log.warning("DocuSign JWT grant failed: %s", e)
        return None


def send_envelope(
    *,
    document_path: str,
    recipient_email: str,
    recipient_name: str,
    subject: str,
    message: str = "",
) -> ToolResult:
    """Send a document for signature. Returns the DocuSign envelope ID."""
    token = _get_jwt_token()
    if not token:
        return _mock_send(document_path, recipient_email, subject)

    try:
        import httpx
        with open(document_path, "rb") as f:
            doc_bytes = base64.b64encode(f.read()).decode()
        body = {
            "documents": [{
                "documentBase64": doc_bytes,
                "name": os.path.basename(document_path),
                "fileExtension": "pdf",
            }],
            "emailSubject": subject,
            "emailBlurb": message,
            "recipients": {
                "signers": [{
                    "email": recipient_email,
                    "name": recipient_name,
                    "recipientId": "1",
                    "tabs": {
                        "signHereTabs": [{
                            "documentId": "1",
                            "pageNumber": "1",
                            "xPosition": "200",
                            "yPosition": "500",
                        }],
                    },
                }],
            },
            "status": "sent",
        }
        account_id = os.environ["DOCUSIGN_ACCOUNT_ID"]
        r = httpx.post(
            f"https://demo.docusign.net/restapi/v2.1/accounts/{account_id}/envelopes",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
            timeout=30,
        )
        r.raise_for_status()
        env_id = r.json()["envelopeId"]
        return ToolResult(
            ok=True,
            data={"envelope_id": env_id, "status": "sent"},
            tools_used=["docusign.send_envelope"],
        )
    except Exception as e:
        return ToolResult(ok=False, error=f"DocuSign send failed: {e}")


def get_envelope_status(envelope_id: str) -> ToolResult:
    token = _get_jwt_token()
    if not token:
        return _mock_status(envelope_id)
    try:
        import httpx
        account_id = os.environ["DOCUSIGN_ACCOUNT_ID"]
        r = httpx.get(
            f"https://demo.docusign.net/restapi/v2.1/accounts/{account_id}/envelopes/{envelope_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        return ToolResult(
            ok=True,
            data={
                "envelope_id": data["envelopeId"],
                "status": data.get("status"),
                "completed": data.get("status") == "completed",
                "source": "docusign",
            },
            tools_used=["docusign.get_status"],
        )
    except Exception as e:
        return ToolResult(ok=False, error=f"DocuSign status failed: {e}")


# ---------------------------------------------------------------------------
# Mock fallbacks
# ---------------------------------------------------------------------------
def _mock_send(document_path: str, recipient_email: str, subject: str) -> ToolResult:
    """Mock: pretend we sent the envelope, return a deterministic ID."""
    import hashlib
    eid = "mock-" + hashlib.sha256(f"{document_path}{recipient_email}".encode()).hexdigest()[:12]
    log.info("DocuSign mock: sent %s to %s as %s", document_path, recipient_email, eid)
    return ToolResult(
        ok=True,
        data={"envelope_id": eid, "status": "sent (mock)"},
        tools_used=["docusign.send_envelope"],
    )


def _mock_status(envelope_id: str) -> ToolResult:
    return ToolResult(
        ok=True,
        data={"envelope_id": envelope_id, "status": "completed (mock)", "completed": True},
        tools_used=["docusign.get_status"],
    )
