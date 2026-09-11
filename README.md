# Production RAG with Citations

> PDF Q&A bot with hybrid search, cross-encoder reranking, grounding, and page-level citations.
> Built with LangGraph + FastAPI + SQLite-vec + React + Vite.

---

## Architecture

```
                 User
                   │
                   ▼
              FastAPI (HTTP, auth, CORS)
                   │
       ┌───────────┴───────────┐
       ▼                       ▼
  Ingestion API           Query API
       │                       │
       ▼                       ▼
  PDF Pipeline          LangGraph Workflow
  ┌──────────┐         ┌─────────────────┐
  │PyMuPDF   │         │ retrieve_node   │ ← Hybrid BM25 + vector (RRF)
  │Chunker   │         │ rerank_node     │ ← CrossEncoder
  │Embedder  │         │ grounding_node  │ ← Verify context
  │Indexer   │         │ generate_node   │ ← Llama LLM
  └──────────┘         │ citation_node   │ ← Extract page refs
       │               └─────────────────┘
       ▼                       │
  SQLite + SQLite-vec ◄────────┘
       │
       ▼
      LLM (Ollama / Llama)
```

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
| LLM | Llama 3.2 via Ollama |
| Frontend | React 18 + Vite + TypeScript |
| Containerisation | Docker + docker-compose |

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+
- [Ollama](https://ollama.ai) running locally

### 1. Clone and setup
```bash
git clone <repo>
cd production-rag
bash scripts/setup.sh
```

### 2. Start Ollama + pull model
```bash
ollama serve
ollama pull llama3.2
```

### 3. Start backend
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### 4. Start frontend
```bash
cd frontend
npm run dev
# → http://localhost:5173
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

---

## Project Structure

```
production-rag/
├── backend/app/
│   ├── api/          # HTTP endpoints (upload, query, health)
│   ├── core/         # Config, logging, database init
│   ├── ingestion/    # PDF → chunks → embeddings → index
│   ├── retrieval/    # BM25, vector, hybrid (RRF), reranker
│   ├── graph/        # LangGraph state, nodes, workflow
│   ├── llm/          # Prompts + Ollama/mock generator
│   ├── services/     # Business logic (document & query)
│   ├── models/       # Pydantic schemas
│   ├── storage/      # SQLite + sqlite-vec adapters
│   └── tests/        # Unit + integration tests
├── frontend/src/
│   ├── components/   # FileUploader, DocumentList, ChatWindow, ChatMessage, ChatInput
│   ├── hooks/        # useChat (streaming), useDocuments
│   ├── api/          # Typed API client
│   └── types/        # TypeScript interfaces
├── data/             # uploads/, processed/, embeddings/
├── docker/           # Dockerfiles + docker-compose + nginx
└── scripts/          # setup.sh, test.sh, ingest_sample.py
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

---

## Running Tests
```bash
bash scripts/test.sh
# Or directly:
cd backend
LLM_PROVIDER=mock pytest app/tests/ -v
```

---

## Configuration (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | `dev-key` | Authentication key for all API endpoints |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | SentenceTransformers model name |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | CrossEncoder model |
| `CHUNK_SIZE` | `512` | Tokens per chunk |
| `CHUNK_OVERLAP` | `64` | Overlap tokens between chunks |
| `RETRIEVAL_TOP_K` | `20` | Candidates from hybrid search |
| `RERANK_TOP_K` | `5` | Final chunks after reranking |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model to use |
| `LLM_PROVIDER` | `ollama` | `ollama` or `mock` |

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

The `LLMGenerator` is an abstract base class. To add a new backend:

```python
# backend/app/llm/generator.py
class MyNewGenerator(LLMGenerator):
    async def generate(self, query: str, context: str) -> str:
        # Call your API here
        ...

# Add to build_generator():
elif p == "mynew":
    return MyNewGenerator()
```

Then set `LLM_PROVIDER=mynew` in `.env`.

---

Built by **Sam** · Dar es Salaam Institute of Technology · 2025
