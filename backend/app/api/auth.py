"""
api/auth.py
User registration and login — issues JWT access tokens.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..core.auth import create_access_token, hash_password, verify_password
from ..core.database import get_db
from ..core.logging import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])


class AuthRequest(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(payload: AuthRequest):
    """Create a new user and return an access token."""
    async with get_db() as db:
        cur = await db.execute("SELECT id FROM users WHERE email = ?", (payload.email,))
        if await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO users (id, email, hashed_password, is_active, created_at) "
            "VALUES (?, ?, ?, 1, ?)",
            (user_id, payload.email, hash_password(payload.password), now),
        )
        await db.commit()

    log.info("User registered", user_id=user_id)
    access_token = create_access_token({"sub": user_id})
    return TokenResponse(access_token=access_token, user_id=user_id)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive an access token",
)
async def login(payload: AuthRequest):
    """Verify credentials and return an access token."""
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, hashed_password, is_active FROM users WHERE email = ?",
            (payload.email,),
        )
        row = await cur.fetchone()

    if row is None or not verify_password(payload.password, row["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    log.info("User logged in", user_id=row["id"])
    access_token = create_access_token({"sub": row["id"]})
    return TokenResponse(access_token=access_token, user_id=row["id"])
