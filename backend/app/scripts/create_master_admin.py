"""
Bootstrap the master admin (superadmin).

Usage (interactive — password is read with getpass, never from the command
line or an environment variable, and never logged or printed):

    cd backend
    ../.venv/bin/python -m app.scripts.create_master_admin --email founder@example.com

Idempotent: creates the account if it does not exist, otherwise promotes the
existing account. Refuses to create a second superadmin unless the explicit
--force-second flag is passed. The superadmin role can ONLY be assigned here
— never through the API or the UI.

--stdin reads the password from the first line of standard input. It exists
for the automated verification script and CI only; use the interactive
(getpass) form for real deployments.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
import uuid
from datetime import datetime, timezone

from ..core.auth import hash_password
from ..core.database import get_db, init_db


async def _bootstrap(email: str, force_second: bool, password: str) -> int:
    await init_db()
    async with get_db() as db:
        cur = await db.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'superadmin' AND "
            "suspended_at IS NULL"
        )
        existing_superadmins = int((await cur.fetchone())["n"])
        if existing_superadmins > 0 and not force_second:
            print(
                "A superadmin already exists. Refusing to create a second one. "
                "Re-run with --force-second only if you are certain."
            )
            return 1

        if len(password) < 8:
            print("Password must be at least 8 characters.")
            return 1

        cur = await db.execute("SELECT id, role FROM users WHERE email = ?", (email,))
        row = await cur.fetchone()
        if row:
            await db.execute(
                "UPDATE users SET role = 'superadmin', permissions = NULL, "
                "suspended_at = NULL, suspended_reason = NULL, "
                "hashed_password = ? WHERE id = ?",
                (hash_password(password), row["id"]),
            )
            action = "promoted"
            user_id = row["id"]
        else:
            user_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO users (id, email, hashed_password, is_active, "
                "created_at, plan, trial_ends_at, role) "
                "VALUES (?, ?, ?, 1, ?, 'free', NULL, 'superadmin')",
                (
                    user_id,
                    email,
                    hash_password(password),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            action = "created"
        await db.commit()

    print(f"Master admin {action}: {email}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or promote the master admin.")
    parser.add_argument("--email", required=True, help="Founder's account email.")
    parser.add_argument(
        "--force-second",
        action="store_true",
        help="Allow a second superadmin even when one already exists.",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read the password from stdin (verification/CI only).",
    )
    args = parser.parse_args()

    email = args.email.strip().lower()
    if "@" not in email:
        print("Enter a valid email address.")
        return 1

    if args.stdin:
        password = sys.stdin.readline().rstrip("\n")
        if not password:
            print("No password provided on stdin.")
            return 1
    else:
        password = getpass.getpass("Master admin password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match.")
            return 1

    return asyncio.run(_bootstrap(email, args.force_second, password))


if __name__ == "__main__":
    raise SystemExit(main())
