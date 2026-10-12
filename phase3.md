# Phase 3 — Config Hardening, Runtime Safety & Prod Images

Execution record for the production-readiness work completed **2026-10-12**.
Goal: secrets out of images, fail-fast on insecure config, honest health
signals, tests that can't pollute dev data, and an env-driven prod compose.
Local development behavior is unchanged (verified, see §3.5).

Design rule (same as Phase 2): production behavior arrives **behind env**,
the local default never moves.

---

## 1. What was built

### 1.1 Secrets out of the image (`docker/Dockerfile.backend`)

| Before | After |
|---|---|
| `COPY .env .` baked the live key into every image | Removed — config arrives as env vars or a runtime mount |
| No model-cache control | `HF_HOME/TRANSFORMERS_CACHE/HF_HUB_CACHE=/app/.hf-cache` (warmed at build) |
| Single uvicorn worker | `--workers ${UVICORN_WORKERS:-2}` (dev overrides with `--reload --workers 1`) |

### 1.2 Fail-fast on insecure secrets (`backend/app/main.py`, `core/config.py`)

- New `SECRET_KEY` setting (was missing entirely) + `enable_docs` flag
  (default `true` locally, `false` in prod).
- Lifespan guard: `DEBUG=false` + default `SECRET_KEY` → **refuse to boot**
  with an actionable error instead of signing JWTs with a public value.
- Behavior matrix (verified): prod+default → refuse; prod+real key → boot;
  dev (`DEBUG=true`)+default → boot.
- Local `.env` (untracked, never committed) was given a generated 64-hex
  `SECRET_KEY` so the existing `DEBUG=false` dev setup keeps booting.

### 1.3 Interactive docs hidden in production (`backend/app/main.py`)

`docs_url`/`redoc_url` are `None` when `ENABLE_DOCS=false`.
Verified: `/docs` + `/redoc` → 404, `/health` → 200.

### 1.4 Honest readiness (`backend/app/api/health.py`)

`GET /health/ready` returned **200 even with a dead database** (failure was
buried in the JSON body), so orchestrators kept routing traffic to broken
replicas. Now: 200 `{"status":"ready"}` when the `SELECT 1` check passes,
**503** `{"status":"not_ready"}` when it doesn't (same body shape).
Verified against an unreachable Postgres (503 + `database: error`), and the
healthy path still returns 200 (`database: ok`).

### 1.5 Test isolation (`backend/app/tests/conftest.py`)

The suite used to write users/workspaces/documents into the developer's real
`data/rag.db` **and** real `data/uploads/` (every full run added junk rows;
restores from backup were needed twice in Phases 1–2).
Now `conftest.py` sets `DATABASE_URL` + `UPLOAD_DIR` to a throwaway temp dir
**before** `app` is first imported (settings freeze at import; real env vars
beat the `.env` file), and a session fixture runs `init_db()` once there.
Verified: full suite leaves dev DB at 23 users / 20 workspaces and uploads
at 15 dirs — byte-identical before and after.

### 1.6 Production env template + compose (`.env.example`, `docker/compose.prod.yml`)

- `.env.example` documents every Phase 1–3 variable: `SECRET_KEY`,
  `ENABLE_DOCS`, `APP_PUBLIC_URL`, Neon `DATABASE_URL` + pool sizes, all
  `S3_*/AWS_*/PRESIGNED_*/MAX_UPLOAD_BYTES`, `UVICORN_WORKERS`, frontend
  build args. Production CORS placeholder (`https://app.yourplatform.com`).
- `docker/compose.prod.yml`: Neon + R2/S3, **no** `../data:/app/data` DB
  mount, **no** `env_file`, required vars fail fast (`${VAR:?…}`),
  persistent `hf-cache` volume, `ENABLE_DOCS=false`, `UVICORN_WORKERS=2`,
  frontend built with prod API URL. Validated with
  `docker compose -f docker/compose.prod.yml config` (exit 0).

---

## 2. Deliberately deferred (with reasons)

| Item | Reason |
|---|---|
| `TIMESTAMPTZ` / `BOOLEAN` column migration | Correct but touches all 60 call sites + pydantic models; zero user value until then. Baseline stays TEXT/INTEGER by design. |
| `ACCESS_TOKEN_EXPIRE_DAYS` 7 → 1 | Would silently log out all users/apps; needs a comms plan, not a drive-by. |
| Rate limiting on `/auth` + `/public/*` | Needs a store (Redis/memory) decision + tests; queued for Phase 4/5. |
| Non-root image user | Would break the current root-owned bind-mount dev setup; belongs with Phase 4 volume work (see §4.2). |
| LAN CORS regex removal | Dev convenience; prod sets explicit `ALLOWED_ORIGINS`. No code change to avoid breaking LAN testing. |

---

## 3. Tests + verification results (2026-10-12)

| Check | Result |
|---|---|
| Full suite `pytest backend/app/tests/ -q` | **19 passed, 4 skipped** (HF downloads), **1 failed — pre-existing** LangGraph `'citations' state key` (fails identically on clean tree, untouched by this phase) |
| Dev-DB pollution check (23 users / 20 workspaces / 15 upload dirs before **and** after) | **PASS — isolation works, no restore needed** |
| Secret-guard matrix (refuse/boot/boot) | PASS |
| `ENABLE_DOCS=false` (`/docs`+`/redoc` 404, `/health` 200) | PASS |
| Readiness 503 on unreachable DB (body shape unchanged) | PASS |
| Readiness 200 on healthy PG (`database: ok`) | PASS (re-verified from Phase 2) |
| `compose.prod.yml config` validation | PASS (exit 0; only the stock `version` deprecation warning) |
| `py_compile` on all touched files | PASS |

---

## 4. Operational notes (read before hosting)

1. **Rotate `OPENROUTER_API_KEY`.** Still live in untracked `.env`. Images no
   longer bake it (this phase), but the key itself was once committed.
2. **The `rag-backend` compose container (project `docker`) runs as root with
   a bind mount on `data/` and zeroed `data/rag.db` on 2026-10-11.** It was
   stopped during Phase 2 (restart: `docker compose up -d backend`). Phase 4
   must add `user:` + named volumes (or the documented prod compose, which has
   no DB bind mount) before this bites again.
3. Durable dev-DB backup: `~/.xvec-backups/rag.db.phase2-start-2026-10-11`
   (do **not** rely on `/tmp` — wiped between sessions).
4. Commit for this phase: `Phase 3: …` on the current branch (local commit,
   unpushed unless you ask).
