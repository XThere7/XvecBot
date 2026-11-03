"""
core/totp.py
RFC 6238 TOTP with only the standard library (hmac / base64 / hashlib /
struct / secrets / time), plus Fernet encryption of the stored secret.

Security properties
-------------------
  * Secrets are generated with ``secrets.token_bytes(20)`` (160 bits) and
    stored Fernet-encrypted with a key derived from ``SECRET_KEY`` — so a DB
    leak alone does not expose the seeds, and rotating the app secret
    invalidates stored seeds (acceptable: admins re-enroll).
  * Recovery codes are 10 random groups of 10 characters; only SHA-256 hashes
    are stored, so a DB leak cannot replay them.
  * Verification accepts a ±1 step window and enforces a per-account attempt
    rate limit in the caller (auth routes).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time

from cryptography.fernet import Fernet, InvalidToken

from .config import settings

_WINDOW = 1  # accept one 30-second step of skew in either direction


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def generate_secret() -> str:
    """Return a base32 TOTP secret (no padding, uppercase)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_secret(encrypted: str) -> str | None:
    try:
        return _fernet().decrypt(encrypted.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def provisioning_uri(secret: str, email: str) -> str:
    """otpauth:// URI used for the QR code (rendered with qrcode[pil])."""
    issuer = (settings.app_name or "BotBase").replace(" ", "%20")
    label = email.replace("@", "%40")
    return f"otpauth://totp/{issuer}:{label}?secret={secret}&issuer={issuer}"


def _hmac_digest(secret: str, counter: int) -> bytes:
    key = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8))
    message = struct.pack(">Q", counter)
    return hmac.new(key, message, hashlib.sha1).digest()


def code_at(secret: str, timestamp: int) -> str:
    """6-digit code for the given unix timestamp (seconds)."""
    counter = timestamp // 30
    digest = _hmac_digest(secret, counter)
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{binary % 1_000_000:06d}"


def verify_code(secret: str, code: str) -> bool:
    """Constant-ish comparison against the current step and ±1 window."""
    code = (code or "").strip()
    if not code.isdigit() or len(code) != 6:
        return False
    now = int(time.time())
    expected = [code_at(secret, now + step * 30) for step in (-1, 0, 1)]
    return any(hmac.compare_digest(code, candidate) for candidate in expected)


def generate_recovery_codes(count: int = 10) -> tuple[list[str], list[str]]:
    """Return (plain codes, their SHA-256 hashes). Only hashes are stored."""
    plain = [
        f"{secrets.token_urlsafe(9).replace('-', 'X').replace('_', 'Y')[:10]}"
        for _ in range(count)
    ]
    hashes = [hashlib.sha256(code.encode("utf-8")).hexdigest() for code in plain]
    return plain, hashes


def match_recovery_code(candidate: str, stored_hashes_json: str | None) -> bool:
    """True when the candidate matches an unused stored code hash."""
    import json

    if not stored_hashes_json:
        return False
    try:
        hashes: list[str] = json.loads(stored_hashes_json)
    except (ValueError, TypeError):
        return False
    digest = hashlib.sha256((candidate or "").strip().encode("utf-8")).hexdigest()
    return digest in hashes


def consume_recovery_code(
    candidate: str, stored_hashes_json: str | None
) -> tuple[bool, str | None]:
    """Match and remove the used code. Returns (matched, updated_json)."""
    import json

    if not stored_hashes_json:
        return False, stored_hashes_json
    try:
        hashes: list[str] = json.loads(stored_hashes_json)
    except (ValueError, TypeError):
        return False, stored_hashes_json
    digest = hashlib.sha256((candidate or "").strip().encode("utf-8")).hexdigest()
    if digest not in hashes:
        return False, stored_hashes_json
    hashes.remove(digest)
    return True, json.dumps(hashes)
