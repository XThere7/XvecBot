#!/usr/bin/env python
"""
scripts/set_plan.py
Operator tool for changing a workspace's subscription plan while payments are
not configured. There is deliberately no public self-service upgrade endpoint:
this script is the supported way to move a test/demo workspace to Standard or
Pro until a payment provider is wired up.

Examples (from the repo root):
    python scripts/set_plan.py --list
    python scripts/set_plan.py --workspace-id <uuid> --plan pro
    python scripts/set_plan.py --email owner@example.com --plan standard

Inside the production compose stack:
    docker compose -f docker/compose.prod.yml exec backend \
        python /app/scripts/set_plan.py --workspace-id <uuid> --plan pro

Only the workspace's plan and plan_started_at change. Usage for the current
month is preserved, so downgrading below current usage blocks new responses
until the next monthly reset (or an upgrade).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.plans import PLAN_IDS  # noqa: E402
from app.services import plan_service  # noqa: E402


async def _run(args: argparse.Namespace) -> int:
    from app.core.database import get_db, init_db

    await init_db()
    async with get_db() as db:
        if args.list:
            async with db.execute(
                """SELECT w.id, w.name, w.plan, w.plan_started_at, u.email
                   FROM workspaces w JOIN users u ON u.id = w.owner_id
                   ORDER BY w.created_at DESC"""
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
            if not rows:
                print("No workspaces found.")
                return 0
            for row in rows:
                print(
                    f"{row['id']}  {row['plan']:<8}  "
                    f"{row['email']}  {row['name']}"
                )
            return 0

        if args.workspace_id:
            async with db.execute(
                "SELECT * FROM workspaces WHERE id = ?", (args.workspace_id,)
            ) as cur:
                matches = [dict(r) for r in await cur.fetchall()]
        elif args.email:
            async with db.execute(
                """SELECT w.* FROM workspaces w
                   JOIN users u ON u.id = w.owner_id
                   WHERE lower(u.email) = lower(?)""",
                (args.email,),
            ) as cur:
                matches = [dict(r) for r in await cur.fetchall()]
        else:
            print("Provide --workspace-id, --email, or --list.", file=sys.stderr)
            return 2

        if not matches:
            print("Workspace not found.", file=sys.stderr)
            return 1
        if len(matches) > 1:
            print(
                "That email owns more than one workspace; use --workspace-id. "
                "Candidates: " + ", ".join(m["id"] for m in matches),
                file=sys.stderr,
            )
            return 1

        workspace = matches[0]
        try:
            updated = await plan_service.set_workspace_plan(
                db, workspace["id"], args.plan
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        print(
            f"{updated['name']} ({updated['id']}): "
            f"{workspace.get('plan') or 'free'} -> {updated['plan']}"
        )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list workspaces")
    parser.add_argument("--workspace-id", help="workspace UUID")
    parser.add_argument("--email", help="workspace owner's email")
    parser.add_argument("--plan", choices=PLAN_IDS, help="target plan")
    args = parser.parse_args()

    if not args.list and not args.plan:
        parser.error("--plan is required unless --list is used")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
