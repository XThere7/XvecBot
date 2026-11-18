"""
api/auth.py
User registration and login — issues JWT access tokens.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..core.auth import create_access_token, hash_password, verify_password
from ..core.config import settings
from ..core.database import get_db
from ..core.logging import get_logger
from ..core.plan import (
    PLAN_PRICES_TZS,
    get_limits,
    get_trial_status,
    normalize_plan_id,
    trial_end_from,
)
from ..emails import deliver_welcome_email
from .deps import get_current_user

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])


class AuthRequest(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str


class TotpChallengeResponse(BaseModel):
    token_type: str = "totp"
    totp_token: str
    user_id: str


class TotpLoginRequest(BaseModel):
    totp_token: str = Field(..., min_length=1, max_length=1024)
    code: str = Field(..., min_length=1, max_length=32)


# In-process admin sign-in / TOTP attempt buckets (per-worker; see
# core/rate_limit.py for the scaling note). Keys: login:{email}, totp:{user_id}.
_auth_buckets: dict[str, list[float]] = {}
_LOGIN_WINDOW = 900.0
_TOTP_WINDOW = 900.0


def reset_admin_auth_buckets() -> None:
    """Clear the in-process sign-in/TOTP attempt buckets (tests)."""
    _auth_buckets.clear()


def _check_bucket(
    key: str, limit: int, window: float, *, consume: bool = True
) -> bool:
    import time as _time

    now = _time.monotonic()
    hits = [t for t in _auth_buckets.get(key, []) if now - t < window]
    if len(hits) >= max(1, limit):
        _auth_buckets[key] = hits
        return False
    if consume:
        hits.append(now)
        _auth_buckets[key] = hits
    else:
        _auth_buckets[key] = hits
    return True


def _totp_challenge_token(user_id: str) -> str:
    """Short-lived (5 minute) single-purpose token for the 2FA step."""
    from ..core.auth import create_access_token

    return create_access_token(
        {"sub": user_id, "type": "totp"}, expire_days=5 / (24 * 60)
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(payload: AuthRequest, background_tasks: BackgroundTasks):
    """Create a new user, enqueue the one-time welcome email, return a token."""
    async with get_db() as db:
        # Platform control: the master admin can close new sign-ups.
        from ..services import admin_service

        if not await admin_service.signups_open(db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="New sign-ups are currently closed.",
            )

        cur = await db.execute("SELECT id FROM users WHERE email = ?", (payload.email,))
        if await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        trial_ends_at = trial_end_from()
        await db.execute(
            "INSERT INTO users "
            "(id, email, hashed_password, is_active, created_at, plan, trial_ends_at) "
            "VALUES (?, ?, ?, 1, ?, 'free', ?)",
            (
                user_id,
                payload.email,
                hash_password(payload.password),
                now,
                trial_ends_at,
            ),
        )
        await db.commit()

    # Enqueue only after the row is committed. The task itself is best-effort:
    # a mail failure is caught and logged there, so registration always
    # returns the same success response at the same speed as before.
    background_tasks.add_task(deliver_welcome_email, user_id, payload.email)

    log.info("User registered", user_id=user_id)
    access_token = create_access_token({"sub": user_id})
    return TokenResponse(access_token=access_token, user_id=user_id)


@router.get(
    "/me",
    summary="Current user, effective plan, trial status and limits",
)
async def me(user: dict = Depends(get_current_user)):
    """Return the account view used by the dashboard and pricing page."""
    import json

    trial = get_trial_status(user)
    base_plan = normalize_plan_id(user.get("plan"))
    try:
        permissions = json.loads(user.get("permissions") or "[]")
        if not isinstance(permissions, list):
            permissions = []
    except ValueError:
        permissions = []
    return {
        "id": user["id"],
        "email": user["email"],
        "role": user.get("role") or "user",
        "permissions": permissions,
        "suspended_at": user.get("suspended_at"),
        "totp_enabled": bool(user.get("totp_enabled")),
        "plan": {
            "base": base_plan,
            "effective": trial["effective_plan"],
            "is_trial": trial["is_trial"],
            "trial_ends_at": trial["trial_ends_at"],
            "days_remaining": trial["days_remaining"],
            "price_tzs": PLAN_PRICES_TZS.get(base_plan, 0),
        },
        "limits": get_limits(user),
        "created_at": user.get("created_at"),
    }


@router.post(
    "/login",
    response_model=None,
    summary="Login and receive an access token (or a TOTP challenge)",
)
async def login(payload: AuthRequest):
    """Verify credentials and return an access token."""
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, email, hashed_password, is_active, suspended_at, "
            "role, totp_enabled FROM users WHERE email = ?",
            (payload.email,),
        )
        row = await cur.fetchone()

    role = (row["role"] or "user") if row is not None else "user"

    # Admin sign-in is rate limited per email per 15 minutes. The bucket is
    # consumed BEFORE password verification so wrong passwords count too;
    # checking it only after a successful password made brute force cheap.
    is_admin = row is not None and role in ("admin", "superadmin")
    bucket_key = f"login:{payload.email.lower()}"
    if is_admin:
        if not _check_bucket(
            bucket_key,
            settings.admin_login_max_per_email_per_15m,
            _LOGIN_WINDOW,
            consume=False,
        ):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many sign-in attempts. Try again later.",
            )

    invalid = (
        row is None
        or not verify_password(payload.password, row["hashed_password"])
        or not row["is_active"]
        or row["suspended_at"]
    )
    if invalid:
        # Count failures only; successful sign-ins must not consume the
        # bucket or a busy admin could lock themselves out.
        if is_admin:
            _check_bucket(
                bucket_key,
                settings.admin_login_max_per_email_per_15m,
                _LOGIN_WINDOW,
                consume=True,
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Two-factor authentication (TOTP) — admins and the superadmin only.
    if row["totp_enabled"]:
        return TotpChallengeResponse(
            totp_token=_totp_challenge_token(row["id"]), user_id=row["id"]
        )

    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?", (now, row["id"])
        )
        await db.commit()

    log.info("User logged in", user_id=row["id"])
    expire = (
        settings.admin_session_expire_hours / 24
        if role in ("admin", "superadmin")
        else None
    )
    access_token = create_access_token({"sub": row["id"]}, expire_days=expire)
    return TokenResponse(access_token=access_token, user_id=row["id"])


@router.post(
    "/login/totp",
    response_model=TokenResponse,
    summary="Complete an admin sign-in with a TOTP or recovery code",
)
async def login_totp(payload: TotpLoginRequest):
    """Verify the second factor and issue the (shorter) admin session."""
    from ..core.auth import decode_token
    from ..core import totp

    decoded = decode_token(payload.totp_token)
    if decoded is None or decoded.get("type") != "totp":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This sign-in attempt has expired. Start again.",
        )
    user_id = decoded.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This sign-in attempt has expired. Start again.",
        )

    if not _check_bucket(
        f"totp:{user_id}",
        settings.totp_max_attempts_per_15m,
        _TOTP_WINDOW,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification attempts. Try again later.",
        )

    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, email, totp_secret, totp_enabled, recovery_codes, "
            "is_active, suspended_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = await cur.fetchone()

    if row is None or not row["is_active"] or row["suspended_at"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    matched = False
    used_recovery = False
    recovery_json = row["recovery_codes"]
    if row["totp_enabled"]:
        secret = totp.decrypt_secret(row["totp_secret"]) if row["totp_secret"] else None
        if secret and totp.verify_code(secret, payload.code):
            matched = True
        elif totp.match_recovery_code(payload.code, recovery_json):
            matched = True
            used_recovery = True

    if not matched:
        async with get_db() as db:
            await db.execute(
                "UPDATE users SET totp_failed_count = totp_failed_count + 1, "
                "totp_failed_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), user_id),
            )
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid verification code.",
        )

    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        if used_recovery:
            _, updated = totp.consume_recovery_code(payload.code, recovery_json)
            await db.execute(
                "UPDATE users SET recovery_codes = ?, totp_failed_count = 0, "
                "totp_failed_at = NULL, last_login_at = ? WHERE id = ?",
                (updated, now, user_id),
            )
        else:
            await db.execute(
                "UPDATE users SET totp_failed_count = 0, totp_failed_at = NULL, "
                "last_login_at = ? WHERE id = ?",
                (now, user_id),
            )
        await db.commit()

    log.info("User logged in with 2FA", user_id=user_id)
    access_token = create_access_token(
        {"sub": user_id}, expire_days=settings.admin_session_expire_hours / 24
    )
    return TokenResponse(access_token=access_token, user_id=user_id)
