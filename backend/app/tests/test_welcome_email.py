"""
tests/test_welcome_email.py
Welcome email contract: exactly one professional message per new account,
rendered from templates, sent only from the registration path, never blocking
or failing registration.

These tests run against the isolated temp DB from conftest.py and the
`memory` email backend — no real mail can leave the process.
"""
import logging
import re
import uuid
from email import policy
from email.parser import Parser

import pytest

from ..core.config import settings
from ..core.database import get_db
from ..core.plan import TRIAL_DAYS
from ..emails import render_welcome_email
from ..services import email_service


@pytest.fixture(autouse=True)
def _clean_outbox():
    email_service.reset_memory_outbox()
    yield
    email_service.reset_memory_outbox()


async def _register(client, email=None, password=None):
    email = email or f"{uuid.uuid4().hex[:12]}@example.com"
    password = password or "WelcomePass123!"
    return email, await client.post(
        "/auth/register", json={"email": email, "password": password}
    )


async def _sent_at(email: str):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT welcome_email_sent_at FROM users WHERE email = ?", (email,)
        )
        row = await cur.fetchone()
    return row["welcome_email_sent_at"] if row else None


@pytest.mark.asyncio
async def test_register_sends_exactly_one_welcome_email(test_client):
    email, response = await _register(test_client)
    assert response.status_code == 201, response.text
    body = response.json()
    # The response contract is unchanged.
    assert set(body) == {"access_token", "token_type", "user_id"}
    assert body["token_type"] == "bearer"

    sent = [item for item in email_service.MEMORY_OUTBOX if item["to"] == email]
    assert len(sent) == 1
    # Sent only after a successful send, exactly once.
    assert await _sent_at(email) is not None


@pytest.mark.asyncio
async def test_message_has_proper_multipart_and_headers():
    rendered = render_welcome_email(first_name=None, trial_days=TRIAL_DAYS)
    _, message = email_service.build_message(
        to="recipient@example.com",
        subject=rendered["subject"],
        html=rendered["html"],
        text=rendered["text"],
        reply_to=settings.resolved_reply_to,
    )

    assert message["Subject"] == (
        f"Welcome to {settings.app_name} – Your AI Journey Starts Here! 🚀"
    )
    assert message["To"] == "recipient@example.com"
    assert message["From"].startswith((settings.email_from_name or "BotBase"))
    assert message["Reply-To"] == settings.resolved_reply_to
    assert message["Date"]
    assert message["Message-ID"].startswith("<")

    parsed = Parser(policy=policy.default).parsestr(message.as_string())
    assert parsed.is_multipart()
    assert parsed.get_body(preferencelist=("plain",)).get_content_type() == "text/plain"
    assert parsed.get_body(preferencelist=("html",)).get_content_type() == "text/html"


@pytest.mark.asyncio
async def test_html_links_match_configured_urls_and_text_part():
    rendered = render_welcome_email(first_name=None, trial_days=TRIAL_DAYS)
    html, text = rendered["html"], rendered["text"]

    assert settings.resolved_docs_url in html
    assert settings.resolved_dashboard_url in html
    # Every href in the HTML also appears in the plain-text part.
    for href in re.findall(r'href="([^"]+)"', html):
        assert href in text, f"link {href!r} missing from the text part"
    # No unrendered placeholders or Python Nones anywhere.
    for marker in ("{{", "}}", "{first_name}", "{BRAND}", "None"):
        assert marker not in html, f"unrendered marker {marker!r} in HTML"
        assert marker not in text, f"unrendered marker {marker!r} in text"


@pytest.mark.asyncio
async def test_logins_and_duplicate_registration_send_nothing(test_client):
    email, response = await _register(test_client)
    assert response.status_code == 201

    for _ in range(3):
        login = await test_client.post(
            "/auth/login", json={"email": email, "password": "WelcomePass123!"}
        )
        assert login.status_code == 200, login.text

    # Same address again: 400 and no extra email.
    duplicate = await test_client.post(
        "/auth/register", json={"email": email, "password": "WelcomePass123!"}
    )
    assert duplicate.status_code == 400

    sent = [item for item in email_service.MEMORY_OUTBOX if item["to"] == email]
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_pre_existing_users_receive_nothing(test_client):
    # Simulate an account created before this feature existed: the row exists
    # with welcome_email_sent_at NULL, and nothing may ever email it.
    legacy_email = f"legacy-{uuid.uuid4().hex[:8]}@example.com"
    async with get_db() as db:
        await db.execute(
            "INSERT INTO users (id, email, hashed_password, is_active, created_at, "
            "plan, trial_ends_at) VALUES (?, ?, ?, 1, ?, 'free', NULL)",
            (str(uuid.uuid4()), legacy_email, "not-a-hash", "2026-01-01T00:00:00+00:00"),
        )
        await db.commit()

    new_email, response = await _register(test_client)
    assert response.status_code == 201

    assert not [item for item in email_service.MEMORY_OUTBOX if item["to"] == legacy_email]
    sent = [item for item in email_service.MEMORY_OUTBOX if item["to"] == new_email]
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_mail_failure_never_blocks_registration(test_client, monkeypatch, caplog):
    email = f"failing-{uuid.uuid4().hex[:8]}@example.com"
    password = "WelcomePass123!"

    def boom(*args, **kwargs):
        raise email_service.EmailBackendError("mailbox unavailable")

    monkeypatch.setattr(email_service, "send_email", boom)
    with caplog.at_level(logging.INFO):
        response = await test_client.post(
            "/auth/register", json={"email": email, "password": password}
        )
    assert response.status_code == 201, response.text

    # The user can still sign in.
    login = await test_client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200, login.text

    # Not recorded, nothing sent, and the email pipeline itself logs nothing
    # sensitive. (aiosqlite's DEBUG SQL logging also sees the address — that
    # predates this feature — so scope the assertion to the mail loggers.)
    assert await _sent_at(email) is None
    mail_logs = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name.startswith(
            ("backend.app.emails", "backend.app.services.email_service")
        )
    )
    assert email not in mail_logs
    assert password not in mail_logs
    assert "AI Journey" not in mail_logs


@pytest.mark.asyncio
async def test_hostile_names_are_escaped():
    rendered = render_welcome_email(
        first_name='<script>alert(1)</script>', trial_days=TRIAL_DAYS
    )
    assert "<script>alert(1)</script>" not in rendered["html"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered["html"]
    # The plain-text part keeps the readable greeting.
    assert "Hello <script>alert(1)</script>," in rendered["text"]


@pytest.mark.asyncio
async def test_html_layout_constraints():
    rendered = render_welcome_email(first_name=None, trial_days=TRIAL_DAYS)
    html = rendered["html"]

    # Viewport meta for mobile clients.
    assert 'name="viewport"' in html
    # Container capped at 600px.
    assert "max-width: 600px" in html
    # No fixed width above 600px anywhere.
    for match in re.findall(r"width:\s*(\d+)px", html):
        assert int(match) <= 600, f"fixed width {match}px exceeds 600"
    # Bulletproof buttons carry a real text fallback.
    for anchor_text in ("Explore BotBase Documentation", "Open My BotBase Dashboard"):
        assert anchor_text in html
    # Hidden preheader is present.
    assert "display: none" in html and "mso-hide: all" in html


@pytest.mark.asyncio
async def test_trial_sentence_tracks_the_real_constant():
    rendered = render_welcome_email(first_name=None, trial_days=TRIAL_DAYS)
    expected = (
        f"Enjoy your {TRIAL_DAYS}-day free trial and explore the features "
        "available across our plans."
    )
    assert expected in rendered["text"]
    assert expected in rendered["html"]
    # The duration can only come from the product constant, never a hardcoded
    # "21-day" string baked into the templates.
    assert "21-day" not in _load_welcome_templates()

    without_trial = render_welcome_email(first_name=None, trial_days=None)
    assert "free trial" not in without_trial["text"]
    assert "free trial" not in without_trial["html"]


@pytest.mark.asyncio
async def test_console_backend_refuses_outside_debug(monkeypatch):
    monkeypatch.setattr(settings, "email_backend", "console")
    monkeypatch.setattr(settings, "debug", False)
    with pytest.raises(email_service.EmailBackendError):
        await email_service.send_email(
            to="x@example.com", subject="subject", html="<p>html</p>", text="text"
        )


def _load_welcome_templates() -> str:
    from pathlib import Path

    directory = Path(__file__).resolve().parents[1] / "emails"
    return (directory / "welcome.html").read_text() + (
        directory / "welcome.txt"
    ).read_text()
