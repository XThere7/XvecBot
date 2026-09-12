/**
 * api/client.ts
 * Typed API client — all HTTP calls go through here, never scattered fetch() calls.
 * Uses the X-API-Key header for authentication.
 */
import type {
  Document,
  QueryRequest,
  QueryResponse,
  StreamEvent,
  UploadResponse,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "/api/v1";
const API_KEY = import.meta.env.VITE_API_KEY ?? "dev-key";

/** Derive server root (scheme+host, no /api/v1 suffix) for /health checks. */
function serverRoot(): string {
  // Relative BASE_URL (e.g. "/api/v1") → same origin, just use "" so "/health" is same-origin too.
  if (BASE_URL.startsWith("/")) return "";
  // Absolute BASE_URL (e.g. "http://192.168.1.27:8000/api/v1") → strip trailing /api/v1.
  return BASE_URL.replace(/\/api\/v1\/?$/, "");
}

const headers = (): HeadersInit => ({
  "X-API-Key": API_KEY,
  "Content-Type": "application/json",
});

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ── Documents ─────────────────────────────────────────────────────────────────

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/documents/upload`, {
    method: "POST",
    headers: { "X-API-Key": API_KEY },
    body: form,
  });
  return handleResponse<UploadResponse>(res);
}

export async function listDocuments(): Promise<Document[]> {
  const res = await fetch(`${BASE_URL}/documents/`, { headers: headers() });
  const data = await handleResponse<{ documents: Document[]; total: number }>(res);
  return data.documents;
}

export async function deleteDocument(id: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/documents/${id}`, {
    method: "DELETE",
    headers: headers(),
  });
  if (!res.ok && res.status !== 204) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
}

// ── Query (non-streaming) ─────────────────────────────────────────────────────

export async function queryDocuments(req: QueryRequest): Promise<QueryResponse> {
  const res = await fetch(`${BASE_URL}/query/`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(req),
  });
  return handleResponse<QueryResponse>(res);
}

// ── Query (SSE streaming) ─────────────────────────────────────────────────────

export function streamQuery(
  req: QueryRequest,
  onToken: (token: string) => void,
  onDone: (event: StreamEvent) => void,
  onError: (err: Error) => void
): () => void {
  const controller = new AbortController();

  (async () => {
    let tokensReceived = 0;
    let doneReceived = false;
    try {
      const res = await fetch(`${BASE_URL}/query/stream`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify(req),
        signal: controller.signal,
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;
          const event: StreamEvent = JSON.parse(raw);
          if (event.error) {
            // Backend LLM failure (bad key / no credits / rate limit / bad model).
            // Surface it instead of leaving an empty assistant bubble.
            throw new Error(event.error);
          }
          if (event.done) {
            doneReceived = true;
            onDone(event);
          } else if (event.token) {
            tokensReceived += 1;
            onToken(event.token);
          }
        }
      }

      if (!doneReceived && !controller.signal.aborted) {
        throw new Error(
          tokensReceived === 0
            ? "The assistant returned no response. The OpenRouter API key may be missing/invalid, out of credits, or rate-limited — check backend logs and GET /api/v1/query/llm/status."
            : "The response stream ended unexpectedly before completing."
        );
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        onError(err as Error);
      }
    }
  })();

  // Return cancel function
  return () => controller.abort();
}

// ── Health ────────────────────────────────────────────────────────────────────

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${serverRoot()}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

export interface LlmStatus {
  provider: string;
  ok: boolean;
  model?: string;
  base_url?: string;
  error?: string;
  [key: string]: unknown;
}

/** Query GET /api/v1/query/llm/status — call this when chat returns no text. */
export async function checkLlmStatus(): Promise<LlmStatus> {
  const res = await fetch(`${BASE_URL}/query/llm/status`, { headers: headers() });
  return handleResponse<LlmStatus>(res);
}
