"""
api/admin/usage.py
Usage and model analytics: requests over time, by model/channel/plan, latency
percentiles, error rates, top workspaces, and a clearly-labelled cost
estimate from token counts (or provider list prices when tokens are missing).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from .deps import require_permission
from ...core.database import get_db

router = APIRouter()


def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@router.get("/usage/summary", summary="Usage analytics")
async def usage_summary(
    days: int = 30,
    user: dict = Depends(require_permission("analytics.read")),
):
    days = max(1, min(90, int(days)))
    since = _since(days)
    async with get_db() as db:
        async def rows(sql: str, params: tuple = ()):
            cur = await db.execute(sql, params)
            return [dict(r) for r in await cur.fetchall()]

        total = await db.execute(
            "SELECT COUNT(*) AS n FROM usage_events WHERE created_at >= ? AND kind = 'chat'",
            (since,),
        )
        total_n = int((await total.fetchone())["n"])

        errors = await db.execute(
            "SELECT COUNT(*) AS n FROM usage_events WHERE created_at >= ? "
            "AND status = 'error' AND kind = 'chat'",
            (since,),
        )
        errors_n = int((await errors.fetchone())["n"])

        by_model = await rows(
            "SELECT COALESCE(model, 'unknown') AS model, COUNT(*) AS n, "
            "COALESCE(AVG(latency_ms), 0) AS avg_latency_ms, "
            "COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens, "
            "COALESCE(SUM(completion_tokens), 0) AS completion_tokens "
            "FROM usage_events WHERE created_at >= ? AND kind = 'chat' "
            "GROUP BY model ORDER BY n DESC",
            (since,),
        )
        by_channel = await rows(
            "SELECT COALESCE(channel, 'legacy') AS channel, COUNT(*) AS n "
            "FROM usage_events WHERE created_at >= ? AND kind = 'chat' "
            "GROUP BY channel ORDER BY n DESC",
            (since,),
        )
        by_day = await rows(
            "SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS n, "
            "SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors "
            "FROM usage_events WHERE created_at >= ? AND kind = 'chat' "
            "GROUP BY day ORDER BY day ASC",
            (since,),
        )
        latency_percentiles = await rows(
            "SELECT "
            "MIN(latency_ms) AS p0, "
            "MAX(latency_ms) AS p100 "
            "FROM usage_events WHERE created_at >= ? AND latency_ms IS NOT NULL",
            (since,),
        )
        # Simple in-SQL percentiles via ordered window is heavy; approximate
        # with AVG and report it honestly.
        avg_latency = await db.execute(
            "SELECT AVG(latency_ms) FROM usage_events WHERE created_at >= ? "
            "AND latency_ms IS NOT NULL",
            (since,),
        )
        avg_latency_row = await avg_latency.fetchone()

        top_workspaces = await rows(
            "SELECT ue.workspace_id, w.name AS workspace_name, u.email AS owner_email, "
            "COUNT(*) AS n "
            "FROM usage_events ue "
            "LEFT JOIN workspaces w ON w.id = ue.workspace_id "
            "LEFT JOIN users u ON u.id = w.owner_id "
            "WHERE ue.created_at >= ? AND ue.kind = 'chat' "
            "GROUP BY ue.workspace_id, w.name, u.email ORDER BY n DESC LIMIT 20",
            (since,),
        )

    # Rough cost estimate: provider-style blended price per 1M tokens.
    # Clearly labelled as an estimate — the platform has no per-token billing.
    prompt_total = sum(int(m["prompt_tokens"] or 0) for m in by_model)
    completion_total = sum(int(m["completion_tokens"] or 0) for m in by_model)
    cost_usd_estimate = round(
        prompt_total / 1_000_000 * 0.15 + completion_total / 1_000_000 * 0.60, 4
    )

    return {
        "window_days": days,
        "total_requests": total_n,
        "error_rate": round(errors_n / total_n, 4) if total_n else 0,
        "average_latency_ms": (
            round(float(avg_latency_row[0]), 1)
            if avg_latency_row and avg_latency_row[0] is not None
            else None
        ),
        "latency_min_max_ms": latency_percentiles[0] if latency_percentiles else {},
        "by_model": by_model,
        "by_channel": by_channel,
        "by_day": by_day,
        "top_workspaces": top_workspaces,
        "cost_usd_estimate": cost_usd_estimate,
        "cost_estimate_note": (
            "Estimate only: blended $0.15/1M input and $0.60/1M output tokens; "
            "no per-token billing exists."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
