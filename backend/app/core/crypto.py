"""Symmetric encryption for stored secrets (OAuth refresh tokens, etc.).

Fernet (AES-128-CBC + HMAC) with a key derived from SECRET_KEY — no extra
key management for self-hosters, and rotating SECRET_KEY deliberately
invalidates stored provider tokens (reconnect is the recovery path).
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.exceptions import AuthenticationError


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.get_secret_value().encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise AuthenticationError(
            "Stored credential cannot be decrypted (SECRET_KEY changed?). Reconnect the provider."
        ) from exc
