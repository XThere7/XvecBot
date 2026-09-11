// ── API Types ─────────────────────────────────────────────────────────────────

export interface Citation {
  page: number;
  chunk_id: string;
  text_preview: string;
}

export interface Document {
  id: string;
  filename: string;
  upload_date: string;
  total_pages: number;
  file_size: number;
  status: "processing" | "ready" | "error";
}

export interface UploadResponse {
  document_id: string;
  filename: string;
  total_pages: number;
  chunk_count: number;
  message: string;
}

export interface QueryRequest {
  question: string;
  conversation_id?: string;
  document_id?: string;
}

export interface QueryResponse {
  answer: string;
  citations: Citation[];
  conversation_id: string;
  grounded: boolean;
  retrieved_count: number;
}

// ── UI State Types ────────────────────────────────────────────────────────────

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  isStreaming?: boolean;
}

export interface StreamEvent {
  token?: string;
  done: boolean;
  citations?: Citation[];
  conversation_id?: string;
  grounded?: boolean;
  error?: string;
}
