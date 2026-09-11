"""
api/deps.py
Shared FastAPI dependencies — authentication, rate limiting, etc.
Imported by individual routers via Depends().
"""
from fastapi import Header, HTTPException, status

from ..core.config import settings
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
