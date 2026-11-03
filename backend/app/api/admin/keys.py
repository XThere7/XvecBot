"""
api/admin/keys.py
Platform-wide API keys and embed tokens (prefixes only, never full secrets)
with revoke for abuse response.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .deps import require_permission
from ...core.database import get_db
from ...services import admin_service

router = APIRouter()


class RevokeBody(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


@router.get("/keys", summary="List developer API keys and embed tokens")
async def list_keys(
    kind: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
    user: dict = Depends(require_permission("keys.manage")),
):
    async with get_db() as db:
        like = admin_service.like_pattern(search)
        items = []
        page, size = admin_service.page_params(page, page_size)

        if kind in (None, "developer"):
            where, params = [], []
            if like:
                where.append("(k.key_prefix LIKE ? OR u.email LIKE ?)")
                params += [like, like]
            clause = f"WHERE {' AND '.join(where)}" if where else ""
            cur = await db.execute(
                f"SELECT k.id, k.user_id, u.email AS owner_email, k.workspace_id, "
                f"k.name, k.key_prefix, k.is_active, k.request_count, k.last_used_at, "
                f"k.expires_at, k.created_at "
                f"FROM developer_api_keys k JOIN users u ON u.id = k.user_id "
                f"{clause} ORDER BY k.created_at DESC LIMIT ? OFFSET ?",
                (*params, size, (page - 1) * size),
            )
            items += [dict(r) for r in await cur.fetchall()]

        if kind in (None, "embed"):
            where, params = [], []
            if like:
                where.append("(t.token LIKE ? OR u.email LIKE ?)")
                params += [like, like]
            clause = f"WHERE {' AND '.join(where)}" if where else ""
            cur = await db.execute(
                f"SELECT t.id, t.agent_id, u.email AS owner_email, t.label, "
                f"t.token AS token_prefix, t.is_active, t.request_count, "
                f"t.last_used_at, t.created_at "
                f"FROM agent_embed_tokens t "
                f"JOIN agents a ON a.id = t.agent_id "
                f"JOIN workspaces w ON w.id = a.workspace_id "
                f"JOIN users u ON u.id = w.owner_id "
                f"{clause} ORDER BY t.created_at DESC LIMIT ? OFFSET ?",
                (*params, size, (page - 1) * size),
            )
            for item in await cur.fetchall():
                row = dict(item)
                # Only ever expose the first 8 characters of an embed token.
                row["token_prefix"] = (row["token_prefix"] or "")[:8]
                row["kind"] = "embed"
                items.append(row)

        if kind == "developer":
            for item in items:
                item["kind"] = "developer"
    items = sorted(
        items, key=lambda item: item.get("created_at") or "", reverse=True
    )
    total = len(items)
    start = (page - 1) * size
    return {
        "items": items[start : start + size],
        "page": page,
        "page_size": size,
        "total": total,
        "note": "Only prefixes are displayed; full secrets are never returned.",
    }


@router.post("/keys/developer/{key_id}/revoke", summary="Revoke an API key")
async def revoke_developer_key(
    key_id: str,
    body: RevokeBody,
    request: Request,
    user: dict = Depends(require_permission("keys.manage")),
):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id FROM developer_api_keys WHERE id = ?", (key_id,)
        )
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="API key not found.")
        await db.execute(
            "UPDATE developer_api_keys SET is_active = 0 WHERE id = ?", (key_id,)
        )
        await admin_service.write_audit(
            db, actor=user, action="key.revoke", target_type="developer_api_key",
            target_id=key_id, summary=f"revoked: {body.reason[:200]}",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    return {"revoked": True}


@router.post("/keys/embed/{token_id}/revoke", summary="Revoke an embed token")
async def revoke_embed_token(
    token_id: str,
    body: RevokeBody,
    request: Request,
    user: dict = Depends(require_permission("keys.manage")),
):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id FROM agent_embed_tokens WHERE id = ?", (token_id,)
        )
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Embed token not found.")
        await db.execute(
            "UPDATE agent_embed_tokens SET is_active = 0 WHERE id = ?", (token_id,)
        )
        await admin_service.write_audit(
            db, actor=user, action="key.revoke", target_type="embed_token",
            target_id=token_id, summary=f"revoked: {body.reason[:200]}",
            ip=request.client.host if request.client else None,
        )
        await db.commit()
    return {"revoked": True}
