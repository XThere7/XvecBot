"""
services/email_agent_service.py
Email Agent: configured mailbox → incoming message → AI draft → simulated SMS
alert → owner review → approve → simulated send.

What is real:
  * the integration record, encrypted credentials, filters and audit trail;
  * incoming-message ingestion and idempotent deduplication;
  * knowledge-grounded draft generation through the same retrieval stack as chat;
  * draft editing, approval/rejection state machine and dashboard persistence.

What is simulated (clearly labelled in the UI and in stored status):
  * SMS delivery (``notification_service``);
  * sending the approved reply. No outbound email leaves the server. A row is
    marked ``sent`` only together with ``sent_simulated = 1``.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite
from fastapi import HTTPException, status

from ..core.credentials import decrypt_json, encrypt_json
from ..core.logging import get_logger
from ..llm.generator import build_generator
from ..models.email_agent import EmailIntegrationUpsert, SimulatedEmailRequest
from . import notification_service, plan_service

log = get_logger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DEFAULT_LIMIT = 25
MAX_LIMIT = 100


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_load(raw: Any, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _row_to_integration(row: Any, *, include_secrets: bool = False) -> dict[str, Any]:
    data = dict(row)
    encrypted = data.pop("credentials_encrypted", None)
    data["filters"] = _json_load(data.get("filters"), {})
    data["has_credentials"] = bool(encrypted)
    if include_secrets:
        data["_credentials"] = decrypt_json(encrypted)
    return data


def _row_to_email(row: Any) -> dict[str, Any]:
    return dict(row)


def _row_to_draft(row: Any, email: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    data = dict(row)
    if email is not None:
        data["email"] = _row_to_email(email)
    return data


async def get_integration(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str
) -> Optional[dict[str, Any]]:
    async with db.execute(
        """SELECT * FROM email_integrations
           WHERE workspace_id = ? AND agent_id = ?""",
        (workspace_id, agent_id),
    ) as cur:
        row = await cur.fetchone()
    return _row_to_integration(row) if row is not None else None


async def upsert_integration(
    db: aiosqlite.Connection,
    workspace: dict,
    agent_id: str,
    payload: EmailIntegrationUpsert,
    *,
    actor: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Create or update the agent's mailbox configuration.

    Credentials are accepted only here and are encrypted before the row is
    written. The response never contains them.
    """
    plan = await plan_service.plan_for_workspace(db, workspace)
    if not plan_service.feature_enabled(plan, "email_integration"):
        raise plan_service.limit_error(
            resource="email_integration",
            plan=plan,
            used=0,
            limit=0,
            code="plan_feature_locked",
            message=(
                "The Email Agent is included in Standard and Pro. Upgrade this "
                "workspace to connect a mailbox."
            ),
        )

    email_address = payload.email_address.strip().lower()
    if not EMAIL_RE.match(email_address):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter a valid email address.",
        )

    existing = await get_integration(db, workspace["id"], agent_id)
    filters_json = json.dumps(payload.filters or {})
    notification_phone = notification_service.normalise_phone(payload.notification_phone)
    if payload.notification_phone and notification_phone is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter a valid notification phone number.",
        )

    credentials_blob = None
    if payload.imap_password or payload.imap_username:
        credentials_blob = encrypt_json(
            {
                "imap_username": (payload.imap_username or "").strip(),
                "imap_password": payload.imap_password or "",
            }
        )

    if payload.provider == "simulated":
        integration_status = "simulation_ready"
    elif payload.provider == "imap" and credentials_blob:
        integration_status = "credentials_saved"
    elif payload.provider in ("gmail_oauth", "microsoft_oauth"):
        integration_status = "oauth_required"
    else:
        integration_status = "setup_required"

    now = _now()
    if existing is None:
        integration_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO email_integrations
               (id, workspace_id, agent_id, provider, email_address, display_name,
                credentials_encrypted, status, filters, automation_enabled,
                notification_phone, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                integration_id,
                workspace["id"],
                agent_id,
                payload.provider,
                email_address,
                (payload.display_name or "").strip() or None,
                credentials_blob,
                integration_status,
                filters_json,
                1 if payload.automation_enabled else 0,
                notification_phone,
                now,
                now,
            ),
        )
    else:
        integration_id = existing["id"]
        # An empty password means "keep the stored credentials", not "erase".
        await db.execute(
            """UPDATE email_integrations
               SET provider = ?, email_address = ?, display_name = ?,
                   credentials_encrypted = COALESCE(?, credentials_encrypted),
                   status = ?, filters = ?, automation_enabled = ?,
                   notification_phone = ?, updated_at = ?
               WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
            (
                payload.provider,
                email_address,
                (payload.display_name or "").strip() or None,
                credentials_blob,
                integration_status,
                filters_json,
                1 if payload.automation_enabled else 0,
                notification_phone,
                now,
                integration_id,
                workspace["id"],
                agent_id,
            ),
        )
    await db.commit()

    if actor is not None:
        from . import admin_service

        await admin_service.write_audit(
            db,
            actor=actor,
            action="email_integration.saved",
            target_type="email_integration",
            target_id=integration_id,
            summary=(
                f"Email integration {payload.provider} configured for agent "
                f"{agent_id}; credentials {'stored encrypted' if credentials_blob else 'unchanged'}."
            ),
        )
        await db.commit()

    saved = await get_integration(db, workspace["id"], agent_id)
    assert saved is not None
    log.info(
        "Email integration saved",
        workspace_id=workspace["id"],
        agent_id=agent_id,
        provider=payload.provider,
        has_credentials=bool(credentials_blob) or saved["has_credentials"],
    )
    return saved


async def delete_integration(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    *,
    actor: Optional[dict[str, Any]] = None,
) -> None:
    await db.execute(
        """DELETE FROM email_integrations
           WHERE workspace_id = ? AND agent_id = ?""",
        (workspace_id, agent_id),
    )
    await db.commit()
    if actor is not None:
        from . import admin_service

        await admin_service.write_audit(
            db,
            actor=actor,
            action="email_integration.deleted",
            target_type="email_integration",
            target_id=agent_id,
            summary="Email integration removed; stored credentials were deleted.",
        )
        await db.commit()


def _passes_filters(payload: SimulatedEmailRequest, filters: dict[str, Any]) -> tuple[bool, Optional[str]]:
    sender = payload.sender_email.strip().lower()
    ignored = {str(item).strip().lower() for item in filters.get("ignore_senders", []) if str(item).strip()}
    if sender in ignored:
        return False, "Sender is on the ignore list."
    keywords = [str(item).strip().lower() for item in filters.get("subject_keywords", []) if str(item).strip()]
    if keywords and not any(keyword in payload.subject.lower() for keyword in keywords):
        return False, "Subject did not match the configured keywords."
    return True, None


async def receive_email(
    db: aiosqlite.Connection,
    workspace: dict,
    agent: dict,
    payload: SimulatedEmailRequest,
    *,
    actor: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Ingest one (simulated) incoming email and produce an AI draft."""
    integration = await get_integration(db, workspace["id"], agent["id"])
    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Configure the Email Agent before receiving messages.",
        )
    plan = await plan_service.plan_for_workspace(db, workspace)
    if not plan_service.feature_enabled(plan, "email_integration"):
        raise plan_service.limit_error(
            resource="email_integration",
            plan=plan,
            used=0,
            limit=0,
            code="plan_feature_locked",
            message="The Email Agent is not included in the current plan.",
        )

    sender_email = payload.sender_email.strip().lower()
    if not EMAIL_RE.match(sender_email):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter a valid sender email address.",
        )

    provider_message_id = (
        (payload.provider_message_id or "").strip()
        or "sim-" + hashlib.sha256(
            f"{sender_email}|{payload.subject}|{payload.body_text}|{payload.received_at or ''}".encode("utf-8")
        ).hexdigest()
    )

    async with db.execute(
        """SELECT * FROM incoming_emails
           WHERE integration_id = ? AND provider_message_id = ?""",
        (integration["id"], provider_message_id),
    ) as cur:
        existing = await cur.fetchone()
    if existing is not None:
        email = _row_to_email(existing)
        draft = await get_draft_for_email(db, workspace["id"], agent["id"], email["id"])
        return {"email": email, "draft": draft, "duplicate": True}

    email_id = str(uuid.uuid4())
    now = _now()
    received_at = (payload.received_at or "").strip() or now
    await db.execute(
        """INSERT INTO incoming_emails
           (id, workspace_id, agent_id, integration_id, provider_message_id,
            sender_name, sender_email, subject, body_text, received_at, status,
            error_message, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'processing', NULL, ?)""",
        (
            email_id,
            workspace["id"],
            agent["id"],
            integration["id"],
            provider_message_id,
            (payload.sender_name or "").strip() or None,
            sender_email,
            payload.subject.strip()[:300],
            payload.body_text.strip(),
            received_at,
            now,
        ),
    )
    await db.commit()

    passes, reason = _passes_filters(payload, integration.get("filters") or {})
    if not passes:
        await db.execute(
            """UPDATE incoming_emails
               SET status = 'filtered', error_message = ?
               WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
            (reason, email_id, workspace["id"], agent["id"]),
        )
        await db.commit()
        email = await get_incoming_email(db, workspace["id"], agent["id"], email_id)
        return {"email": email, "draft": None, "duplicate": False, "filtered": True}

    if not integration.get("automation_enabled"):
        await db.execute(
            """UPDATE incoming_emails SET status = 'received'
               WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
            (email_id, workspace["id"], agent["id"]),
        )
        await db.commit()
        email = await get_incoming_email(db, workspace["id"], agent["id"], email_id)
        return {"email": email, "draft": None, "duplicate": False}

    draft = await _create_draft(db, workspace, agent, integration, email_id)
    incoming_status = "drafted" if draft["status"] == "draft_ready" else "failed"
    await db.execute(
        """UPDATE incoming_emails
           SET status = ?, error_message = ?
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (
            incoming_status,
            draft.get("error_message"),
            email_id,
            workspace["id"],
            agent["id"],
        ),
    )
    await db.commit()

    if draft["status"] == "draft_ready" and integration.get("notification_phone"):
        sender = (payload.sender_name or sender_email).strip()
        await notification_service.send_simulated_sms(
            db,
            workspace_id=workspace["id"],
            agent_id=agent["id"],
            recipient=integration["notification_phone"],
            body=(
                "Botbase Email Agent: A reply has been drafted for an email "
                f"from {sender}. Subject: {payload.subject.strip()[:80]}. "
                "Review and approve it from your dashboard."
            ),
            related_type="email_draft",
            related_id=draft["id"],
        )

    email = await get_incoming_email(db, workspace["id"], agent["id"], email_id)
    return {
        "email": email,
        "draft": await get_draft(db, workspace["id"], agent["id"], draft["id"]),
        "duplicate": False,
    }


async def _create_draft(
    db: aiosqlite.Connection,
    workspace: dict,
    agent: dict,
    integration: dict[str, Any],
    email_id: str,
) -> dict[str, Any]:
    email = await get_incoming_email(db, workspace["id"], agent["id"], email_id)
    draft_id = str(uuid.uuid4())
    now = _now()
    body = ""
    model_used: Optional[str] = None
    error_message: Optional[str] = None

    try:
        from .agent_chat_service import _format_context, _retrieve_knowledge

        query = f"Subject: {email['subject']}\n\n{email['body_text']}"
        chunks, _sources = await _retrieve_knowledge(
            db, workspace["id"], agent["id"], query
        )
        context = _format_context(chunks)
        system_prompt = (
            f"{agent['system_prompt']}\n\n"
            "You are replying to a customer email on behalf of this business. "
            "Write a concise, professional reply in the customer's language. "
            "Use only the retrieved knowledge when making factual claims. If the "
            "knowledge does not answer the question, say a team member will "
            "follow up. Do not invent prices, policies or availability. "
            "Return only the email body, without a subject line or markdown "
            "code fences."
        )
        llm = build_generator()
        body = (
            await llm.generate(
                query=query,
                context=context,
                system_prompt=system_prompt,
                history=[],
                model=agent["model"],
                temperature=0.3,
            )
        ).strip()
        model_used = llm.last_model_used
        if not body:
            raise RuntimeError("The model returned an empty draft.")
    except Exception as exc:
        error_message = (
            "The AI provider could not generate a draft. You can write the reply "
            "manually and approve it. Technical detail: " + str(exc)[:300]
        )
        log.warning("Email draft generation failed", error=type(exc).__name__)

    draft_status = "draft_ready" if body else "failed"
    await db.execute(
        """INSERT INTO email_drafts
           (id, workspace_id, agent_id, integration_id, email_id, body, status,
            model_used, error_message, approved_at, sent_at, sent_simulated,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0, ?, ?)""",
        (
            draft_id,
            workspace["id"],
            agent["id"],
            integration["id"],
            email_id,
            body,
            draft_status,
            model_used,
            error_message,
            now,
            now,
        ),
    )
    await db.commit()
    return await get_draft(db, workspace["id"], agent["id"], draft_id)


async def get_incoming_email(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str, email_id: str
) -> dict[str, Any]:
    async with db.execute(
        """SELECT * FROM incoming_emails
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (email_id, workspace_id, agent_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Email not found"
        )
    return _row_to_email(row)


async def list_incoming(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    limit = max(1, min(MAX_LIMIT, int(limit)))
    offset = max(0, int(offset))
    async with db.execute(
        """SELECT COUNT(*) AS n FROM incoming_emails
           WHERE workspace_id = ? AND agent_id = ?""",
        (workspace_id, agent_id),
    ) as cur:
        row = await cur.fetchone()
    total = int(row["n"] if row is not None else 0)
    async with db.execute(
        """SELECT * FROM incoming_emails
           WHERE workspace_id = ? AND agent_id = ?
           ORDER BY received_at DESC LIMIT ? OFFSET ?""",
        (workspace_id, agent_id, limit, offset),
    ) as cur:
        rows = await cur.fetchall()
    return [_row_to_email(r) for r in rows], total


async def get_draft(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str, draft_id: str
) -> dict[str, Any]:
    async with db.execute(
        """SELECT * FROM email_drafts
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (draft_id, workspace_id, agent_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found"
        )
    draft = _row_to_draft(row)
    draft["email"] = await get_incoming_email(
        db, workspace_id, agent_id, draft["email_id"]
    )
    return draft


async def get_draft_for_email(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str, email_id: str
) -> Optional[dict[str, Any]]:
    async with db.execute(
        """SELECT * FROM email_drafts
           WHERE email_id = ? AND workspace_id = ? AND agent_id = ?""",
        (email_id, workspace_id, agent_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return await get_draft(db, workspace_id, agent_id, row["id"])


async def list_drafts(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    *,
    status_filter: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    limit = max(1, min(MAX_LIMIT, int(limit)))
    offset = max(0, int(offset))
    clauses = ["workspace_id = ?", "agent_id = ?"]
    params: list[Any] = [workspace_id, agent_id]
    if status_filter:
        clauses.append("status = ?")
        params.append(status_filter)
    where = " AND ".join(clauses)
    async with db.execute(
        f"SELECT COUNT(*) AS n FROM email_drafts WHERE {where}", tuple(params)
    ) as cur:
        row = await cur.fetchone()
    total = int(row["n"] if row is not None else 0)
    async with db.execute(
        f"""SELECT * FROM email_drafts WHERE {where}
            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    ) as cur:
        rows = await cur.fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        draft = _row_to_draft(row)
        try:
            draft["email"] = await get_incoming_email(
                db, workspace_id, agent_id, draft["email_id"]
            )
        except HTTPException:
            draft["email"] = None
        items.append(draft)
    return items, total


async def update_draft(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    draft_id: str,
    body: str,
    *,
    actor: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    draft = await get_draft(db, workspace_id, agent_id, draft_id)
    if draft["status"] in ("sent", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This draft is already final and cannot be edited.",
        )
    cleaned = body.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The reply cannot be empty.",
        )
    await db.execute(
        """UPDATE email_drafts
           SET body = ?, status = 'draft_ready', error_message = NULL, updated_at = ?
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (cleaned[:30000], _now(), draft_id, workspace_id, agent_id),
    )
    await db.commit()
    if actor is not None:
        from . import admin_service

        await admin_service.write_audit(
            db,
            actor=actor,
            action="email_draft.edited",
            target_type="email_draft",
            target_id=draft_id,
            summary="Owner edited an AI email draft.",
        )
        await db.commit()
    return await get_draft(db, workspace_id, agent_id, draft_id)


async def approve_and_simulate_send(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    draft_id: str,
    *,
    body: Optional[str],
    confirm_simulated_send: bool,
    actor: dict[str, Any],
) -> dict[str, Any]:
    if not confirm_simulated_send:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Confirm that you understand sending is simulated before "
                "approving this reply."
            ),
        )
    draft = await get_draft(db, workspace_id, agent_id, draft_id)
    if draft["status"] in ("sent", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This draft is already final.",
        )
    final_body = (body or draft["body"]).strip()
    if not final_body:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Write a reply before approving it.",
        )
    now = _now()
    await db.execute(
        """UPDATE email_drafts
           SET body = ?, status = 'sent', approved_at = ?, sent_at = ?,
               sent_simulated = 1, error_message = NULL, updated_at = ?
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (final_body[:30000], now, now, now, draft_id, workspace_id, agent_id),
    )
    await db.execute(
        """UPDATE incoming_emails SET status = 'sent'
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (draft["email_id"], workspace_id, agent_id),
    )
    await db.execute(
        """INSERT INTO email_approvals
           (id, workspace_id, agent_id, email_id, draft_id, action, actor_id,
            notes, created_at)
           VALUES (?, ?, ?, ?, ?, 'approved_and_sent_simulated', ?, ?, ?)""",
        (
            str(uuid.uuid4()),
            workspace_id,
            agent_id,
            draft["email_id"],
            draft_id,
            actor.get("id"),
            "Owner approved the draft; send was simulated.",
            now,
        ),
    )
    await db.commit()

    from . import admin_service

    await admin_service.write_audit(
        db,
        actor=actor,
        action="email_draft.approved",
        target_type="email_draft",
        target_id=draft_id,
        summary="Owner approved an email draft; outbound send was simulated.",
    )
    await db.commit()
    log.info(
        "Email draft approved (simulated send)",
        workspace_id=workspace_id,
        agent_id=agent_id,
        draft_id=draft_id,
    )
    return await get_draft(db, workspace_id, agent_id, draft_id)


async def reject_draft(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    draft_id: str,
    *,
    reason: Optional[str],
    actor: dict[str, Any],
) -> dict[str, Any]:
    draft = await get_draft(db, workspace_id, agent_id, draft_id)
    if draft["status"] == "sent":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A sent draft cannot be rejected.",
        )
    now = _now()
    await db.execute(
        """UPDATE email_drafts
           SET status = 'rejected', error_message = ?, updated_at = ?
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        ((reason or "Rejected by owner.")[:1000], now, draft_id, workspace_id, agent_id),
    )
    await db.execute(
        """UPDATE incoming_emails SET status = 'rejected'
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (draft["email_id"], workspace_id, agent_id),
    )
    await db.execute(
        """INSERT INTO email_approvals
           (id, workspace_id, agent_id, email_id, draft_id, action, actor_id,
            notes, created_at)
           VALUES (?, ?, ?, ?, ?, 'rejected', ?, ?, ?)""",
        (
            str(uuid.uuid4()),
            workspace_id,
            agent_id,
            draft["email_id"],
            draft_id,
            actor.get("id"),
            (reason or "")[:1000],
            now,
        ),
    )
    await db.commit()

    from . import admin_service

    await admin_service.write_audit(
        db,
        actor=actor,
        action="email_draft.rejected",
        target_type="email_draft",
        target_id=draft_id,
        summary="Owner rejected an email draft.",
    )
    await db.commit()
    return await get_draft(db, workspace_id, agent_id, draft_id)


async def stats(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str
) -> dict[str, int]:
    out = {
        "incoming_total": 0,
        "drafts_ready": 0,
        "awaiting_approval": 0,
        "sent_simulated": 0,
        "rejected": 0,
        "failed": 0,
    }
    async with db.execute(
        """SELECT COUNT(*) AS n FROM incoming_emails
           WHERE workspace_id = ? AND agent_id = ?""",
        (workspace_id, agent_id),
    ) as cur:
        row = await cur.fetchone()
    out["incoming_total"] = int(row["n"] if row is not None else 0)

    async with db.execute(
        """SELECT status, COUNT(*) AS n FROM email_drafts
           WHERE workspace_id = ? AND agent_id = ? GROUP BY status""",
        (workspace_id, agent_id),
    ) as cur:
        rows = await cur.fetchall()
    by_status = {row["status"]: int(row["n"]) for row in rows}
    out["drafts_ready"] = by_status.get("draft_ready", 0)
    out["awaiting_approval"] = by_status.get("draft_ready", 0) + by_status.get("failed", 0)
    out["sent_simulated"] = by_status.get("sent", 0)
    out["rejected"] = by_status.get("rejected", 0)
    out["failed"] = by_status.get("failed", 0)
    return out
