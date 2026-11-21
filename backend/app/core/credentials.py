"""
core/credentials.py
Small wrapper around Fernet for credentials that must be stored reversibly
(IMAP passwords, OAuth refresh tokens). The key is derived from SECRET_KEY, so
rotating SECRET_KEY invalidates stored credentials and requires re-entering them
— the correct fail-closed behaviour.

Nothing in this module logs plaintext. Callers must never return decrypted
values through an API response.
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_json(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return _fernet().encrypt(raw).decode("ascii")


def decrypt_json(blob: str | None) -> dict[str, Any] | None:
    if not blob:
        return None
    try:
        raw = _fernet().decrypt(blob.encode("ascii"))
        value = json.loads(raw.decode("utf-8"))
        return value if isinstance(value, dict) else None
    except (InvalidToken, ValueError, TypeError):
        return None
