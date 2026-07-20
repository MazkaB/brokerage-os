"""
Security foundation for BOS Phase 1.

This module implements the security primitives required by the PRD:
  * API-key authentication for the messaging gateway
  * Role-Based Access Control (RBAC) matching section 14 of the PRD
  * PII detection & masking (section 15 - PII masking)
  * A simple secrets-management shim (so secrets never get logged)
  * Output validation utilities

NOTE (Phase 1 scope): Full AES-256 at rest, KMS, and HSM-backed key management
are explicitly Phase 2. For Phase 1 we use Fernet-style hashing, environment
variables for secrets, and structured logging that masks secrets in logs.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional

from .config import ROLE_PERMISSIONS, Settings, get_settings


# Insecure default values - the system warns at boot if these are still in use.
INSECURE_DEFAULTS = {
    "bos-local-dev-key-CHANGE-ME",
    "bos-local-jwt-secret-CHANGE-ME",
    "bos-local-encryption-key-32bytes",
}

log = logging.getLogger("bos.security")


# ---------------------------------------------------------------------------
# 1. Authentication
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AuthContext:
    """Represents the identity of a caller (human user or trusted service)."""

    user_id: str
    username: str
    role: str
    permissions: frozenset[str]
    is_authenticated: bool = True

    def has_permission(self, perm: str) -> bool:
        if "*" in self.permissions:
            return True
        return perm in self.permissions


def authenticate_api_key(api_key: str, settings: Optional[Settings] = None) -> AuthContext:
    """Authenticate a request using the static BOS_API_KEY.

    Returns an AuthContext as the `admin` role. For multi-user/multi-role
    scenarios use `authenticate_user` with an explicit user mapping.

    Uses `hmac.compare_digest` for constant-time comparison to prevent
    timing attacks (H1 in security audit).
    """
    settings = settings or get_settings()
    # Constant-time comparison to avoid timing oracle on API key recovery.
    if not api_key or not hmac.compare_digest(api_key, settings.api_key):
        return AuthContext(
            user_id="anonymous",
            username="anonymous",
            role="anonymous",
            permissions=frozenset(),
            is_authenticated=False,
        )
    return AuthContext(
        user_id="admin",
        username="admin",
        role="admin",
        permissions=frozenset(ROLE_PERMISSIONS["admin"]),
    )


# Pre-registered demo users for the local dashboard. Phase 1 uses an in-memory
# user directory; Phase 2 will move this to a managed identity provider.
_DEMO_USERS: Dict[str, Dict[str, Any]] = {
    "advisor@bos.local": {"user_id": "u_advisor", "username": "advisor", "role": "advisor"},
    "ops@bos.local": {"user_id": "u_ops", "username": "ops", "role": "operations"},
    "compliance@bos.local": {"user_id": "u_comp", "username": "compliance", "role": "compliance"},
    "manager@bos.local": {"user_id": "u_mgr", "username": "manager", "role": "manager"},
    "admin@bos.local": {"user_id": "u_admin", "username": "admin", "role": "admin"},
}


def authenticate_user(username: str, role: Optional[str] = None) -> AuthContext:
    """Authenticate by username.

    SECURITY: The `role` parameter is accepted ONLY for backwards compatibility
    and is **ignored** if it does not match the role configured for that user
    in `_DEMO_USERS`. This prevents the privilege-escalation exploit C2
    documented in SECURITY_AUDIT.md (an attacker passing `role="admin"` while
    impersonating `advisor@bos.local`).
    """
    user = _DEMO_USERS.get(username) if username else None
    if user is None:
        return AuthContext(
            user_id="anonymous",
            username=username or "anonymous",
            role="anonymous",
            permissions=frozenset(),
            is_authenticated=False,
        )
    # Only honour a role override if it matches the user's configured role.
    # (i.e. caller cannot escalate.)
    configured_role = user["role"]
    effective_role = configured_role
    if role is not None and role != configured_role:
        log.warning(
            "authenticate_user: rejected role override attempt "
            "(username=%s configured=%s requested=%s)",
            username, configured_role, role,
        )
    return AuthContext(
        user_id=user["user_id"],
        username=user["username"],
        role=effective_role,
        permissions=frozenset(ROLE_PERMISSIONS.get(effective_role, [])),
    )


def list_demo_users() -> List[Dict[str, str]]:
    return [
        {"username": u, "user_id": d["user_id"], "role": d["role"]}
        for u, d in _DEMO_USERS.items()
    ]


# ---------------------------------------------------------------------------
# 2. PII Detection & Masking
# ---------------------------------------------------------------------------
# Lightweight, deterministic, regex-based PII detection. Phase 2 will use a
# proper NER model. Patterns are conservative to minimize false positives in
# the brokerage domain.
_PII_PATTERNS: Dict[str, re.Pattern] = {
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "phone": re.compile(r"\b(?:\+?(\d{1,3}))?[-. (]*(\d{3})[-. )]*(\d{3})[-. ]*(\d{4})\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
    "account_number": re.compile(r"\bACCT[-\s]?\d{6,12}\b", re.IGNORECASE),
    "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}

# SSNs and credit card numbers get fully masked; emails and phones keep
# a hint for usability in the admin UI.
_MASK_POLICY = {
    "email": lambda m: m.group(0)[:2] + "***@" + m.group(0).split("@")[-1],
    "phone": lambda m: re.sub(r"\d", "*", m.group(0)[:-4]) + m.group(0)[-4:],
    "ssn": lambda m: "***-**-****",
    "credit_card": lambda m: "**** **** **** " + m.group(0)[-4:],
    "iban": lambda m: m.group(0)[:4] + "*" * (len(m.group(0)) - 8) + m.group(0)[-4:],
    "account_number": lambda m: "ACCT-" + ("*" * (len(m.group(0)) - 5)),
    "ip_address": lambda m: "***.***.***." + m.group(0).split(".")[-1],
}


def detect_pii(text: str) -> List[Dict[str, Any]]:
    """Return a list of detected PII occurrences (without masking them)."""
    findings = []
    for pii_type, pattern in _PII_PATTERNS.items():
        for match in pattern.finditer(text):
            findings.append(
                {
                    "type": pii_type,
                    "value": match.group(0),
                    "span": [match.start(), match.end()],
                }
            )
    return findings


def mask_pii(text: str) -> str:
    """Mask all detected PII in `text` using the masking policy."""
    masked = text
    for pii_type, pattern in _PII_PATTERNS.items():
        masked = pattern.sub(_MASK_POLICY[pii_type], masked)
    return masked


# ---------------------------------------------------------------------------
# 3. Secrets management shim
# ---------------------------------------------------------------------------
@lru_cache()
def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def redact(value: str) -> str:
    """Return a non-reversible short hash for safe logging of secret material."""
    if not value:
        return "<empty>"
    return f"redacted:{_hash_secret(value)}"


def safe_dict(d: Dict[str, Any], secret_keys: Iterable[str] = ()) -> Dict[str, Any]:
    """Return a copy of `d` with secret values redacted for logging."""
    secret_keys = set(secret_keys) | {
        "password", "api_key", "secret", "token", "encryption_key", "jwt_secret"
    }
    out = {}
    for k, v in d.items():
        if k.lower() in secret_keys or any(s in k.lower() for s in secret_keys):
            out[k] = redact(str(v)) if v else None
        elif isinstance(v, dict):
            out[k] = safe_dict(v, secret_keys)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# 4. Output validation
# ---------------------------------------------------------------------------
def validate_agent_output(output: Any, schema_keys: Iterable[str]) -> List[str]:
    """Ensure a worker agent output contains the expected contract keys.

    Returns a list of missing keys. Empty list means valid.
    """
    if not isinstance(output, dict):
        return ["<root: expected dict>"]
    expected = set(schema_keys)
    return [k for k in expected if k not in output]


def enforce_tool_policy(agent_name: str, tool_name: str, policy: Dict[str, List[str]]) -> bool:
    """Check whether an agent is permitted to invoke a tool given a policy matrix.

    `policy` shape: {"agent_name": {"allowed": [...], "forbidden": [...]}}
    """
    entry = policy.get(agent_name, {})
    forbidden = set(entry.get("forbidden", []))
    if tool_name in forbidden:
        log.warning("tool policy violation: agent=%s tool=%s is forbidden", agent_name, tool_name)
        return False
    allowed = entry.get("allowed")
    if allowed is None:
        return True
    if tool_name not in allowed:
        log.warning("tool policy violation: agent=%s tool=%s not in allow-list", agent_name, tool_name)
        return False
    return True
