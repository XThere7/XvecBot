"""
services/email_service.py
Pluggable transactional email with no third-party dependency.

Backends are selected by ``EMAIL_BACKEND``:

  * ``file``    — write each message as an ``.eml`` file into a git-ignored
                  outbox directory (local development and the verification
                  script). This is the default so a fresh checkout can never
                  send real mail by accident.
  * ``memory``  — keep messages in an in-process list (unit tests).
  * ``console`` — print a header-only summary. Refuses to run when the app is
                  not in debug mode.
  * ``smtp``    — send through the platform's real mailbox using the standard
                  library (STARTTLS or SSL, 10 second socket timeouts, run off
                  the event loop via ``asyncio.to_thread``).

Messages are proper ``multipart/alternative`` (plain text + HTML) with
``From``, ``Reply-To``, ``Date``, ``Message-ID`` and UTF-8 headers (the
welcome subject contains an emoji).

Logging policy: never log credentials, message bodies, or recipient lists.
Only a message id and a coarse outcome are logged.
"""
from __future__ import annotations

import asyncio
import smtplib
import ssl
import uuid
from email.message import EmailMessage
from email.policy import default as default_policy
from email.utils import formataddr, formatdate, localtime, make_msgid
from pathlib import Path
from typing import Any

from ..core.config import settings
from ..core.logging import get_logger

log = get_logger(__name__)

# Unit tests read this list (reset_memory_outbox clears it between tests).
MEMORY_OUTBOX: list[dict[str, Any]] = []


class EmailBackendError(RuntimeError):
    """Raised when the configured backend cannot deliver the message."""


def reset_memory_outbox() -> None:
    """Clear the in-memory outbox (unit tests)."""
    MEMORY_OUTBOX.clear()


def _outbox_dir() -> Path:
    raw = (settings.email_outbox_dir or "./data/outbox").strip()
    path = Path(raw)
    if not path.is_absolute():
        # Resolve relative to the project root, like the other config paths.
        path = Path(__file__).resolve().parents[3] / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_message(
    *,
    to: str,
    subject: str,
    html: str,
    text: str,
    reply_to: str | None = None,
) -> tuple[str, EmailMessage]:
    """Build a multipart/alternative message and return (local_id, message)."""
    local_id = uuid.uuid4().hex
    message = EmailMessage(policy=default_policy)
    message["From"] = formataddr(
        ((settings.email_from_name or "BotBase").strip(), settings.email_from_address)
    )
    message["To"] = to
    reply = (reply_to or settings.resolved_reply_to).strip()
    if reply:
        message["Reply-To"] = reply
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(idstring=f"botbase.{local_id}")
    message["Date"] = formatdate(localtime=True)
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    return local_id, message


def _write_eml(message: EmailMessage, local_id: str) -> str:
    path = _outbox_dir() / f"{local_id}.eml"
    tmp = path.with_suffix(".eml.tmp")
    tmp.write_bytes(message.as_bytes(policy=default_policy))
    tmp.replace(path)
    return str(path)


def _console_send(message: EmailMessage, local_id: str) -> None:
    # Header-only summary: console output must never carry bodies, recipients
    # or credentials, and the console backend must refuse in production.
    if not settings.debug:
        raise EmailBackendError(
            "EMAIL_BACKEND=console is not allowed when DEBUG=false"
        )
    print(f"[email:{local_id}] {message['Subject']}")


def _send_smtp_sync(message: EmailMessage) -> None:
    host = (settings.smtp_host or "").strip()
    username = (settings.smtp_username or "").strip()
    password = settings.smtp_password or ""
    if not host:
        raise EmailBackendError("SMTP_HOST is not configured")
    if not username or not password:
        raise EmailBackendError(
            "SMTP credentials are not configured (SMTP_USERNAME/SMTP_PASSWORD)"
        )
    security = (settings.smtp_security or "starttls").strip().lower()
    if security == "ssl":
        with smtplib.SMTP_SSL(host, settings.smtp_port, timeout=10) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
        return
    with smtplib.SMTP(host, settings.smtp_port, timeout=10) as smtp:
        if security == "starttls":
            smtp.starttls(context=ssl.create_default_context())
        elif security != "none":
            raise EmailBackendError(f"Unknown SMTP_SECURITY: {security!r}")
        smtp.login(username, password)
        smtp.send_message(message)


async def send_email(
    to: str,
    subject: str,
    html: str,
    text: str,
    reply_to: str | None = None,
) -> str:
    """Deliver one transactional message and return its local id.

    Raises on failure — callers decide whether that matters. Registration
    deliberately catches and continues.
    """
    local_id, message = build_message(
        to=to, subject=subject, html=html, text=text, reply_to=reply_to
    )
    backend = (settings.email_backend or "file").strip().lower()
    try:
        if backend == "file":
            await asyncio.to_thread(_write_eml, message, local_id)
        elif backend == "memory":
            MEMORY_OUTBOX.append(
                {
                    "local_id": local_id,
                    "to": to,
                    "subject": subject,
                    "html": html,
                    "text": text,
                    "reply_to": reply_to or "",
                    "from": message["From"],
                }
            )
        elif backend == "console":
            await asyncio.to_thread(_console_send, message, local_id)
        elif backend == "smtp":
            await asyncio.to_thread(_send_smtp_sync, message)
        else:
            raise EmailBackendError(f"Unknown EMAIL_BACKEND: {settings.email_backend!r}")
    except Exception as exc:
        log.warning(
            "Email not sent",
            message_id=local_id,
            backend=backend,
            outcome=type(exc).__name__,
        )
        raise
    log.info("Email sent", message_id=local_id, backend=backend, outcome="sent")
    return local_id
