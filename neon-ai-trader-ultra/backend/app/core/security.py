"""Security utilities: Fernet encryption at rest, PBKDF2 password hashing, signed tokens, masking."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken


def derive_fernet_key(raw_secret: str) -> bytes:
    """Derive a valid 32-byte url-safe base64 Fernet key from a configured secret."""
    digest = hashlib.sha256(raw_secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


class SecretVault:
    """Encrypts and decrypts broker credentials and sensitive values at rest."""

    def __init__(self, master_secret: str) -> None:
        key = derive_fernet_key(master_secret)
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return ""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Failed to decrypt secret: invalid key or corrupted payload") from exc


def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256."""
    actual_salt = salt or secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        actual_salt.encode("utf-8"),
        200_000,
    ).hex()
    return f"pbkdf2_sha256${actual_salt}${derived}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored PBKDF2-HMAC-SHA256 hash."""
    parts = stored_hash.split("$")
    if len(parts) != 3 or parts[0] != "pbkdf2_sha256":
        return False
    _, salt, expected_hex = parts
    candidate = hash_password(password, salt=salt).split("$")[2]
    return hmac.compare_digest(candidate, expected_hex)


def create_access_token(
    subject: str,
    role: str,
    secret_key: str,
    expires_in_seconds: int = 3600 * 8,
) -> str:
    """Create a compact HMAC-SHA256 signed JWT-compatible token."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + expires_in_seconds,
        "jti": secrets.token_hex(8),
    }
    h_b64 = base64.urlsafe_b64encode(json.dumps(header, separators=(",", ":")).encode()).rstrip(b"=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    signing_input = h_b64 + b"." + p_b64
    sig = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    s_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=")
    return f"{h_b64.decode()}.{p_b64.decode()}.{s_b64.decode()}"


def verify_access_token(token: str, secret_key: str) -> Dict[str, Any]:
    """Validate signature and expiration of an access token."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed access token")
    h_b64, p_b64, s_b64 = parts
    signing_input = f"{h_b64}.{p_b64}".encode("utf-8")
    expected_sig = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    expected_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode("utf-8")
    if not hmac.compare_digest(s_b64, expected_b64):
        raise ValueError("Invalid token signature")
    padded = p_b64 + "=" * (-len(p_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Token expired")
    return payload


def mask_account_id(account_id: str) -> str:
    """Safely mask account identifiers for UI and logs (e.g., ****4821)."""
    if not account_id:
        return "UNCONFIGURED"
    clean = str(account_id).strip()
    if len(clean) <= 4:
        return "*" * len(clean)
    return f"{'*' * max(4, len(clean) - 4)}{clean[-4:]}"


_SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key|api[_-]?secret|password|token|secret)\s*[:=]\s*[^\s,;]+", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    """Ensure credentials never leak into logs or notification payloads."""
    sanitized = text
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub(lambda m: f"{m.group(1)}=[REDACTED]", sanitized)
    return sanitized
