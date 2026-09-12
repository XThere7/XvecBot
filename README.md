# Production RAG with Citations

> PDF Q&A bot with hybrid search, cross-encoder reranking, grounding, and page-level citations.
> Built with LangGraph + FastAPI + SQLite-vec + React + Vite.
> Sole LLM engine: OpenRouter cloud API (`inclusionai/ling-3.0-flash-fin:free`).

---

## Architecture

```
                 User (browser, e.g. http://192.168.1.27:5173)
                    │
                    ▼  same-origin /api/*  (Vite dev proxy → no CORS)
               Vite dev server (:5173) ──proxy──▶ FastAPI (:8000)
                    │                                    │
                    │                          ┌─────────┴───────────┐
                    │                          ▼                     ▼
                    │                    Ingestion API           Query API
                    │                          │                     │
                    │                          ▼                     ▼
                    │                    PDF Pipeline        LangGraph Workflow
                    │                    ┌──────────┐       ┌───────────────────┐
                    │                    │PyMuPDF   │       │ retrieve_node     │ ← Hybrid BM25 + vector (RRF)
                    │                    │Chunker   │       │ rerank_node       │ ← CrossEncoder
                    │                    │Embedder  │       │ grounding_node    │ ← Verify context
                    │                    │Indexer   │       │ generate_node     │ ← OpenRouter (cloud)
                    │                    └──────────┘       │ citation_node     │ ← Page refs
                    │                          │            └───────────────────┘
                    │                          ▼                     │
                    │                    SQLite + SQLite-vec ◄───────┘
                    │
                    └── chat streams back token-by-token (SSE)
```

### LLM backend: OpenRouter (only provider)

All generation goes through the OpenAI-compatible chat-completions endpoint:

```
POST https://openrouter.ai/api/v1/chat/completions
```

There are no local inference backends and no provider switching — `build_generator()`
returns an `OpenRouterGenerator` unconditionally. (`MockGenerator` exists only as a
test stub and is never wired into the app.)

## Stack

| Layer | Technology |
|-------|-----------|
| Backend framework | FastAPI |
| AI pipeline | LangGraph |
| PDF extraction | PyMuPDF |
| Embeddings | SentenceTransformers (all-MiniLM-L6-v2) |
| Reranker | CrossEncoder (ms-marco-MiniLM-L-6-v2) |
| Keyword search | BM25 (rank-bm25) |
| Relational DB | SQLite + aiosqlite |
| Vector DB | sqlite-vec |
| LLM | OpenRouter cloud API (`inclusionai/ling-3.0-flash-fin:free`) via httpx |
| Frontend | React 18 + Vite + TypeScript |
| Containerisation | Docker + docker-compose |

---

## Quick Start

### Prerequisites

- Python 3.10–3.13
- Node.js 20+
- An OpenRouter API key (see below) — no local model, no GPU, no ~20 GB download

### 1. Clone and setup

```bash
git clone <repo>
cd production-rag
bash scripts/setup.sh        # backend .venv + frontend node_modules + data dirs
```

### 2. Getting Your OpenRouter API Key

1. Go to [https://openrouter.ai/keys](https://openrouter.ai/keys) and sign in.
2. Click **Create API Key**, give it a name (e.g. `rag-project`), and copy the key
   (it starts with `sk-or-v1-...`). Top up credits if needed at
   [https://openrouter.ai/credits](https://openrouter.ai/credits) — the
   `inclusionai/ling-3.0-flash-fin:free` model is free, but an account is still required.
3. Paste it into `.env`:

```bash
OPENROUTER_API_KEY=sk-or-v1-paste-your-key-here
```

### 3. Start backend

```bash
cd backend
source .venv/bin/activate
python -u -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
```

### 4. Start frontend (new terminal — Vite bakes `.env` at startup, so restart it after any `.env` change)

```bash
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173
# → local:  http://localhost:5173
# → LAN:    http://<your-ip>:5173   (e.g. http://192.168.1.27:5173)
```

### 5. API docs

```
http://localhost:8000/docs
```

---

## Docker (full stack)

```bash
cd docker
docker-compose up --build
# → Frontend: http://localhost:80
# → API:      http://localhost:8000
```

Make sure `OPENROUTER_API_KEY` is set in the root `.env` (it is passed through via `env_file`).

---

## Project Structure

```
production-rag/
├── .env                        # backend config (API key, OpenRouter, CORS, chunking…)
├── .env.example                # template — copy to .env and fill in OPENROUTER_API_KEY
├── backend/
│   └── app/
│       ├── api/          # HTTP endpoints (upload, query, health)
│       ├── core/         # Config, logging, database init
│       ├── ingestion/    # PDF → chunks → embeddings → index
│       ├── retrieval/    # BM25, vector, hybrid (RRF), reranker
│       ├── graph/        # LangGraph state, nodes, workflow
│       ├── llm/          # Prompts + OpenRouter generator (+ Mock stub for tests)
│       ├── services/     # Business logic (document & query)
│       ├── models/       # Pydantic schemas
│       ├── storage/      # SQLite + sqlite-vec adapters
│       └── tests/        # Unit + integration tests
├── frontend/src/
│   ├── components/   # FileUploader, DocumentList, ChatWindow, ChatMessage, ChatInput
│   ├── hooks/        # useChat (streaming), useDocuments
│   ├── api/          # Typed API client (all HTTP goes through here)
│   └── types/        # TypeScript interfaces
├── data/               # uploads/, processed/, embeddings/
├── docker/             # Dockerfiles + docker-compose + nginx
└── scripts/            # setup.sh, test.sh, ingest_sample.py
```

---

## API Reference

### Upload a document

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "X-API-Key: dev-key" \
  -F "file=@paper.pdf"
```

### Ask a question

```bash
curl -X POST http://localhost:8000/api/v1/query/ \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the main findings?", "document_id": "<id>"}'
```

### Stream an answer (SSE)

```bash
curl -X POST http://localhost:8000/api/v1/query/stream \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"question": "Summarise page 3"}' \
  --no-buffer
```

### LLM diagnostics — check this first when chat returns no text

```bash
curl http://localhost:8000/api/v1/query/llm/status -H "X-API-Key: dev-key"
# {"provider":"openrouter","ok":true,
#  "model":"inclusionai/ling-3.0-flash-fin:free",...}
```

If `"ok": false`, the `"error"` field tells you the exact fix
(e.g. missing/invalid key, no credits, rate limit, bad model ID). The chat UI
surfaces these errors instead of showing an empty bubble.

---

## Running Tests

```bash
bash scripts/test.sh
# Or directly:
cd backend
PYTHONPATH=. .venv/bin/python -m pytest app/tests/ -v
```

Tests use `MockGenerator`, so no OpenRouter API key is needed.

---

## Configuration (.env)

### Backend — project root `.env`

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | `dev-key` | Auth key for all API endpoints (send as `X-API-Key`) |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | SentenceTransformers model |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | CrossEncoder model |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `512` / `64` | Chunking (tokens) |
| `RETRIEVAL_TOP_K` / `RERANK_TOP_K` | `20` / `5` | Hybrid candidates / final chunks |
| `OPENROUTER_API_KEY` | _(empty — you fill it in)_ | **Required.** Secret key from https://openrouter.ai/keys. Missing key raises a clear error on first request, never on import |
| `OPENROUTER_MODEL` | `inclusionai/ling-3.0-flash-fin:free` | Model ID sent to OpenRouter |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter API base URL |
| `LLM_MAX_TOKENS` | `512` | Max generated tokens per answer |
| `LLM_TEMPERATURE` | `0.1` | Sampling temperature |
| `ALLOWED_ORIGINS` | localhost/127.0.0.1/192.168.1.27 `:5173`/`:3000` | Explicit CORS origins (a LAN regex in `main.py` also covers any `192.168.x.x`/`10.x.x.x`) |

### Frontend — `frontend/.env`

| Variable | Value | Description |
|----------|-------|-------------|
| `VITE_API_URL` | `/api/v1` | **Relative** → same-origin via Vite proxy (works on localhost *and* any LAN IP, no CORS). Only use an absolute URL (`http://<ip>:8000/api/v1`) if you bypass the proxy. |
| `VITE_API_KEY` | must match backend `API_KEY` | Sent as `X-API-Key` |

---

## Model Setup

There is no local model to download. The backend calls OpenRouter over HTTPS:

1. Create a key at [https://openrouter.ai/keys](https://openrouter.ai/keys).
2. Set in `.env`:
   ```env
   OPENROUTER_API_KEY=sk-or-v1-...
   OPENROUTER_MODEL=inclusionai/ling-3.0-flash-fin:free
   OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
   ```
3. Restart the backend, then verify:
   ```bash
   curl http://localhost:8000/api/v1/query/llm/status -H "X-API-Key: dev-key"
   # {"provider":"openrouter","ok":true,...}
   ```

To switch models, change `OPENROUTER_MODEL` to any ID listed at
[https://openrouter.ai/models](https://openrouter.ai/models) and restart.

---

## How Citations Work

1. **PyMuPDF** extracts text page-by-page; each page's number (1-indexed) is stored with its text.
2. **Chunker** splits pages into overlapping chunks; each chunk carries its `page` field.
3. **Page number travels** through retrieval → reranking unchanged.
4. **Prompt** prepends `[Page N]` to each context chunk so the LLM can reference pages naturally.
5. **citation_node** de-duplicates page numbers from the top-K reranked chunks and returns them as structured `Citation` objects in the API response.
6. **Frontend** renders citations as clickable chips below each assistant message, with the chunk text preview on hover.

---

## Switching the LLM

The `LLMGenerator` is an abstract base class (`generate` + `stream`).
The production backend is `OpenRouterGenerator`
(`backend/app/llm/openrouter_generator.py`), returned unconditionally by
`build_generator()`. To point at a different OpenRouter model, just change
`OPENROUTER_MODEL` — no code changes needed.

---

## Troubleshooting

### Upload fails: `CORS Missing Allow Origin` / `NetworkError when attempting to fetch resource`

Root cause we fixed: the page was served from `http://192.168.1.27:5173`
but `VITE_API_URL` pointed at `http://127.0.0.1:8000` — a different origin
(and on any other LAN device, `127.0.0.1` is *itself*, not your server),
while the backend allow-list only contained `localhost:5173`.

Current setup avoids this two ways:

1. `frontend/.env` uses `VITE_API_URL=/api/v1` → requests stay same-origin
   and Vite proxies `/api/*` + `/health` to `127.0.0.1:8000` (see
   `frontend/vite.config.ts`). No cross-origin request → no CORS at all,
   on localhost or any LAN IP.
2. Belt-and-braces: `ALLOWED_ORIGINS` lists all dev origins and
   `backend/app/main.py` adds an `allow_origin_regex` covering any
   `192.168.x.x` / `10.x.x.x` / `172.16.x.x` host, so direct absolute-URL
   access also passes preflight.

Remember: **restart Vite after changing `frontend/.env`** (values are baked
at startup), and tighten the origins for production.

### Chat returns no text (empty assistant bubble)

1. Check diagnostics: `GET /api/v1/query/llm/status` (see API Reference).
   - `"OPENROUTER_API_KEY is not set"` → paste your key into `.env` and restart.
   - `HTTP 401` → bad/revoked key — create a new one at https://openrouter.ai/keys.
   - `HTTP 402` → no credits — top up at https://openrouter.ai/credits.
   - `HTTP 429` → rate-limited — wait and retry.
   - `HTTP 404` → bad `OPENROUTER_MODEL` ID.
   - The UI shows this error text directly.
2. Check the backend terminal: LLM errors are logged with actionable hints.
3. Slow first answer is normal on a cold start: the embedding + reranker weights
   load lazily (~30–90 s on CPU). Watch the logs, not just the UI.

---

Built by **Sam** · Dar es Salaam Institute of Technology · 2025
