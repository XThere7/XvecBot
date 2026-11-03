"""
tests/test_password_reset.py
Self-service password recovery: neutral responses, single-use hashed tokens,
30-minute expiry, session invalidation, rate limiting, and email quality.

Runs on the isolated temp DB and the `memory` email backend — no real mail.
"""
import asyncio
import hashlib
import logging
import re
import uuid

import pytest

from ..core.config import settings
from ..core.database import get_db
from ..services import email_service, password_reset_service
from ..services.password_reset_service import FORGOT_RESPONSE

RESET_LINK_RE = re.compile(r"token=([A-Za-z0-9_\-]+)")
GENERIC_INVALID = "This reset link is invalid or has expired."


@pytest.fixture(autouse=True)
def _clean_state():
    email_service.reset_memory_outbox()
    password_reset_service.reset_rate_limit_state()
    yield
    email_service.reset_memory_outbox()
    password_reset_service.reset_rate_limit_state()


async def _register(client, email=None, password=None):
    email = email or f"{uuid.uuid4().hex[:12]}@example.com"
    password = password or "OldPassword123!"
    response = await client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert response.status_code == 201, response.text
    return email, password, response.json()


def _reset_email_for(email: str) -> dict | None:
    for item in email_service.MEMORY_OUTBOX:
        if item["to"] == email and item["subject"].startswith("Reset your"):
            return item
    return None


def _token_from(item: dict) -> str:
    match = RESET_LINK_RE.search(item["text"])
    assert match, f"no reset link in email: {item['text']!r}"
    return match.group(1)


async def _request_reset(client, email: str):
    return await client.post("/auth/forgot-password", json={"email": email})


@pytest.mark.asyncio
async def test_forgot_returns_neutral_body_and_sends_one_email(test_client):
    email, _, _ = await _register(test_client)
    response = await _request_reset(test_client, email)
    assert response.status_code == 200
    assert response.json() == FORGOT_RESPONSE

    item = _reset_email_for(email)
    assert item is not None
    assert settings.resolved_frontend_url in item["text"]
    assert len(
        [
            m
            for m in email_service.MEMORY_OUTBOX
            if m["to"] == email and m["subject"].startswith("Reset your")
        ]
    ) == 1


@pytest.mark.asyncio
async def test_unknown_email_same_body_and_no_mail(test_client):
    before = len(email_service.MEMORY_OUTBOX)
    response = await _request_reset(test_client, f"unknown-{uuid.uuid4().hex[:8]}@example.com")
    assert response.status_code == 200
    assert response.json() == FORGOT_RESPONSE
    assert len(email_service.MEMORY_OUTBOX) == before


@pytest.mark.asyncio
async def test_malformed_email_same_body_and_no_mail(test_client):
    before = len(email_service.MEMORY_OUTBOX)
    response = await _request_reset(test_client, "definitely-not-an-email")
    assert response.status_code == 200
    assert response.json() == FORGOT_RESPONSE
    assert len(email_service.MEMORY_OUTBOX) == before


@pytest.mark.asyncio
async def test_token_stored_hashed_only_with_30_minute_expiry(test_client):
    email, _, _ = await _register(test_client)
    await _request_reset(test_client, email)
    raw = _token_from(_reset_email_for(email))

    async with get_db() as db:
        cur = await db.execute(
            "SELECT t.token_hash, t.created_at, t.expires_at, t.used_at "
            "FROM password_reset_tokens t JOIN users u ON u.id = t.user_id "
            "WHERE u.email = ?",
            (email,),
        )
        rows = await cur.fetchall()

    assert len(rows) == 1
    row = rows[0]
    assert row["token_hash"] == hashlib.sha256(raw.encode()).hexdigest()
    assert raw not in row["token_hash"]
    assert raw not in " ".join(str(v) for v in dict(row).values())
    from datetime import datetime, timezone

    created = datetime.fromisoformat(row["created_at"])
    expires = datetime.fromisoformat(row["expires_at"])
    delta_minutes = (expires - created).total_seconds() / 60
    assert 29 <= delta_minutes <= 31
    assert delta_minutes == pytest.approx(settings.password_reset_token_ttl_minutes, abs=1)
    assert row["used_at"] is None
    assert created.tzinfo is not None


@pytest.mark.asyncio
async def test_reset_success_new_password_works_old_fails(test_client):
    email, old_password, _ = await _register(test_client)
    await _request_reset(test_client, email)
    token = _token_from(_reset_email_for(email))

    response = await test_client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "NewPassword123!"},
    )
    assert response.status_code == 200, response.text
    assert "reset" in response.json()["message"].lower()

    login_new = await test_client.post(
        "/auth/login", json={"email": email, "password": "NewPassword123!"}
    )
    assert login_new.status_code == 200
    login_old = await test_client.post(
        "/auth/login", json={"email": email, "password": old_password}
    )
    assert login_old.status_code == 401

    notices = [
        m for m in email_service.MEMORY_OUTBOX
        if m["to"] == email and "password was changed" in m["subject"].lower()
    ]
    assert len(notices) == 1


@pytest.mark.asyncio
async def test_token_reuse_rejected(test_client):
    email, _, _ = await _register(test_client)
    await _request_reset(test_client, email)
    token = _token_from(_reset_email_for(email))

    first = await test_client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "NewPassword123!"},
    )
    assert first.status_code == 200
    second = await test_client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "AnotherPassword123!"},
    )
    assert second.status_code == 400
    assert second.json()["detail"] == GENERIC_INVALID


@pytest.mark.asyncio
async def test_new_request_invalidates_earlier_link(test_client):
    email, _, _ = await _register(test_client)
    await _request_reset(test_client, email)
    first_token = _token_from(_reset_email_for(email))

    await _request_reset(test_client, email)
    reset_mails = [
        m
        for m in email_service.MEMORY_OUTBOX
        if m["to"] == email and m["subject"].startswith("Reset your")
    ]
    assert len(reset_mails) == 2
    second_token = _token_from(reset_mails[1])

    stale = await test_client.post(
        "/auth/reset-password",
        json={"token": first_token, "new_password": "NewPassword123!"},
    )
    assert stale.status_code == 400
    assert stale.json()["detail"] == GENERIC_INVALID

    fresh = await test_client.post(
        "/auth/reset-password",
        json={"token": second_token, "new_password": "NewPassword123!"},
    )
    assert fresh.status_code == 200


@pytest.mark.asyncio
async def test_expired_token_rejected(test_client):
    email, _, _ = await _register(test_client)
    await _request_reset(test_client, email)
    token = _token_from(_reset_email_for(email))

    from datetime import datetime, timedelta, timezone

    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    async with get_db() as db:
        await db.execute(
            "UPDATE password_reset_tokens SET expires_at = ?", (past,)
        )
        await db.commit()

    response = await test_client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "NewPassword123!"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == GENERIC_INVALID


@pytest.mark.asyncio
async def test_weak_and_mismatched_rejections_do_not_consume_token(test_client):
    email, _, _ = await _register(test_client)
    await _request_reset(test_client, email)
    token = _token_from(_reset_email_for(email))

    weak = await test_client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "short"},
    )
    assert weak.status_code == 422

    mismatch = await test_client.post(
        "/auth/reset-password",
        json={
            "token": token,
            "new_password": "NewPassword123!",
            "confirm_password": "DifferentPassword123!",
        },
    )
    assert mismatch.status_code == 400
    assert mismatch.json()["detail"] == "New passwords do not match."

    # The token survived both rejections.
    success = await test_client.post(
        "/auth/reset-password",
        json={
            "token": token,
            "new_password": "NewPassword123!",
            "confirm_password": "NewPassword123!",
        },
    )
    assert success.status_code == 200


@pytest.mark.asyncio
async def test_concurrent_use_only_one_succeeds(test_client):
    email, _, _ = await _register(test_client)
    await _request_reset(test_client, email)
    token = _token_from(_reset_email_for(email))

    async def attempt():
        return await test_client.post(
            "/auth/reset-password",
            json={"token": token, "new_password": "NewPassword123!"},
        )

    first, second = await asyncio.gather(attempt(), attempt())
    assert sorted([first.status_code, second.status_code]) == [200, 400]


@pytest.mark.asyncio
async def test_session_invalidation_after_reset(test_client):
    email, _, registered = await _register(test_client)
    other_email, _, _ = await _register(test_client)
    other_login = await test_client.post(
        "/auth/login", json={"email": other_email, "password": "OldPassword123!"}
    )
    other_token = other_login.json()["access_token"]

    login_before = await test_client.post(
        "/auth/login", json={"email": email, "password": "OldPassword123!"}
    )
    old_token = login_before.json()["access_token"]
    me_before = await test_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {old_token}"}
    )
    assert me_before.status_code == 200

    await _request_reset(test_client, email)
    token = _token_from(_reset_email_for(email))
    reset = await test_client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "NewPassword123!"},
    )
    assert reset.status_code == 200

    me_after = await test_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {old_token}"}
    )
    assert me_after.status_code == 401

    login_new = await test_client.post(
        "/auth/login", json={"email": email, "password": "NewPassword123!"}
    )
    assert login_new.status_code == 200

    # A user who did not reset keeps their session.
    me_other = await test_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert me_other.status_code == 200


@pytest.mark.asyncio
async def test_rate_limits_per_email(test_client, monkeypatch):
    monkeypatch.setattr(settings, "password_reset_max_per_email_per_hour", 2)
    monkeypatch.setattr(settings, "password_reset_max_per_ip_per_hour", 1000)
    password_reset_service.reset_rate_limit_state()

    email, _, _ = await _register(test_client)
    other_email, _, _ = await _register(test_client)

    assert (await _request_reset(test_client, email)).status_code == 200
    assert (await _request_reset(test_client, email)).status_code == 200
    limited = await _request_reset(test_client, email)
    assert limited.status_code == 429
    assert limited.json() == FORGOT_RESPONSE

    # A different address is not blocked by the first one's bucket.
    assert (await _request_reset(test_client, other_email)).status_code == 200


@pytest.mark.asyncio
async def test_token_cannot_change_another_user(test_client):
    email_a, _, _ = await _register(test_client)
    email_b, password_b, _ = await _register(test_client)

    await _request_reset(test_client, email_a)
    token_a = _token_from(_reset_email_for(email_a))

    response = await test_client.post(
        "/auth/reset-password",
        json={"token": token_a, "new_password": "Hijacked123!"},
    )
    assert response.status_code == 200  # changes A, obviously

    # B is untouched: old password still signs in.
    login_b = await test_client.post(
        "/auth/login", json={"email": email_b, "password": password_b}
    )
    assert login_b.status_code == 200


@pytest.mark.asyncio
async def test_tokens_and_passwords_never_reach_logs(test_client, caplog):
    email, password, _ = await _register(test_client)
    with caplog.at_level(logging.INFO):
        await _request_reset(test_client, email)
        raw = _token_from(_reset_email_for(email))
        await test_client.post(
            "/auth/reset-password",
            json={"token": raw, "new_password": "NewPassword123!"},
        )
    logs = caplog.text
    assert raw not in logs
    assert "reset-password?token=" not in logs
    assert password not in logs
    assert "NewPassword123!" not in logs


@pytest.mark.asyncio
async def test_reset_email_quality(test_client):
    email, _, _ = await _register(test_client)
    await _request_reset(test_client, email)
    item = _reset_email_for(email)

    assert settings.resolved_frontend_url in item["html"]
    hrefs = re.findall(r'href="([^"]+)"', item["html"])
    reset_hrefs = [h for h in hrefs if "reset-password?token=" in h]
    assert len(reset_hrefs) == 2  # button + plain link
    for href in reset_hrefs:
        assert href in item["text"]
    assert f"{settings.password_reset_token_ttl_minutes} minutes" in item["text"]
    assert "password has not changed" in item["text"].lower()
    assert "if you did not request" in item["text"].lower()
    for marker in ("{{", "}}", "{BRAND}", "None"):
        assert marker not in item["html"]
        assert marker not in item["text"]
    # No password material appears in the mail (this account's password).
    assert "OldPassword123!" not in item["text"]
    assert "OldPassword123!" not in item["html"]
