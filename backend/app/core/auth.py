"""
core/auth.py
JWT and password utilities — bcrypt hashing, token signing/decoding.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings
from .logging import get_logger

log = get_logger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expire_days: float | None = None) -> str:
    """
    Sign a JWT with the given payload, expiring per ACCESS_TOKEN_EXPIRE_DAYS
    (or ``expire_days``, used for shorter admin sessions).

    Every token carries an ``iat`` claim so ``get_current_user`` can reject
    sessions issued before the account's last password reset (see
    ``users.password_changed_at``). Tokens created before this feature shipped
    have no ``iat`` and are treated as still-valid — deploying this change
    never logs out an existing user.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    days = settings.ACCESS_TOKEN_EXPIRE_DAYS if expire_days is None else expire_days
    to_encode.update({"exp": now + timedelta(days=days), "iat": now})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT.
    Returns the payload dict, or None on any error (expired, bad signature, malformed).
    """
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        log.debug("Token decode failed", error=str(exc))
        return None
