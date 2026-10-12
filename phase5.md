# Phase 5 — Cutover Runbook: Staging → Production

Execution record for the production-readiness work completed **2026-10-12**.
Goal: make the actual go-live a checklist with automated gates, not an
adventure. Everything here runs against local, staging, and production with
only `--base-url` / env changing. Local development behavior is unchanged.

---

## 1. What was built

| File | Purpose |
|---|---|
| `scripts/cutover_preflight.py` | Read-only go/no-go gate: secrets, DB tables (+ alembic version on pg), R2 reachability, docs/CORS/public-URL posture, recent backups. Exit 0 = go, 1 = FAIL present. `--strict` is the production gate (prod-only SKIPs become FAILs) |
| `scripts/staging_smoke.py` | End-to-end probe: health → readiness → register → workspace → upload → train → poll ready → chat → delete doc → delete workspace. `--base-url` targets any deployment; `--no-chat` skips the LLM step where no key exists |
| `backend/app/tests/test_cutover_preflight.py` | The gate testing itself: non-strict passes locally, `--strict` rejects local (loopback CORS), every line is PASS/FAIL/SKIP |

Local `.env` (untracked, never committed) also gained a generated `API_KEY`
— it was still the documented placeholder, which the new preflight
correctly FAILed. The manual guide's `KEY=$(grep …)` pattern keeps working.

---

## 2. The cutover runbook (when you have Neon + R2 credentials)

1. **Provision.** Neon project (+ `pgvector`), R2 bucket (+ versioning and a
   lifecycle rule expiring `backups/`), PaaS services from
   `docker/compose.prod.yml` with real env (`DATABASE_URL`, `SECRET_KEY`,
   `API_KEY`, `OPENROUTER_API_KEY`, `ALLOWED_ORIGINS`, `APP_PUBLIC_URL`,
   `S3_*`). Keep local `.env` untouched.
2. **Deploy staging.** `alembic upgrade head`, then
   `python scripts/migrate_sqlite_to_neon.py --copy` (dry-run first),
   then `python scripts/backfill_uploads_to_r2.py --copy`.
3. **Gate.** `python scripts/cutover_preflight.py --strict` must exit 0.
   Then `python scripts/staging_smoke.py --base-url <staging>` (all steps ok;
   chat step needs the staging LLM key, else `--no-chat` + the §6 chat guide).
4. **Freeze writes** on the old deployment (maintenance banner), re-run the
   two copy scripts (final delta sync), take a `pg_dump` snapshot to R2.
5. **Switch** the dashboard build arg `NEXT_PUBLIC_API_BASE_URL` to prod,
   deploy, re-run preflight + smoke against prod.
6. **Monitor** 24 h (error rate, p95 chat latency, `/health/ready` 503s,
   R2 4xx). Rollback = flip the dashboard URL back + restore the Neon
   snapshot; the SQLite file stays a read-only fallback for 14 days.

---

## 3. Tests + verification results (2026-10-12, local)

| Check | Result |
|---|---|
| Live server boot (`uvicorn`, real embedding warmup) + `/health/ready` 200 | PASS |
| Preflight non-strict on local checkout | **9/9 ok** (after generating local `API_KEY`; docs/CORS/URL/backups correctly SKIP) |
| Preflight `--strict` on local checkout | Correctly **rejects** (docs on, loopback CORS, http URL) — the prod gate works |
| Smoke `--no-chat` vs live server (upload→train 1 chunk→ready→deletes) | **9/9 steps ok** |
| 2 new preflight tests | PASS |
| Full suite | **23 passed, 4 skipped**, **1 failed — pre-existing** LangGraph `'citations' state key` |
| Dev data after runs (smoke registers 1 user outside pytest isolation) | Restored to 23 users / 15 upload dirs from durable backup |

One bug fixed during verification: `cutover_preflight.py` shipped a `}`
for `]` typo (`str(exc)[:200})`) — caught by `py_compile` before first run.

---

## 4. Operational notes

1. **Rotate `OPENROUTER_API_KEY`.** Still live in untracked `.env`.
2. Smoke's `--no-chat` was used because each chat burns key credit; run one
   full chat (or the §6 guide) against staging before go-live.
3. Durable dev-DB backup: `~/.xvec-backups/rag.db.phase2-start-2026-10-11`.
4. The pytest suite is isolated (Phase 3), but `staging_smoke.py` and manual
   curl write to whichever `--base-url` you point at — never aim it at prod
   except during the cutover window.
5. Commit for this phase: `Phase 5: …` on the current branch (local commit,
   unpushed unless you ask).
