# Production RAG with Citations

> PDF Q&A bot with hybrid search, cross-encoder reranking, grounding, and page-level citations.
> Built with LangGraph + FastAPI + SQLite-vec + React + Vite + Ollama / OpenVINO.

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
                    │                    │Indexer   │       │ generate_node     │ ← Ollama / OpenVINO / mock
                    │                    └──────────┘       │ citation_node     │ ← Page refs
                    │                          │            └───────────────────┘
                    │                          ▼                     │
                    │                    SQLite + SQLite-vec ◄───────┘
                    │
                    └── chat streams back token-by-token (SSE)
```

### LLM backends (`LLM_PROVIDER` in `.env`)

| Provider | How it runs | RAM (≈) | When to use |
|----------|-------------|---------|-------------|
| `ollama` (default) | Local Ollama server (`:11434`), e.g. `qwen2.5:3b` | ~2.5 GB (3B) / ~5 GB (7B) | Default dev setup |
| `openvino` | INT4 OpenVINO IR on CPU/iGPU, no Ollama needed | ~2 GB (3B INT4) / ~4–5 GB (7B INT4) | Lowest memory footprint |
| `mock` | Deterministic stub answer | ~0 | Unit tests / UI dev without models |

> ⚠️ **Model-size warning (measured on an 11 GB RAM, i5-8250U box):**
> Qwen2.5 sizes are **0.5 / 1.5 / 3 / 7 / 14 / 32 / 72B — there is no `qwen2.5:35b`**
> (that name means the 32B variant). A 32B Q4 model needs **~20 GB RAM**
> (~18 GB+ even as OpenVINO INT4) and will push this machine to **90%+ RAM,
> hang, and never answer**. Stay on **3B** (comfortable) or **7B max**.

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
| LLM (default) | Qwen2.5 via Ollama |
| LLM (low-RAM) | Qwen2.5-Instruct INT4 via OpenVINO |
| Frontend | React 18 + Vite + TypeScript |
| Containerisation | Docker + docker-compose |

---

## Quick Start

### Prerequisites

- Python 3.11+ (3.10–3.13 if you plan to use the OpenVINO backend — OpenVINO
  does not publish wheels for every brand-new Python release)
- Node.js 20+
- [Ollama](https://ollama.ai) running locally (only for `LLM_PROVIDER=ollama`)
- ~4 GB free RAM for the 3B models (see table above)

### 1. Clone and setup

```bash
git clone <repo>
cd production-rag
bash scripts/setup.sh        # backend .venv + frontend node_modules + data dirs
```

### 2. Start Ollama + pull a model (skip if using OpenVINO — see below)

```bash
ollama serve
ollama pull qwen2.5:3b       # recommended here; 7B max on 11 GB RAM
ollama list                  # confirm what you have
```

> `OLLAMA_MODEL` in `.env` must match one of these names exactly.

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

Ollama is commented out in `docker-compose.yml` by default — uncomment the
`ollama` service to run it containerised, and point `OLLAMA_BASE_URL` at it.

---

## Project Structure

```
production-rag/
├── .env                        # backend config (API key, LLM, CORS, chunking…)
├── backend/
│   ├── requirements-openvino.txt   # optional OpenVINO deps (NOT installed by default)
│   └── app/
│       ├── api/          # HTTP endpoints (upload, query, health)
│       ├── core/         # Config, logging, database init
│       ├── ingestion/    # PDF → chunks → embeddings → index
│       ├── retrieval/    # BM25, vector, hybrid (RRF), reranker
│       ├── graph/        # LangGraph state, nodes, workflow
│       ├── llm/          # Prompts + generators (ollama / openvino / mock)
│       ├── services/     # Business logic (document & query)
│       ├── models/       # Pydantic schemas
│       ├── storage/      # SQLite + sqlite-vec adapters
│       └── tests/        # Unit + integration tests
├── frontend/src/
│   ├── components/   # FileUploader, DocumentList, ChatWindow, ChatMessage, ChatInput
│   ├── hooks/        # useChat (streaming), useDocuments
│   ├── api/          # Typed API client (all HTTP goes through here)
│   └── types/        # TypeScript interfaces
├── models/             # OpenVINO IR downloads (created by the download script)
├── data/               # uploads/, processed/, embeddings/
├── docker/             # Dockerfiles + docker-compose + nginx
└── scripts/            # setup.sh, test.sh, ingest_sample.py, download_openvino_model.py
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
# {"provider":"ollama","ok":true,"configured_model":"qwen2.5:3b",
#  "reachable":true,"model_available":true,
#  "available_models":["qwen2.5:7b","qwen2.5:3b","llama3.2:3b"]}
```

If `"ok": false`, the `"error"` field tells you the exact fix
(e.g. ``ollama pull qwen2.5:3b``). The chat UI now surfaces these errors
instead of showing an empty bubble.

---

## Running Tests

```bash
bash scripts/test.sh
# Or directly:
cd backend
LLM_PROVIDER=mock PYTHONPATH=. .venv/bin/python -m pytest app/tests/ -v
```

Tests use `MockGenerator`, so no Ollama/OpenVINO is needed. (The full suite
loads the embedding model once — expect ~40 s on first run.)

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
| `LLM_PROVIDER` | `ollama` | `ollama`, `openvino`, or `mock` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server address |
| `OLLAMA_MODEL` | `qwen2.5:3b` | Must be pulled (`ollama list`); no `35b` exists |
| `OLLAMA_TIMEOUT` | `300` | Seconds to wait for Ollama per request (120 was too short for CPU inference) |
| `OLLAMA_NUM_CTX` | `4096` | Context window (`num_ctx`) — smaller = less RAM, faster first token |
| `OLLAMA_KEEP_ALIVE` | `5m` | Keep model resident between requests |
| `LLM_MAX_TOKENS` | `512` | Max generated tokens per answer |
| `LLM_TEMPERATURE` | `0.1` | Sampling temperature |
| `OPENVINO_MODEL_ID` | `OpenVINO/Qwen2.5-3B-Instruct-int4-ov` | HF ID or local IR dir (used when `LLM_PROVIDER=openvino`) |
| `OPENVINO_DEVICE` | `CPU` | `CPU`, `GPU` (Intel iGPU), or `AUTO` |
| `OPENVINO_MAX_NEW_TOKENS` | `512` | Max generated tokens (OpenVINO path) |
| `ALLOWED_ORIGINS` | localhost/127.0.0.1/192.168.1.27 `:5173`/`:3000` | Explicit CORS origins (a LAN regex in `main.py` also covers any `192.168.x.x`/`10.x.x.x`) |

### Frontend — `frontend/.env`

| Variable | Value | Description |
|----------|-------|-------------|
| `VITE_API_URL` | `/api/v1` | **Relative** → same-origin via Vite proxy (works on localhost *and* any LAN IP, no CORS). Only use an absolute URL (`http://<ip>:8000/api/v1`) if you bypass the proxy. |
| `VITE_API_KEY` | must match backend `API_KEY` | Sent as `X-API-Key` |

---

## Model Setup

### Option A — Ollama (default, simplest)

```bash
ollama serve
ollama pull qwen2.5:3b
# .env: LLM_PROVIDER=ollama / OLLAMA_MODEL=qwen2.5:3b
```

Lower `OLLAMA_NUM_CTX` (e.g. `2048`) and `LLM_MAX_TOKENS` if RAM is tight;
raise `OLLAMA_TIMEOUT` if big models answer slowly.

### Option B — OpenVINO (lowest memory, no Ollama at runtime)

OpenVINO runs a **pre-quantized INT4** model in IR format — it cannot use
Ollama's GGUF files. Use the ready-made INT4 repos (no conversion needed):

| Model | RAM | Verdict on 11 GB machine |
|-------|-----|--------------------------|
| `OpenVINO/Qwen2.5-3B-Instruct-int4-ov` | ~2 GB | ✅ recommended |
| `OpenVINO/Qwen2.5-7B-Instruct-int4-ov` | ~4–5 GB | ⚠️ max, close other apps |
| any 32B IR | ~18 GB+ | ❌ still OOMs — do not use |

```bash
# 1. Python 3.10–3.13 venv (OpenVINO wheels), then:
pip install -r backend/requirements-openvino.txt

# 2. Download the INT4 IR (~2 GB for 3B):
python scripts/download_openvino_model.py
# (7B: python scripts/download_openvino_model.py --model OpenVINO/Qwen2.5-7B-Instruct-int4-ov)

# 3. .env:
LLM_PROVIDER=openvino
OPENVINO_MODEL_ID=./models/qwen2.5-3b-instruct-int4-ov
OPENVINO_DEVICE=CPU        # or GPU for Intel iGPU, AUTO to let OpenVINO decide

# 4. Restart backend, then verify:
curl http://localhost:8000/api/v1/query/llm/status -H "X-API-Key: dev-key"
# {"provider":"openvino","ok":true,...}
```

First OpenVINO answer compiles/optimises the graph — expect a slow first
request, then fast ones (the model stays cached in-process). `nncf` is only
needed if you quantize your own model; skip it for the `-int4-ov` repos.

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
To add a new backend:

```python
# backend/app/llm/generator.py
class MyNewGenerator(LLMGenerator):
    async def generate(self, query: str, context: str) -> str:
        # Call your API here
        ...

    async def check_health(self) -> dict:
        return {"provider": "mynew", "ok": True}

# Add to build_generator():
elif p == "mynew":
    return MyNewGenerator()
```

Then set `LLM_PROVIDER=mynew` in `.env`.

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
   - `"reachable": false` → `ollama serve` isn't running.
   - `"model_available": false` → run `ollama pull <OLLAMA_MODEL>`.
   - `"ok": false` → read `"error"`; the UI now shows this text.
2. Check the backend terminal: Ollama errors are logged with actionable hints.
3. A **32B/“35b” model on ~11 GB RAM** is the classic cause: RAM spikes to
   90%+, generation stalls past the timeout, and nothing arrives. Use
   `qwen2.5:3b` (or 7B max), or switch to the OpenVINO INT4 3B model.
4. Slow first answer is normal: embedding + reranker + LLM weights load
   lazily (~30–90 s on CPU). Watch the logs, not just the UI.

### RAM spikes to 90%+ during generation

- The model is too big for the machine — drop to `qwen2.5:3b` or
  `LLM_PROVIDER=openvino` with the 3B INT4 IR (~2 GB).
- Reduce `OLLAMA_NUM_CTX` (2048) and `LLM_MAX_TOKENS` (256–512): the KV-cache
  scales with context × output length.
- Note the backend also holds the embedding model (~90 MB), the reranker,
  and a CUDA build of torch — some baseline usage is expected. `OLLAMA_KEEP_ALIVE=0`
  unloads the LLM between requests at the cost of reload latency.

### OpenVINO issues

- `OpenVINO dependencies are not installed` → `pip install -r backend/requirements-openvino.txt`
  in a Python 3.10–3.13 venv.
- `has no OpenVINO IR (*.xml)` → run `python scripts/download_openvino_model.py`.
- Empty/slow answers → first request compiles the graph; check RAM (use the
  3B model) and that `OPENVINO_MODEL_ID` points at an `-int4-ov` repo/dir.
- GGUF files (`.gguf` from Ollama) will **never** load in OpenVINO — that is
  expected; download the IR instead.

---

Built by **Sam** · Dar es Salaam Institute of Technology · 2025
