"""
api/admin/overview.py
Platform overview: totals, trends, plan/trial breakdown, estimated revenue and
a "needs attention" panel. Every number is a real SQL count; anything without
a source is omitted rather than faked.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from .deps import require_permission
from ...core.database import get_db
from ...core.plan import PLAN_PRICES_TZS

router = APIRouter()


def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@router.get("/overview", summary="Platform totals and trends")
async def overview(user: dict = Depends(require_permission("overview.read"))):
    async with get_db() as db:
        async def one(sql: str, params: tuple = ()) -> int:
            cur = await db.execute(sql, params)
            row = await cur.fetchone()
            return int(row[0]) if row and row[0] is not None else 0

        totals = {
            "users": await one("SELECT COUNT(*) FROM users"),
            "signups_7d": await one(
                "SELECT COUNT(*) FROM users WHERE created_at >= ?", (_since(7),)
            ),
            "signups_30d": await one(
                "SELECT COUNT(*) FROM users WHERE created_at >= ?", (_since(30),)
            ),
            "signups_90d": await one(
                "SELECT COUNT(*) FROM users WHERE created_at >= ?", (_since(90),)
            ),
            "workspaces": await one("SELECT COUNT(*) FROM workspaces"),
            "agents": await one("SELECT COUNT(*) FROM agents"),
            "documents": await one("SELECT COUNT(*) FROM workspace_documents"),
            "chunks": await one("SELECT COUNT(*) FROM chunks"),
            "conversations": await one("SELECT COUNT(*) FROM conversations"),
            "messages": await one("SELECT COUNT(*) FROM messages"),
            "active_7d": await one(
                "SELECT COUNT(DISTINCT user_id) FROM usage_events "
                "WHERE created_at >= ? AND user_id IS NOT NULL",
                (_since(7),),
            ),
            "suspended": await one(
                "SELECT COUNT(*) FROM users WHERE suspended_at IS NOT NULL"
            ),
            "trials_expiring_7d": await one(
                "SELECT COUNT(*) FROM users WHERE trial_ends_at IS NOT NULL "
                "AND trial_ends_at >= ? AND trial_ends_at <= ?",
                (
                    datetime.now(timezone.utc).isoformat(),
                    (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                ),
            ),
        }

        plans = {
            row["plan"]: row["n"]
            for row in (
                await (
                    await db.execute(
                        "SELECT plan, COUNT(*) AS n FROM users GROUP BY plan"
                    )
                ).fetchall()
            )
        }
        trials = {
            "active": await one(
                "SELECT COUNT(*) FROM users WHERE trial_ends_at > ?",
                (datetime.now(timezone.utc).isoformat(),),
            ),
            "expired": await one(
                "SELECT COUNT(*) FROM users WHERE trial_ends_at IS NOT NULL "
                "AND trial_ends_at <= ?",
                (datetime.now(timezone.utc).isoformat(),),
            ),
        }

        chat = {
            "7d": await one(
                "SELECT COUNT(*) FROM usage_events WHERE created_at >= ? AND kind = 'chat'",
                (_since(7),),
            ),
            "30d": await one(
                "SELECT COUNT(*) FROM usage_events WHERE created_at >= ? AND kind = 'chat'",
                (_since(30),),
            ),
            "90d": await one(
                "SELECT COUNT(*) FROM usage_events WHERE created_at >= ? AND kind = 'chat'",
                (_since(90),),
            ),
        }
        by_channel = {
            row["channel"]: row["n"]
            for row in (
                await (
                    await db.execute(
                        "SELECT COALESCE(channel, 'legacy') AS channel, COUNT(*) AS n "
                        "FROM usage_events WHERE created_at >= ? AND kind = 'chat' "
                        "GROUP BY channel",
                        (_since(90),),
                    )
                ).fetchall()
            )
        }
        errors = await one(
            "SELECT COUNT(*) FROM usage_events WHERE status = 'error' "
            "AND created_at >= ?",
            (_since(30),),
        )
        total_30 = await one(
            "SELECT COUNT(*) FROM usage_events WHERE created_at >= ? AND kind = 'chat'",
            (_since(30),),
        )
        latency = await db.execute(
            "SELECT AVG(latency_ms) FROM usage_events "
            "WHERE latency_ms IS NOT NULL AND created_at >= ?",
            (_since(30),),
        )
        latency_row = await latency.fetchone()

        # Estimated monthly revenue: assigned paid plans only, labelled as an
        # estimate (manual payments until a gateway exists).
        standard_n = plans.get("standard", 0)
        pro_n = plans.get("pro", 0)
        revenue_estimate_tzs = (
            standard_n * PLAN_PRICES_TZS["standard"] + pro_n * PLAN_PRICES_TZS["pro"]
        )

        attention = []
        attention.append(
            {
                "kind": "failed_trainings",
                "count": await one(
                    "SELECT COUNT(*) FROM workspace_documents WHERE status = 'failed'"
                ),
            }
        )
        attention.append(
            {
                "kind": "failed_website_syncs",
                "count": await one(
                    "SELECT COUNT(*) FROM website_sources WHERE status = 'failed'"
                ),
            }
        )
        attention.append(
            {
                "kind": "suspended_accounts",
                "count": totals["suspended"],
            }
        )
        attention.append(
            {
                "kind": "expiring_trials",
                "count": totals["trials_expiring_7d"],
            }
        )
        attention.append(
            {
                "kind": "server_errors_24h",
                "count": await one(
                    "SELECT COUNT(*) FROM error_events WHERE ts >= ?",
                    (_since(1),),
                ),
            }
        )

    return {
        "totals": totals,
        "plans": plans,
        "trials": trials,
        "chat": chat,
        "chat_by_channel_90d": by_channel,
        "error_rate_30d": round(errors / total_30, 4) if total_30 else 0,
        "average_latency_ms_30d": (
            round(float(latency_row[0]), 1) if latency_row and latency_row[0] else None
        ),
        "estimated_monthly_revenue_tzs": revenue_estimate_tzs,
        "estimated_monthly_revenue_note": (
            "Estimate from assigned Standard/Pro plans; manual payments only."
        ),
        "needs_attention": attention,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
