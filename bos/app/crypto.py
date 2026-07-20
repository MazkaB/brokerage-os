"""
AES-256 at-rest encryption with envelope pattern.

Two modes:
  * LOCAL (default for dev / single-host Phase 1): Fernet (AES-128-CBC + HMAC)
    keyed by a derived key from BOS_ENCRYPTION_KEY. Suitable when the host
    is trusted (e.g. laptop, single-tenant container).
  * GCP KMS (production): envelope encryption. Each plaintext gets a fresh
    data-encryption-key (DEK) generated locally, the DEK encrypts the
    plaintext with AES-256-GCM, and the DEK itself is wrapped by KMS.
    Set KMS_KEY_ID=projects/p/locations/l/keyRings/r/cryptoKeys/k to enable.

Public API:
  encrypt(plaintext: str|bytes) -> str    # returns "v1:<dek_b64>:<ct_b64>"
  decrypt(token: str) -> bytes
  is_encrypted(value: str) -> bool        # checks "v1:" prefix
  ensure_encrypted(value) -> str          # no-op if already encrypted

This lets us add at-rest protection to existing text columns (user_profile.notes,
audit.human_approval, attachment payloads) without schema migrations: the
stored value is a self-describing token.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
from typing import Optional, Union

from .config import get_settings

log = logging.getLogger("bos.crypto")

_VERSION = "v1"
_PREFIX = f"{_VERSION}:"


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------
def _kms_key_id() -> Optional[str]:
    return os.environ.get("KMS_KEY_ID")


def _local_key() -> bytes:
    """Derive a 32-byte Fernet-compatible key from BOS_ENCRYPTION_KEY."""
    settings = get_settings()
    seed = settings.encryption_key.encode("utf-8")
    digest = hashlib.sha256(seed).digest()
    return base64.urlsafe_b64encode(digest)


def is_encrypted(value: object) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


# ---------------------------------------------------------------------------
# LOCAL mode (Fernet) - always available, no external deps beyond cryptography
# ---------------------------------------------------------------------------
_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is None:
        from cryptography.fernet import Fernet
        _fernet = Fernet(_local_key())
    return _fernet


def _local_encrypt(plaintext: bytes) -> str:
    f = _get_fernet()
    ct = f.encrypt(plaintext)
    return f"{_PREFIX}local:{ct.decode('ascii')}"


def _local_decrypt(token: str) -> bytes:
    f = _get_fernet()
    body = token[len(f"{_PREFIX}local:"):]
    return f.decrypt(body.encode("ascii"))


# ---------------------------------------------------------------------------
# KMS mode (envelope encryption with AES-256-GCM)
# ---------------------------------------------------------------------------
def _aes_gcm_encrypt(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """AES-256-GCM. Returns nonce(12) + ciphertext + tag(16)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    return nonce + ct


def _aes_gcm_decrypt(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce, ct = blob[:12], blob[12:]
    return AESGCM(key).decrypt(nonce, ct, aad)


def _kms_encrypt(plaintext: bytes) -> str:
    """Envelope encryption using GCP KMS to wrap a per-record DEK."""
    try:
        from google.cloud import kms
    except ImportError as e:
        log.warning("google-cloud-kms not installed; falling back to local mode")
        return _local_encrypt(plaintext)

    key_id = _kms_key_id()
    client = kms.KeyManagementServiceClient()

    # 1. Generate fresh DEK locally (32 bytes = AES-256)
    dek = secrets.token_bytes(32)
    # 2. Encrypt the plaintext with the DEK (AES-256-GCM)
    ct = _aes_gcm_encrypt(dek, plaintext)
    # 3. Wrap the DEK with KMS
    wrapped = client.encrypt(
        request={"name": key_id, "plaintext": dek}
    ).ciphertext
    return (
        f"{_PREFIX}kms:"
        + base64.b64encode(wrapped).decode("ascii")
        + ":"
        + base64.b64encode(ct).decode("ascii")
    )


def _kms_decrypt(token: str) -> bytes:
    from google.cloud import kms
    key_id = _kms_key_id()
    client = kms.KeyManagementServiceClient()
    body = token[len(f"{_PREFIX}kms:"):]
    wrapped_b64, ct_b64 = body.split(":", 1)
    wrapped = base64.b64decode(wrapped_b64)
    ct = base64.b64decode(ct_b64)
    # 1. Unwrap the DEK
    dek = client.decrypt(request={"name": key_id, "ciphertext": wrapped}).plaintext
    # 2. Decrypt the ciphertext
    return _aes_gcm_decrypt(dek, ct)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def encrypt(plaintext: Union[str, bytes, None]) -> Optional[str]:
    """Encrypt plaintext, returning a self-describing token. None-safe."""
    if plaintext is None:
        return None
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    if _kms_key_id():
        try:
            return _kms_encrypt(plaintext)
        except Exception as e:
            log.warning("KMS encrypt failed (%s); falling back to local", e)
            return _local_encrypt(plaintext)
    return _local_encrypt(plaintext)


def decrypt(token: Union[str, bytes, None]) -> Optional[bytes]:
    """Decrypt a token produced by `encrypt`. None-safe."""
    if token is None:
        return None
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    if not token.startswith(_PREFIX):
        # Already plaintext (e.g. legacy data) - return as-is bytes
        return token.encode("utf-8")
    if token.startswith(f"{_PREFIX}local:"):
        return _local_decrypt(token)
    if token.startswith(f"{_PREFIX}kms:"):
        return _kms_decrypt(token)
    raise ValueError(f"unknown encryption token format: {token[:20]}...")


def decrypt_str(token: Union[str, bytes, None]) -> Optional[str]:
    """Like decrypt() but returns str."""
    out = decrypt(token)
    return out.decode("utf-8") if out is not None else None


def ensure_encrypted(value: Union[str, None]) -> Optional[str]:
    """Idempotent encrypt: no-op if already encrypted."""
    if value is None or is_encrypted(value):
        return value
    return encrypt(value)
