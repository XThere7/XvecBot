"""
app/emails — transactional email templates and delivery glue.

Templates live as files (welcome.html / welcome.txt) so copy stays reviewable
and no giant string literals sit in code. Rendering uses string.Template and
escapes every dynamic value for the HTML part; the plain-text part keeps the
same content and the same links, unescaped.

Delivery helpers live in services/email_service.py.
"""
from __future__ import annotations

import html as html_lib
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from ..core.config import settings
from ..core.database import get_db
from ..core.logging import get_logger
from ..core.plan import TRIAL_DAYS
from ..services import email_service

log = get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent

WELCOME_SUBJECT_TEMPLATE = "Welcome to {brand} – Your AI Journey Starts Here! 🚀"
RESET_SUBJECT_TEMPLATE = "Reset your {brand} password"
PASSWORD_CHANGED_SUBJECT_TEMPLATE = "Your {brand} password was changed"
TRIAL_LINE_TEMPLATE = (
    "Enjoy your {days}-day free trial and explore the features available "
    "across our plans."
)


def _load_template(name: str) -> str:
    return (_TEMPLATE_DIR / name).read_text(encoding="utf-8")


def _greeting(first_name: str | None) -> str:
    name = (first_name or "").strip()
    return f"Hello {name}," if name else "Hello,"


def render_welcome_email(
    *,
    first_name: str | None = None,
    trial_days: int | None = None,
) -> dict[str, str]:
    """
    Render the welcome email.

    ``first_name`` may be ``None`` (registration stores no name — the email
    greets with "Hello,") and is HTML-escaped so hostile names are inert.
    ``trial_days`` must come from ``core.plan.TRIAL_DAYS`` so the email can
    never disagree with the product; ``None`` omits the trial sentence.
    """
    brand = settings.app_name or "BotBase"
    dashboard_url = settings.resolved_dashboard_url
    docs_url = settings.resolved_docs_url
    support = settings.resolved_support_email

    trial_line = ""
    if trial_days:
        trial_line = TRIAL_LINE_TEMPLATE.format(days=int(trial_days))

    # Raw values for the subject and the plain-text part, escaped values for
    # the HTML part. The template must stay safe even for hostile names.
    raw: dict[str, str] = {
        "BRAND": brand,
        "GREETING": _greeting(first_name),
        "DOCS_URL": docs_url,
        "DASHBOARD_URL": dashboard_url,
        "SUPPORT": support,
        "SUPPORT_MAILTO": f"mailto:{support}",
        "TRIAL_LINE": trial_line,
    }
    escaped: dict[str, str] = {
        key: html_lib.escape(value) for key, value in raw.items()
    }

    html = Template(_load_template("welcome.html")).safe_substitute(escaped)
    text = Template(_load_template("welcome.txt")).safe_substitute(raw)

    return {
        "subject": WELCOME_SUBJECT_TEMPLATE.format(brand=brand),
        "html": html,
        "text": text,
    }


async def deliver_welcome_email(user_id: str, email: str) -> None:
    """
    Background task: send the welcome email exactly once, then record it.

    Called only from the registration path after the user row is committed.
    Any failure — including an unconfigured mailbox — is caught here so
    registration has already returned and can never be slowed down or failed
    by mail. ``welcome_email_sent_at`` is set only after a successful send and
    the UPDATE guard makes a retry a no-op.
    """
    message_id: str | None = None
    try:
        rendered = render_welcome_email(first_name=None, trial_days=TRIAL_DAYS)
        message_id = await email_service.send_email(
            to=email,
            subject=rendered["subject"],
            html=rendered["html"],
            text=rendered["text"],
            reply_to=settings.resolved_reply_to,
        )
    except Exception as exc:
        log.warning(
            "Welcome email skipped",
            user_id=user_id,
            outcome=type(exc).__name__,
        )
        return

    try:
        now = datetime.now(timezone.utc).isoformat()
        async with get_db() as db:
            await db.execute(
                "UPDATE users SET welcome_email_sent_at = ? "
                "WHERE id = ? AND welcome_email_sent_at IS NULL",
                (now, user_id),
            )
            await db.commit()
    except Exception as exc:
        log.warning(
            "Welcome email sent but not recorded",
            user_id=user_id,
            message_id=message_id,
            outcome=type(exc).__name__,
        )
        return

    log.info("Welcome email sent", user_id=user_id, message_id=message_id)


def _brand_values(**extra: str) -> dict[str, str]:
    brand = settings.app_name or "BotBase"
    support = settings.resolved_support_email
    return {
        "BRAND": brand,
        "GREETING": _greeting(None),
        "SUPPORT": support,
        "SUPPORT_MAILTO": f"mailto:{support}",
        **extra,
    }


def _render(template_prefix: str, raw: dict[str, str]) -> dict[str, str]:
    escaped = {key: html_lib.escape(value) for key, value in raw.items()}
    html = Template(_load_template(f"{template_prefix}.html")).safe_substitute(escaped)
    text = Template(_load_template(f"{template_prefix}.txt")).safe_substitute(raw)
    return {"html": html, "text": text}


def render_reset_email(
    reset_url: str, ttl_minutes: int | None = None
) -> dict[str, str]:
    """Render the password reset email. The URL carries the single-use token."""
    ttl = settings.password_reset_token_ttl_minutes if ttl_minutes is None else int(ttl_minutes)
    rendered = _render(
        "reset",
        _brand_values(RESET_URL=reset_url, TTL_MINUTES=str(ttl)),
    )
    return {
        "subject": RESET_SUBJECT_TEMPLATE.format(brand=settings.app_name or "BotBase"),
        **rendered,
    }


def render_password_changed_email() -> dict[str, str]:
    rendered = _render("password_changed", _brand_values())
    return {
        "subject": PASSWORD_CHANGED_SUBJECT_TEMPLATE.format(
            brand=settings.app_name or "BotBase"
        ),
        **rendered,
    }


async def deliver_password_reset_email(email: str, raw_token: str) -> None:
    """
    Send the reset link. The raw token exists only here and in the email;
    it is never logged — only the message id and a coarse outcome are.
    """
    reset_url = (
        f"{settings.resolved_frontend_url}/reset-password?token={raw_token}"
    )
    rendered = render_reset_email(reset_url)
    try:
        message_id = await email_service.send_email(
            to=email,
            subject=rendered["subject"],
            html=rendered["html"],
            text=rendered["text"],
            reply_to=settings.resolved_reply_to,
        )
    except Exception as exc:
        log.warning("Password reset email skipped", outcome=type(exc).__name__)
        return
    log.info("Password reset email sent", message_id=message_id)


async def deliver_password_changed_notice(email: str) -> None:
    """Notify the owner after a successful reset so a hijack is visible."""
    rendered = render_password_changed_email()
    try:
        message_id = await email_service.send_email(
            to=email,
            subject=rendered["subject"],
            html=rendered["html"],
            text=rendered["text"],
            reply_to=settings.resolved_reply_to,
        )
    except Exception as exc:
        log.warning("Password changed notice skipped", outcome=type(exc).__name__)
        return
    log.info("Password changed notice sent", message_id=message_id)


def render_admin_invite_email(
    setup_url: str, ttl_minutes: int | None = None
) -> dict[str, str]:
    """Invite email for a newly created admin account."""
    ttl = (
        settings.admin_invite_ttl_minutes if ttl_minutes is None else int(ttl_minutes)
    )
    rendered = _render(
        "admin_invite",
        _brand_values(SETUP_URL=setup_url, TTL_MINUTES=str(ttl)),
    )
    return {
        "subject": f"Set your {settings.app_name or 'BotBase'} admin password",
        **rendered,
    }


async def deliver_admin_invite_email(email: str, raw_token: str) -> None:
    """Send the admin set-password invite. The raw token is never logged."""
    setup_url = (
        f"{settings.resolved_frontend_url}/reset-password?token={raw_token}"
    )
    rendered = render_admin_invite_email(setup_url)
    try:
        message_id = await email_service.send_email(
            to=email,
            subject=rendered["subject"],
            html=rendered["html"],
            text=rendered["text"],
            reply_to=settings.resolved_reply_to,
        )
    except Exception as exc:
        log.warning("Admin invite email skipped", outcome=type(exc).__name__)
        return
    log.info("Admin invite email sent", message_id=message_id)
