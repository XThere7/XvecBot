"""
scripts/staging_smoke.py (Phase 5)
End-to-end happy-path probe against ANY deployment (local, staging, prod):

  register -> workspace -> legacy upload -> train -> poll ready ->
  workspace chat (needs OPENROUTER_API_KEY on the target) ->
  delete doc -> delete workspace

Usage:
  python scripts/staging_smoke.py --base-url http://localhost:8000
  python scripts/staging_smoke.py --base-url https://api.yourplatform.com --no-chat

--no-chat skips the LLM step (use when the target has no LLM key).
Exit 0 when every step hits its expected status, else 1. Prints a step table.
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid

import httpx

steps: list[tuple[str, str]] = []


def step(name: str, ok: bool, detail: str = "") -> None:
    steps.append((name, "ok" if ok else "FAIL"))
    print(f"[{'ok' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        raise SystemExit(f"smoke FAILED at: {name} ({detail})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--no-chat", action="store_true")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    tag = uuid.uuid4().hex[:8]
    email = f"smoke-{tag}@example.com"

    with httpx.Client(base_url=base, timeout=60.0) as c:
        r = c.get("/health")
        step("health", r.status_code == 200, str(r.status_code))
        r = c.get("/health/ready")
        step("readiness", r.status_code == 200, str(r.status_code))

        r = c.post("/auth/register", json={"email": email, "password": "pw123456"})
        step("register", r.status_code == 201, str(r.status_code))
        auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = c.post("/workspaces", json={"name": f"smoke-{tag}"}, headers=auth)
        step("create-workspace", r.status_code == 201, str(r.status_code))
        ws = r.json()["id"]

        r = c.post(
            f"/workspaces/{ws}/documents",
            files={"file": ("smoke.txt", b"SMOKE keyword alpha bravo. " * 20, "text/plain")},
            headers=auth,
        )
        step("upload", r.status_code == 201, str(r.status_code))
        doc = r.json()["id"]

        r = c.post(f"/workspaces/{ws}/documents/{doc}/train", headers=auth)
        step("train-start", r.status_code == 202, str(r.status_code))
        ready = False
        for _ in range(40):
            time.sleep(3)
            s = c.get(f"/workspaces/{ws}/documents/{doc}/status", headers=auth).json()
            if s.get("status") in ("ready", "failed"):
                ready = s["status"] == "ready"
                step("train-ready", ready, f"chunks={s.get('chunk_count')}")
                break
        else:
            step("train-ready", False, "timed out polling status")

        if args.no_chat:
            print("[skip] chat (no LLM key on target)")
        else:
            r = c.post(
                f"/workspaces/{ws}/chat",
                json={"message": "What is the SMOKE keyword about?"},
                headers=auth,
            )
            ok = r.status_code == 200 and "SMOKE" in r.text.upper()
            step("chat", ok, str(r.status_code))

        r = c.delete(f"/workspaces/{ws}/documents/{doc}", headers=auth)
        step("delete-doc", r.status_code == 204, str(r.status_code))
        r = c.delete(f"/workspaces/{ws}", headers=auth)
        step("delete-workspace", r.status_code == 204, str(r.status_code))

    print(f"\nsmoke: all {len(steps)} steps ok against {base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
