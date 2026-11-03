"""
api/admin/conversations.py
Aggregate conversation analytics (analytics.read) and gated message-content
viewing (conversations.read, audited on every view). No bulk content export.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from .deps import require_permission
from ...core.database import get_db
from ...services import admin_service

router = APIRouter()


@router.get("/conversations", summary="Conversation aggregates (no content)")
async def conversation_aggregates(
    workspace_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    page: int = 1,
    page_size: int = 25,
    user: dict = Depends(require_permission("analytics.read")),
):
    """Counts per workspace/date. Message text is never included here."""
    async with get_db() as db:
        where, params = [], []
        if workspace_id:
            where.append("c.workspace_id = ?")
            params.append(workspace_id)
        if from_date:
            where.append("c.created_at >= ?")
            params.append(from_date)
        if to_date:
            where.append("c.created_at <= ?")
            params.append(to_date)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        base = (
            "FROM conversations c "
            "LEFT JOIN messages m ON m.conversation_id = c.id "
        )
        cur = await db.execute(
            f"SELECT c.id, c.title, c.workspace_id, c.agent_id, c.created_at, "
            f"c.updated_at, COUNT(m.id) AS message_count "
            f"{base} {clause} GROUP BY c.id ORDER BY c.updated_at DESC "
            f"LIMIT ? OFFSET ?",
            (*params, admin_service.MAX_PAGE_SIZE, 0),
        )
        rows = await cur.fetchall()
        totals = await db.execute(
            f"SELECT COUNT(*) AS conversations, COALESCE(SUM(msg_count), 0) AS messages "
            f"FROM (SELECT c.id, COUNT(m.id) AS msg_count {base} {clause} GROUP BY c.id)",
            tuple(params),
        )
        total_row = await totals.fetchone()
    return {
        "items": [dict(r) for r in rows],
        "total_conversations": total_row["conversations"],
        "total_messages": total_row["messages"],
        "note": "Message content is not included here.",
    }


@router.get(
    "/conversations/{conversation_id}/messages",
    summary="View one conversation's messages (audited)",
)
async def conversation_messages(
    conversation_id: str,
    request: Request,
    user: dict = Depends(require_permission("conversations.read")),
):
    """
    Sensitive customer data. Every view is written to the audit log, and the
    response carries a reminder that access is logged. No bulk export exists.
    """
    async with get_db() as db:
        cur = await db.execute(
            "SELECT c.id, c.workspace_id, c.agent_id, m.id AS message_id, "
            "m.role, m.content, m.citations, m.created_at "
            "FROM conversations c JOIN messages m ON m.conversation_id = c.id "
            "WHERE c.id = ? ORDER BY m.created_at ASC",
            (conversation_id,),
        )
        rows = await cur.fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        await admin_service.write_audit(
            db, actor=user, action="conversation.view", target_type="conversation",
            target_id=conversation_id, summary="message content viewed",
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
    return {
        "conversation_id": conversation_id,
        "messages": [dict(r) for r in rows],
        "notice": "Viewing customer message content is logged and limited to "
                  "administrators with the conversations.read permission.",
    }
