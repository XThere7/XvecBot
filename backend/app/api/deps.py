"""
api/deps.py
Shared FastAPI dependencies — authentication, rate limiting, etc.
Imported by individual routers via Depends().
"""
from fastapi import Header, HTTPException, status

from ..core.auth import decode_token
from ..core.config import settings
from ..core.database import get_db
from ..core.logging import get_logger

log = get_logger(__name__)


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """
    Validate the X-API-Key request header.
    Returns the key on success; raises 401 on failure.

    In production, replace with JWT / OAuth2 as needed.
    """
    if x_api_key != settings.api_key:
        log.warning("Invalid API key attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return x_api_key


async def get_current_user(
    authorization: str = Header(None),
) -> dict:
    """
    Resolve the current user from an "Authorization: Bearer <jwt>" header.
    Returns the user row as a dict; raises 401 on any auth failure.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, email, hashed_password, is_active, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = await cur.fetchone()

    if row is None or not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return dict(row)
