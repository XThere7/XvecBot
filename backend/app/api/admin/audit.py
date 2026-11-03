"""
api/admin/audit.py
Append-only audit log: searchable/filterable list plus CSV export. Exports
are themselves audited.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from .deps import require_permission
from ...core.database import get_db
from ...services import admin_service

router = APIRouter()

AUDIT_SORTABLE = {"ts", "action", "actor_email"}


@router.get("/audit", summary="Searchable audit log")
async def audit_log(
    search: str | None = None,
    actor: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    sort: str | None = None,
    direction: str | None = None,
    page: int = 1,
    page_size: int = 25,
    user: dict = Depends(require_permission("audit.read")),
):
    async with get_db() as db:
        where, params = [], []
        like = admin_service.like_pattern(search)
        if like:
            where.append("(summary LIKE ? OR actor_email LIKE ? OR action LIKE ?)")
            params += [like, like, like]
        if actor:
            where.append("actor_email = ?")
            params.append(actor)
        if action:
            where.append("action = ?")
            params.append(action)
        if target_type:
            where.append("target_type = ?")
            params.append(target_type)
        if from_date:
            where.append("ts >= ?")
            params.append(from_date)
        if to_date:
            where.append("ts <= ?")
            params.append(to_date)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        cur = await db.execute(
            f"SELECT COUNT(*) AS n FROM audit_log {clause}", tuple(params)
        )
        total = int((await cur.fetchone())["n"])
        order_by = admin_service.validate_sort(sort, AUDIT_SORTABLE, "ts")
        direction_sql = admin_service.validate_direction(direction)
        page, size = admin_service.page_params(page, page_size)
        cur = await db.execute(
            f"SELECT id, ts, actor_id, actor_email, action, target_type, "
            f"target_id, summary, ip FROM audit_log {clause} "
            f"ORDER BY {order_by} {direction_sql} LIMIT ? OFFSET ?",
            (*params, size, (page - 1) * size),
        )
        rows = await cur.fetchall()
    return {
        "items": [dict(r) for r in rows],
        "page": page,
        "page_size": size,
        "total": total,
    }


@router.get("/audit/export", summary="CSV export of the audit log (audited)")
async def audit_export(
    request: Request,
    from_date: str | None = None,
    to_date: str | None = None,
    user: dict = Depends(require_permission("audit.read")),
):
    async with get_db() as db:
        where, params = [], []
        if from_date:
            where.append("ts >= ?")
            params.append(from_date)
        if to_date:
            where.append("ts <= ?")
            params.append(to_date)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        cur = await db.execute(
            f"SELECT ts, actor_email, action, target_type, target_id, summary, ip "
            f"FROM audit_log {clause} ORDER BY ts ASC",
            tuple(params),
        )
        rows = await cur.fetchall()
        await admin_service.write_audit(
            db, actor=user, action="audit.export", target_type=None,
            target_id=None, summary=f"csv export rows={len(rows)}",
            ip=request.client.host if request.client else None,
        )
        await db.commit()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["ts", "actor_email", "action", "target_type", "target_id",
                     "summary", "ip"])
    for row in rows:
        writer.writerow([row["ts"], row["actor_email"], row["action"],
                         row["target_type"], row["target_id"], row["summary"],
                         row["ip"]])
    buffer.seek(0)
    filename = f"audit-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
