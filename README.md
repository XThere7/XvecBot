# BotBase — Multi-Tenant RAG Platform

> PDF/TXT/DOCX Q&A platform with workspaces, AI agents, hybrid search
> (BM25 + vectors, RRF), cross-encoder reranking, grounding, and citations.
> Backend: FastAPI + LangGraph. Dashboard: Next.js. Sole LLM engine:
> OpenRouter cloud API.
>
> Local-first: runs on SQLite + local disk with zero cloud accounts.
> Production-ready: Neon Postgres + pgvector and R2/S3 presigned uploads
> activate purely via env (see `production.md`).

---

## Architecture

```
Browser (:3000, Next.js dashboard)
   │  JWT (Bearer)                       Embed snippet (customer sites)
   ▼                                     ▼
FastAPI (:8000) ── /workspaces/* ── multi-tenant CRUD, documents, training, chat
              ── /auth/*         ── register / login (JWT)
              ── /public/*       ── widget chat via one-time embed tokens
              ── /api/v1/*       ── legacy Phase-1 endpoints (X-API-Key)

Pipeline per document: extract (PyMuPDF) → chunk → embed (all-MiniLM-L6-v2)
→ index → hybrid retrieve → rerank → ground → generate (OpenRouter) → cite.

Storage, local default:  SQLite data/rag.db (+ sqlite-vec chunk_embeddings)
                         + data/uploads/ (or ./uploads/ for workspaces).
Storage, production:     Neon Postgres + pgvector, R2/S3 via presigned URLs
                         (browser ↔ storage directly; FastAPI never proxies bytes).
```

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, LangGraph, PyMuPDF, python-docx |
| Embeddings / rerank | all-MiniLM-L6-v2 / ms-marco-MiniLM-L-6-v2 |
| Search | BM25 + sqlite-vec (`vec0`) or pgvector (`vector(384)`), RRF |
| Relational DB | SQLite (aiosqlite) locally · Postgres (asyncpg + Alembic) in prod |
| Object storage | Local disk locally · R2/S3 presigned URLs in prod (`boto3`) |
| LLM | OpenRouter (`inclusionai/ling-3.0-flash-fin:free`, fallback `openrouter/free`) |
| Dashboard | Next.js 15 (`BaseBot_UI/`), TanStack Query/Table, Radix UI |
| Containers | Docker + Compose (`docker/docker-compose.yml` local, `docker/compose.prod.yml` prod) |

---

## Quick Start (local)

### Prerequisites

- Python 3.13 (`.venv` at repo root — do **not** use system 3.14) + Node.js 20+
- Docker (only for the container flow below)
- An OpenRouter API key — [openrouter.ai/keys](https://openrouter.ai/keys) (chat only; everything else works without it)

### 1. Configure

```bash
cp .env.example .env
# fill in at minimum:
#   OPENROUTER_API_KEY=sk-or-v1-...
#   SECRET_KEY=$(python3 -c "import secrets;print(secrets.token_hex(32))")
#   API_KEY=<anything-but-dev-key>
```

### 2a. Run natively (fastest iteration)

```bash
# backend (repo root)
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
# → API: http://127.0.0.1:8000  ·  docs: http://127.0.0.1:8000/docs

# dashboard (new terminal)
cd BaseBot_UI && npm install && npm run dev
# → http://localhost:3000  (NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000)
```

### 2b. Run in Docker (prod-like, still fully local)

```bash
# Optional but recommended so bind-mounted files keep your ownership:
export UID GID
docker compose -f docker/docker-compose.yml up --build -d
# → dashboard http://localhost:3000 · API http://localhost:8000
docker compose -f docker/docker-compose.yml logs -f backend
```

Health gates: `/health` (liveness) and `/health/ready` (200 only when the DB
is reachable, 503 otherwise — Docker and load balancers key off this).

### 3. Smoke test the happy path

```bash
.venv/bin/python scripts/staging_smoke.py --base-url http://127.0.0.1:8000 --no-chat
# register → workspace → upload → train → ready → delete doc → delete workspace
```

Without `--no-chat` it also chats (needs `OPENROUTER_API_KEY` on the target).
Manual curl walkthroughs live in `phase2.md` (§2–§11).

---

## Tests

```bash
.venv/bin/python -m pytest backend/app/tests/ -q
# Expected: 23 passed, 4 skipped (need HF downloads), 1 pre-existing failure:
# test_api_query (LangGraph "'citations' state key" — Phase-1 pipeline only,
# workspace chat is unaffected).
```

The suite runs against a **throwaway temp DB + temp uploads** (`conftest.py`
sets `DATABASE_URL`/`UPLOAD_DIR` before app import) — your real `data/rag.db`
and `data/uploads/` are never touched.

---

## Configuration

All settings come from env (see `.env.example`, the documented template).
Production-only values stay empty locally:

| Area | Key vars (local default → prod) |
|---|---|
| Secrets | `SECRET_KEY` (placeholder → 32+ hex; boot refuses placeholder when `DEBUG=false`), `API_KEY`, `OPENROUTER_API_KEY` |
| Database | `DATABASE_URL=sqlite:///./data/rag.db` → `postgresql://…?sslmode=require` (+ `PG_POOL_*`) |
| Storage | empty `S3_BUCKET` (local disk) → bucket + `S3_ENDPOINT_URL` (R2) + keys; `S3_PREFIX`, presigned expiries, `MAX_UPLOAD_BYTES` |
| App | `ENABLE_DOCS=true` → `false`; `ALLOWED_ORIGINS` → dashboard origin(s); `APP_PUBLIC_URL` → `https://…` |
| Runtime | `RATE_LIMIT_ENABLED=false` → `true` (+ per-minute); `LOG_LEVEL`; `UVICORN_WORKERS` |

Key scripts:

| Script | Purpose |
|---|---|
| `scripts/staging_smoke.py` | E2E probe vs any `--base-url` |
| `scripts/cutover_preflight.py` | Go/no-go gate (`--strict` for prod) |
| `scripts/migrate_sqlite_to_neon.py` | `--dry-run` parity / `--copy` SQLite → Postgres |
| `scripts/backfill_uploads_to_r2.py` | `--dry-run` / `--copy` local files → R2 |
| `scripts/backup_postgres_to_r2.py` | `--dry-run` / `--pg` / `--sqlite` nightly backups |

Alembic (`backend/alembic/`, revisions `0001` baseline + `0002` object-storage
columns) manages Postgres schema; SQLite self-heals via idempotent `init_db()`.

---

## Project Structure

```
├── .env / .env.example       # local config / documented template (never commit .env)
├── backend/app/
│   ├── api/          # auth, workspaces, documents (+presigned), agents, chat, public widget, health
│   ├── core/         # config, database (dual SQLite/PG), pg pool/compat/schema, auth, rate limit
│   ├── ingestion/    # extract → chunk → embed → index
│   ├── retrieval/    # BM25, vector, hybrid (RRF), reranker
│   ├── graph/        # LangGraph RAG workflow
│   ├── llm/          # OpenRouter generator (+ Mock test stub)
│   ├── services/     # document / training / chat / agent / embed-token logic
│   ├── models/       # Pydantic schemas
│   ├── storage/      # relational ops, vector_store (vec0/pgvector), object_store (local/S3)
│   └── tests/        # pytest suite (isolated temp DB)
├── BaseBot_UI/               # Next.js 15 dashboard (npm run dev / build / start)
├── data/                 # runtime state (gitignored): rag.db, uploads/
├── docker/               # Dockerfile.backend/frontend, docker-compose.yml (local), compose.prod.yml
├── scripts/              # smoke, preflight, migrate, backfill, backup
├── production.md         # 🌍 real-world deployment guide (start here for go-live)
└── phase2/3/4/5.md       # local execution notes (gitignored, not pushed)
```

---

## Going Live

**`production.md`** is the step-by-step guide: accounts (Neon, R2,
Render/Fly/Railway, domain), provisioning, staging deploy, data migration,
`--strict` gate, DNS/TLS, backups cron, monitoring, and rollback. The
dashboard deploys to **Vercel** (Root Directory `BaseBot_UI`, three
`NEXT_PUBLIC_*` vars per environment — §5). Nothing in it changes your local
setup — production activates purely via env.

---

Built by **Sam** · Dar es Salaam Institute of Technology
