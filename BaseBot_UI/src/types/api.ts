export type ISODate = string;

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  user_id: string;
}

export interface Workspace {
  id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  owner_id: string;
  created_at: ISODate;
  // NOTE: no updated_at on Workspace — do not render "last updated".
}

export type DocStatus = "uploaded" | "processing" | "ready" | "failed";
export type FileType = "pdf" | "txt" | "docx";

export interface WorkspaceDocument {
  id: string;
  workspace_id: string;
  filename: string;
  file_type: FileType;
  size_bytes: number;
  status: DocStatus;
  chunk_count: number;
  created_at: ISODate;
}

export interface DocumentStatusResponse {
  doc_id: string;
  filename: string;
  status: DocStatus;
  chunk_count: number;
}

export interface Agent {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  welcome_message: string | null;
  model: string;
  temperature: number;
  language: string;
  /** Returned as the NUMBER 0 | 1 — always wrap with Boolean() before rendering. */
  is_active: 0 | 1;
  created_at: ISODate;
  updated_at: ISODate;
}

export interface Conversation {
  id: string;
  agent_id: string;
  title: string | null;
  created_at: ISODate;
  updated_at: ISODate;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  sources: Source[] | null;
  created_at: ISODate;
}

export interface Source {
  filename: string;
  chunk_index: number;
}

export interface AgentChatResponse {
  conversation_id: string;
  answer: string;
  /** May be `[]` — retrieval found nothing. Not an error. */
  sources: Source[];
  model_used: string;
}

export interface WorkspaceChatResponse {
  answer: string;
  sources: Source[];
  conversation_history: { role: "user" | "assistant"; content: string }[];
}

export interface ConversationThread {
  conversation: Conversation;
  messages: Message[];
}

export interface EmbedToken {
  id: string;
  agent_id: string;
  /** "a3f7c91b..." (11 chars) on list/get. Full only on create and /snippet. */
  token: string;
  label: string;
  /** A real BOOLEAN here, unlike Agent.is_active. */
  is_active: boolean;
  /** null = any origin allowed. */
  allowed_origins: string[] | null;
  request_count: number;
  created_at: ISODate;
  last_used_at: ISODate | null;
}

export interface EmbedSnippet {
  /** Full HTML embed code; already contains the full token. */
  snippet: string;
  /** Full token. */
  token: string;
}

export interface PublicAgentInfo {
  name: string;
  description: string;
  language: string;
  welcome_message: string;
}

export interface TrainResponse {
  status: "processing" | "ready";
  message?: string;
}

export interface AgentChatRequest {
  message: string;
  conversation_id?: string;
}