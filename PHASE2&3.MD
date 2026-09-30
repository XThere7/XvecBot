# XvecBot — Phase 2 & 3 Technical Document

**Audience:** Developers continuing the project (Phase 4+)
**Scope:** Multi-tenant SaaS layer (Phase 2) and Agent Builder (Phase 3)
**Last verified:** 2026-09-28 against a running instance (36/36 integration tests passing)

---

## 1. What Phase 2 & 3 Added

| Phase | Concept | One-line summary |
|---|---|---|
| 1 (pre-existing) | RAG engine | Single-tenant PDF Q&A: upload → chunk → embed → hybrid search → rerank → LLM |
| 2 | Multi-tenant platform | Users, JWT auth, isolated Workspaces, per-workspace documents, training, workspace chat |
| 3 | Agent Builder | Agents (personalities) bound to a workspace, persistent conversations, per-agent chat |

The core idea: **a Workspace is a container of documents + vector knowledge. An Agent is a configured AI personality that draws on one workspace's knowledge.** One workspace can host many agents (e.g. "Sales Bot" and "Support Bot" over the same documents).

---

## 2. Technology Stack

| Concern | Technology |
|---|---|
| Web framework | FastAPI + uvicorn |
| Database | SQLite via `aiosqlite` (async) |
| Vector search | `sqlite-vec` (vec0 virtual table) |
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim) |
| Keyword search | `rank-bm25` (BM25Okapi) |
| Reranking | `sentence-transformers` cross-encoder (`ms-marco-MiniLM-L-6-v2`) |
| LLM | OpenRouter cloud API via `httpx` (OpenAI-compatible) |
| Auth | JWT (`python-jose`, HS256) + bcrypt (`passlib`) |
| RAG orchestration | LangGraph (Phase 1 pipeline) |
| PDF parsing | PyMuPDF (`pymupdf`) |
| Config | `pydantic-settings` + `.env` |
| Logging | `structlog` |

**Python version:** 3.13 (3.14 breaks the pinned `pydantic-core`).

---

## 3. Repository Layout (Phase 2 & 3 files)

```
backend/app/
├── core/
│   ├── config.py            ← settings (pydantic-settings), all env vars
│   ├── database.py          ← schema, init_db(), get_db(), column migrations
│   ├── auth.py              ← JWT sign/decode, bcrypt hash/verify
│   ├── agent_config.py      ← agent config validation & defaults (Phase 3)
│   └── logging.py           ← structlog setup
├── models/
│   ├── workspace.py         ← User, Workspace, WorkspaceDocument + SQL
│   ├── agent.py             ← Agent, AgentConversation, AgentMessage + SQL
│   ├── query.py             ← Citation (shared), QueryRequest/Response
│   ├── document.py          ← Phase 1 document models
│   └── chunk.py             ← Phase 1 chunk models
├── api/
│   ├── deps.py              ← get_current_user (JWT), verify_api_key (Phase 1)
│   ├── auth.py              ← /auth/register, /auth/login
│   ├── workspaces.py        ← /workspaces CRUD
│   ├── documents.py         ← /workspaces/{id}/documents + train/status/chat
│   └── agents.py            ← /workspaces/{id}/agents + conversations + chat
├── services/
│   ├── workspace_training_service.py  ← train_workspace_document()
│   ├── workspace_query_service.py     ← query_workspace() (Phase 2 chat)
│   ├── agent_service.py               ← agent CRUD
│   ├── conversation_service.py        ← conversation history
│   └── agent_chat_service.py          ← chat_with_agent() (Phase 3 chat)
├── ingestion/               ← Phase 1 (pdf_loader, chunker, embedder, indexer)
├── retrieval/               ← Phase 1 + workspace_id filter (vector_search, bm25, hybrid_search)
├── storage/
│   ├── vector_store.py      ← sqlite-vec insert/search/delete
│   └── sqlite.py            ← relational CRUD helpers
├── llm/
│   ├── generator.py         ← LLMGenerator interface + MockGenerator + build_generator()
│   ├── openrouter_generator.py ← OpenRouter backend (per-call model/temp/system_prompt/history)
│   └── prompts.py           ← prompt templates
└── graph/                   ← Phase 1 LangGraph pipeline
```

---

## 4. Database Schema

All tables live in a single SQLite file (`data/rag.db`). Schema is created idempotently at startup by `init_db()`.

### 4.1 Phase 1 tables (unchanged)

```sql
documents(id, filename, upload_date, total_pages, file_size, status)
chunks(id, document_id→documents, page, chunk_index, text)
conversations(id, created_at)
messages(id, conversation_id→conversations, role, content, citations, created_at)
chunk_embeddings  -- sqlite-vec virtual table (chunk_id, embedding float[384])
```

### 4.2 Phase 2 tables

```sql
users(id, email UNIQUE, hashed_password, is_active, created_at)
workspaces(id, name, description, system_prompt, owner_id→users, created_at)
workspace_documents(id, workspace_id→workspaces, filename, file_path, file_type,
                    size_bytes, status, chunk_count, created_at)
```

### 4.3 Phase 3 tables & migrations

```sql
agents(id, workspace_id→workspaces, name, description, system_prompt, model,
       temperature, language, is_active, created_at, updated_at)
```

**`conversations` and `messages` are SHARED between Phase 1 and Phase 3.** Because `CREATE TABLE IF NOT EXISTS` is a no-op against an existing table, the agent columns are appended with `ALTER TABLE ... ADD COLUMN` (guarded by `PRAGMA table_info`, idempotent, data-preserving):

```sql
-- appended to conversations:
agent_id   TEXT REFERENCES agents(id) ON DELETE CASCADE   -- NULL = legacy Phase 1 row
title      TEXT
updated_at TEXT NOT NULL DEFAULT ''

-- messages gains NO column. Agent sources reuse the existing `citations` JSON array.
```

**How to tell them apart:** an *agent conversation* is any `conversations` row with non-NULL `agent_id`. Legacy Phase 1 rows have `agent_id = NULL` and are untouched by Phase 3 code.

### 4.4 Entity relationships

```
users ──1:N──► workspaces ──1:N──► workspace_documents
                  │                 │
                  ├──1:N──► agents │
                  │           │     └──► chunks (via shadow documents row)
                  │           │            └──► chunk_embeddings
                  └──1:N──► conversations (agent_id NULL = legacy)
                              └──1:N──► messages (citations JSON)
```

### 4.5 The "shadow documents" row

`chunks.document_id` has a foreign key to `documents(id)`. To store workspace-doc chunks, training inserts a **shadow row into `documents`** with `id = workspace_documents.id` and the same `filename`. This:
- satisfies the chunks FK,
- lets the existing delete paths (`delete_embeddings_for_document`, `delete_by_workspace`) work unchanged,
- is what `delete_by_workspace` joins on (`chunks → documents → workspace_documents` via filename).

---

## 5. Authentication (Phase 2)

### 5.1 Flow

```
POST /auth/register  {email, password}  → 201 {access_token, token_type, user_id}
POST /auth/login     {email, password}  → 200 {access_token, token_type, user_id}
```

- Passwords hashed with **bcrypt** (`passlib`).
- JWT signed with **HS256** using `settings.SECRET_KEY`, expiry `settings.ACCESS_TOKEN_EXPIRE_DAYS` (7).
- Token payload: `{"sub": <user_id>, "exp": <timestamp>}`.
- Duplicate email → 400. Wrong password / unknown email → 401 (identical message, no user enumeration).

### 5.2 Protecting endpoints

`api/deps.py` provides:

```python
async def get_current_user(authorization: str = Header(None)) -> dict:
    # 1. require "Authorization: Bearer <jwt>"
    # 2. decode_token() → None on any error → 401
    # 3. load user by payload["sub"]; missing or is_active=0 → 401
    # 4. return the user row as a dict
```

Every Phase 2/3 endpoint depends on `get_current_user` and scopes data by `user["id"]`.

**Phase 1 endpoints** still use the legacy `X-API-Key` header (`verify_api_key`), which reads `settings.API_KEY`. These two auth systems are independent.

---

## 6. Multi-Tenancy Model

- Every tenant resource (`workspaces`, `workspace_documents`, `agents`, `conversations`) is owned by a `users.id`.
- **Ownership is always verified server-side** before any read/write. The `owner_id` is taken from the JWT, never from the request body.
- **Isolation rule:** a non-owner gets **404** (not 403) for workspace-scoped resources, so the existence of another tenant's data is not leaked. (Agent endpoints return 403 when the agent exists but belongs to a different workspace path — see §11.)
- **Retrieval is tenant-scoped:** vector + BM25 search filter on `chunks.workspace_id` AND require the source document `status = 'ready'`. A tenant can only ever retrieve their own trained content.

---

## 7. Document Ingestion & Training (Phase 2)

### 7.1 Upload

```
POST /workspaces/{id}/documents   (multipart, field name "file")
```

- Allowed extensions: `.pdf`, `.txt`, `.docx` → else 400.
- Saved to `uploads/{workspace_id}/{uuid}_{original_filename}` (root from `settings.UPLOAD_DIR`).
- Inserts a `workspace_documents` row with `status='uploaded'`, `chunk_count=0`.
- Returns the document dict (201).

### 7.2 Training pipeline

```
POST /workspaces/{id}/documents/{doc_id}/train   → 202 (background)
GET  /workspaces/{id}/documents/{doc_id}/status  → poll
```

`train_workspace_document(doc_id, db)` runs **as a FastAPI BackgroundTask** (the request returns immediately):

```
uploaded ──train──► processing ──► ready
                        └──────► failed
```

Steps (CPU-heavy work wrapped in `asyncio.to_thread`):

1. **Extract text** — `extract_text_from_file(path, type)`:
   - `pdf` → PyMuPDF (`load_pdf`)
   - `txt` → `open(..., encoding='utf-8', errors='ignore')`
   - `docx` → `python-docx` (`Document`, join `paragraphs`)
   - Returns `""` + logged warning on any failure.
2. **Chunk** — `chunk_document()` (word-based sliding window, `chunk_size=512`, `overlap=64`).
3. **Embed** — `embed_texts()` (sentence-transformers, L2-normalised).
4. **Store** — `index_chunks()` writes chunks + embeddings, tagging each chunk with `workspace_id` and `doc_id` (the metadata columns added in Phase 2).
5. **Mark ready** with `chunk_count`.

Re-training is idempotent: prior chunks/embeddings for the doc are cleared first. A `failed` document can be retrained; a `ready` one returns 200 "Already trained".

### 7.3 Config validation (Phase 3)

`core/agent_config.py` is the single source of truth for agent config rules (see §10). It is applied in `create_agent` / `update_agent`.

---

## 8. Retrieval Pipeline

Used by both workspace chat and agent chat. Scoped to a workspace.

```
message
  │
  ├─► embed_query(message)              (sentence-transformers, in a thread)
  │
  ▼
hybrid_search(db, query, query_vector, workspace_id=W)
  │
  ├─► BM25: build in-memory index over chunks WHERE workspace_id=W AND status='ready'
  │
  ├─► Vector: sqlite-vec KNN over chunk_embeddings, filtered to workspace_id=W
  │           (sqlite-vec can't filter by another table, so candidates are
  │            over-fetched and filtered in Python via a chunks join)
  │
  ▼
Reciprocal Rank Fusion (RRF, k=60) → fused ranking
  │
  ▼
rerank (cross-encoder, top_k=5) → final chunks
  │
  ▼
sources = [{filename, chunk_index}, ...]   (de-duplicated per file+chunk)
```

**Key detail:** retrieval only returns chunks whose `workspace_id = W` **and** whose source document `status = 'ready'`. Untrained / failed documents are invisible to chat.

---

## 9. Chat — Two Paths

### 9.1 Workspace chat (Phase 2)

`POST /workspaces/{id}/chat` → `query_workspace()`. Uses the **workspace's** `system_prompt`. Returns `{answer, sources, conversation_history}`.

### 9.2 Agent chat (Phase 3)

`POST /workspaces/{id}/agents/{agent_id}/chat` → `chat_with_agent()`. Uses the **agent's** own `system_prompt`, `model`, `temperature`, `language`. Returns `{conversation_id, answer, sources, model_used}`.

**Agent chat flow (10 steps):**

```
1. Load agent row (404 if missing) → system_prompt, model, temperature, language, workspace_id
2. Resolve conversation:
     conversation_id=None → create new (title "New Conversation")
     conversation_id given → must belong to this agent, else 404
3. Store user message
4. Build LLM history = all messages EXCEPT the just-stored user message
   (sliced off so the LLM call can append it without duplication)
5. Retrieve knowledge (hybrid search + rerank, workspace-scoped; empty is OK)
6. Assemble system prompt:
     agent.system_prompt
   + "Always respond in {language}."   (skipped if English/unset)
   + "Relevant knowledge:\n{context}"  (skipped if no context)
7. Call LLM with the agent's model + temperature (per-call overrides)
8. Store assistant message (+ sources as JSON in `citations`)
9. Auto-title if this was a new conversation
10. Return {conversation_id, answer, sources, model_used}
```

---

## 10. Agent Configuration (`core/agent_config.py`)

Purely functional — no DB, no FastAPI. Framework-agnostic.

```python
SUPPORTED_MODELS = {          # dict keyed by model id, metadata per entry
    "meta-llama/llama-3.3-70b-instruct:free": {"name": ..., "tier": "free", "max_tokens": 4096},
    "qwen/qwen3-235b-a22b:free":             {...},
    "google/gemma-3-27b-it:free":            {...},
    "openrouter/free":                       {...},
}
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"

MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 1.0
DEFAULT_TEMPERATURE = 0.7

SUPPORTED_LANGUAGES = ["English", "Swahili", "French", "Arabic", "Portuguese"]
DEFAULT_LANGUAGE = "English"
```

| Function | Behaviour |
|---|---|
| `is_model_allowed(m)` | membership check |
| `validate_temperature(v)` | **clamps** to [0,1], logs warning — never raises |
| `is_language_supported(l)` | case-insensitive |
| `get_agent_defaults()` | `{model, temperature, language, system_prompt}` |
| `validate_agent_config(name, system_prompt, model, temperature, language)` | returns clean storable dict |

**Validation rules:**
- **Hard** (raise `ValueError` → HTTP 422 in the service): empty name, name > 100 chars, empty system_prompt, system_prompt < 10 chars.
- **Soft** (fall back to default + log warning): unsupported model → `DEFAULT_MODEL`; unsupported language → `DEFAULT_LANGUAGE`; out-of-range temperature → clamped.

**Extensibility:** adding a paid model tier = new `SUPPORTED_MODELS` entries with `"tier": "paid"`. Adding a language = one list entry. Rate limits per tier can be added as model metadata and consumed by a future limiter without changing callers.

---

## 11. Full API Surface

### Phase 1 (legacy, `X-API-Key` header)
```
GET  /health
GET  /health/ready
POST /api/v1/query/
POST /api/v1/query/stream
GET  /api/v1/query/llm/status
GET  /api/v1/query/conversations/{id}
POST /api/v1/documents/upload
GET  /api/v1/documents/
GET  /api/v1/documents/{id}
DELETE /api/v1/documents/{id}
```

### Phase 2 (JWT)
```
POST /auth/register
POST /auth/login

POST   /workspaces
GET    /workspaces
GET    /workspaces/{workspace_id}
PUT    /workspaces/{workspace_id}
DELETE /workspaces/{workspace_id}

POST   /workspaces/{workspace_id}/documents
GET    /workspaces/{workspace_id}/documents
DELETE /workspaces/{workspace_id}/documents/{doc_id}
POST   /workspaces/{workspace_id}/documents/{doc_id}/train
GET    /workspaces/{workspace_id}/documents/{doc_id}/status
POST   /workspaces/{workspace_id}/chat
```

### Phase 3 (JWT)
```
POST   /workspaces/{workspace_id}/agents
GET    /workspaces/{workspace_id}/agents
GET    /workspaces/{workspace_id}/agents/{agent_id}
PUT    /workspaces/{workspace_id}/agents/{agent_id}
DELETE /workspaces/{workspace_id}/agents/{agent_id}

POST   /workspaces/{workspace_id}/agents/{agent_id}/chat
POST   /workspaces/{workspace_id}/agents/{agent_id}/conversations/new
GET    /workspaces/{workspace_id}/agents/{agent_id}/conversations
GET    /workspaces/{workspace_id}/agents/{agent_id}/conversations/{conversation_id}
DELETE /workspaces/{workspace_id}/agents/{agent_id}/conversations/{conversation_id}
```

**Status code cheat-sheet:** 201 create · 202 training accepted · 204 delete · 400 bad file type · 401 unauthenticated · 403 wrong workspace path · 404 missing / not-owned · 422 validation.

---

## 12. Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | `change-this-in-production` | JWT signing — **change in prod** |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_DAYS` | `7` | token lifetime |
| `API_KEY` | `dev-key` | Phase 1 `X-API-Key` |
| `DATABASE_URL` | `sqlite:///./data/rag.db` | main DB |
| `UPLOAD_DIR` | `./uploads` | Phase 2 workspace uploads root |
| `upload_dir` | `./data/uploads` | Phase 1 legacy uploads |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | embedding model |
| `EMBEDDING_DIMENSION` | `384` | embedding size |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | reranker |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `512` / `64` | chunking |
| `RETRIEVAL_TOP_K` / `RERANK_TOP_K` / `RRF_K` | `20` / `5` / `60` | retrieval |
| `OPENROUTER_API_KEY` | — | **required for chat** |
| `OPENROUTER_MODEL` | `inclusionai/ling-3.0-flash-fin:free` | primary LLM |
| `LLM_FALLBACK_MODEL` | `openrouter/free` | fallback on retryable failure |
| `LLM_MAX_TOKENS` | `4096` | max output tokens |
| `LLM_TEMPERATURE` | `0.1` | default LLM temperature |

**Gotcha:** `UPLOAD_DIR` (Phase 2) and `upload_dir` (Phase 1) differ only by case. pydantic-settings matches env vars case-insensitively, so setting `UPLOAD_DIR` in `.env` feeds **both** fields. Be aware when configuring.

---

## 13. LLM Layer & Model Fallback

`OpenRouterGenerator` (the sole LLM backend) calls OpenRouter's OpenAI-compatible `/chat/completions`.

**Per-call overrides** (added for agents): `generate(query, context, system_prompt=None, history=None, model=None, temperature=None)`. When omitted, instance defaults (from settings) are used — so Phase 1/2 behaviour is unchanged.

**Model fallback:** if the primary model fails for a **retryable** reason, the request is retries once against `LLM_FALLBACK_MODEL`:

| Primary failure | Fallback? |
|---|---|
| 404, 408, 425, 429, 500, 502, 503, 504 | yes |
| network / transport error | yes |
| empty / malformed / truncated response | yes |
| **401** bad key | no (account-level) |
| **402** no credits | no (account-level) |

The actually-used model is tracked on `llm.last_model_used` and returned by agent chat as `model_used`.

**Streaming** only falls back if no token has been emitted yet (avoids duplicating text mid-answer).

---

## 14. Key Design Decisions & Gotchas

1. **Shared `conversations`/`messages`** across phases. Agent conversations are rows with non-NULL `agent_id`. Don't add a separate table.
2. **`messages.citations` is the single source field** for both phases. `Citation` (in `models/query.py`) carries `chunk_id`, optional `page`, `text_preview`, and optional `filename`/`chunk_index`. Old rows deserialise with `filename=None`.
3. **Schema migrations are additive.** `init_db()` uses `CREATE TABLE IF NOT EXISTS` for new tables and PRAGMA-guarded `ALTER TABLE ADD COLUMN` for existing ones. Never rewrite existing tables.
4. **`PRAGMA foreign_keys=ON`** is set per-connection in `get_db()` and `init_db()`. SQLite defaults it OFF — any new raw connection must repeat it or cascades won't fire.
5. **BackgroundTasks for training.** The train endpoint returns 202 immediately; training runs after the response. The service opens its own DB connection when none is passed (the request's connection is closed by then).
6. **Ownership 404 vs 403.** Workspace-scoped resources return 404 for non-owners (no existence leak). Agent endpoints return 403 when the agent exists but the workspace path doesn't match.
7. **`asyncio.to_thread`** wraps all CPU-heavy work (embedding, chunking, extraction, reranking) so the event loop stays responsive.
8. **Config validation is framework-agnostic.** `agent_config.py` raises `ValueError`; the service layer converts to HTTP 422.

---

## 15. Running & Testing

```bash
cd /home/jteckz7/Xvec-chat
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt

# configure
cp .env.example .env   # set OPENROUTER_API_KEY

# run
cd backend
../.venv/bin/uvicorn app.main:app --port 8000

# docs
open http://localhost:8000/docs
```

**Automated tests:**
```bash
cd backend
../.venv/bin/python -m pytest app/tests -q
```
Expected: `12 passed, 4 skipped` + 1 known pre-existing failure (`test_api_query` — a LangGraph `'citations' is already being used as a state key` issue in the Phase 1 pipeline, unrelated to Phase 2/3).

**Manual smoke:** register → create workspace → upload PDF → train → poll status → create agent → chat. A full worked example with exact request/response bodies is in `phase2.md` (§11) and `firstTest.md`.

---

## 16. Known Issues / Cleanup Backlog

| Issue | Impact | Status |
|---|---|---|
| Phase 1 `/api/v1/query/` returns 500 | LangGraph state-key conflict (`'citations'`) | Pre-existing; workspace/agent chat are the working paths |
| Deleted docs may appear in legacy `GET /api/v1/documents/` | shadow `documents` row survives | Cosmetic; harmless to Phase 2/3 chat |
| `UPLOAD_DIR` / `upload_dir` case-collision | setting one feeds both | Documented in §12 |

---

## 17. Guidance for the Next Phase

When building Phase 4+, keep these invariants:

- **New tenant resources** go under a workspace and verify ownership via `get_current_user` + a workspace ownership check.
- **New tables** are created in `init_db()`; new columns on existing tables use the PRAGMA-guarded `ALTER TABLE` pattern (see `_add_columns_if_missing`).
- **Agent config rules** belong in `core/agent_config.py`, not inline in services.
- **LLM calls** go through `build_generator()` and accept per-call `model`/`temperature`/`system_prompt`/`history` — don't hardcode.
- **Retrieval** must stay workspace-scoped (`workspace_id` + `status='ready'`).
- **Sources** are stored in `messages.citations` as a JSON array of `Citation` — don't add a parallel field.
