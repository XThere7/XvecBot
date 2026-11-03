export type ISODate = string;

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  user_id: string;
}

export type PlanId = "free" | "standard" | "pro";

export type WebsiteRefreshPolicy = "manual" | "weekly" | "daily";

export interface PlanLimits {
  /** null means unlimited. */
  agents: number | null;
  documents: number | null;
  pages_indexed: number | null;
  website_sources: number | null;
  website_refresh: WebsiteRefreshPolicy;
  api_keys: number | null;
  chat_messages: number | null;
  embed_tokens: number | null;
  // Existing workspace-level entitlements retained for the billing meters.
  storage_bytes: number;
  members: number;
  /** Per-agent quota for public social media imports. */
  social_media_sources: number;
}

export interface PlanFeatures {
  website_widget: boolean;
  citations: boolean;
  conversation_history: boolean;
  lead_forms: boolean;
  email_integration: boolean;
  lead_qualification: boolean;
  actions: boolean;
  analytics: "usage" | "basic" | "advanced";
  whatsapp: boolean;
  developer_api: boolean;
  automations: boolean;
  custom_branding: boolean;
  support: "community" | "standard" | "priority";
}

export interface Plan {
  id: PlanId;
  name: string;
  tagline: string;
  price_tzs: number;
  /** Pre-formatted by the backend, e.g. "TZS 7,800". */
  price_label: string;
  /** Full price line, e.g. "TZS 7,800 / month" or "Free forever". */
  price_display: string;
  period: "forever" | "month";
  recommended: boolean;
  limits: PlanLimits;
  features: PlanFeatures;
  /** Advertised in this tier but not implemented yet → "Soon" badge. */
  coming_soon: string[];
}

export interface TrialInfo {
  duration_days: number;
  description: string;
  limits: PlanLimits;
}

export interface PlansResponse {
  plans: Plan[];
  currency: string;
  trial: TrialInfo;
  payments_configured: boolean;
  upgrade_available: boolean;
  launch_note: string;
}

export interface UsageCounter {
  used: number;
  /** null means unlimited. */
  limit: number | null;
  percent: number;
  unlimited: boolean;
}

export interface ChatUsage extends UsageCounter {
  period_start: ISODate;
  period_end: ISODate;
  resets_at: ISODate;
}

export interface StorageUsage {
  used_bytes: number;
  limit_bytes: number;
  percent: number;
}

export interface MemberUsage extends UsageCounter {
  /** Member invites do not exist yet; the owner is the only seat. */
  enforced: boolean;
}

export interface BillingUsage {
  agents: UsageCounter;
  documents: UsageCounter;
  pages_indexed: UsageCounter;
  website_sources: UsageCounter;
  api_keys: UsageCounter;
  embed_tokens: UsageCounter;
  chat_messages: ChatUsage;
  storage: StorageUsage;
  members: MemberUsage;
}

export interface BillingSummary {
  workspace_id: string;
  plan: Plan;
  plans: Plan[];
  is_trial: boolean;
  base_plan: PlanId;
  effective_plan: PlanId | "trial";
  trial_ends_at: ISODate | null;
  days_remaining: number | null;
  usage: BillingUsage;
  period: { start: ISODate; end: ISODate; resets_at: ISODate };
  plan_started_at: ISODate | null;
  payments_configured: boolean;
  upgrade_available: boolean;
  launch_note: string;
}

/** Structured `detail` returned by every plan gate (402/403/429). */
export interface PlanLimitDetail {
  code: "plan_limit_reached" | "plan_feature_locked";
  resource:
    | "agents"
    | "documents"
    | "pages_indexed"
    | "website_sources"
    | "website_refresh"
    | "api_keys"
    | "chat_messages"
    | "embed_tokens"
    | "storage"
    | "developer_api"
    | string;
  message: string;
  plan: string;
  plan_name?: string;
  used?: number | string | null;
  limit?: number | string | null;
  resets_at?: ISODate | null;
  upgrade_required?: boolean;
  payments_configured?: boolean;
}

export interface Workspace {
  id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  owner_id: string;
  created_at: ISODate;
  plan: PlanId;
  plan_started_at: ISODate | null;
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

export type WebsiteSourceStatus = "pending" | "syncing" | "synced" | "failed";
export type WebsitePageStatus = "discovered" | "indexed" | "failed" | "removed";

export interface WebsiteSource {
  id: string;
  workspace_id: string;
  url: string;
  name: string;
  status: WebsiteSourceStatus;
  pages_discovered: number;
  pages_indexed: number;
  last_synced_at: ISODate | null;
  next_sync_at: ISODate | null;
  refresh_policy: WebsiteRefreshPolicy;
  error_message: string | null;
  created_at: ISODate;
  updated_at: ISODate;
}

export interface WebsitePage {
  id: string;
  source_id: string;
  workspace_id: string;
  url: string;
  title: string | null;
  content_hash: string | null;
  status: WebsitePageStatus;
  chunk_count: number;
  error_message: string | null;
  last_indexed_at: ISODate | null;
  created_at: ISODate;
}

export type SocialMediaPlatform = "tiktok" | "instagram" | "facebook";
export type SocialMediaSourceStatus =
  | "pending"
  | "extracting"
  | "awaiting_input"
  | "ready"
  | "indexing"
  | "imported"
  | "failed";

export interface SocialMediaSource {
  id: string;
  workspace_id: string;
  agent_id: string;
  url: string;
  normalized_url: string;
  platform: SocialMediaPlatform;
  provider_post_id: string | null;
  title: string | null;
  author_name: string | null;
  published_at: string | null;
  thumbnail_url: string | null;
  content_text: string | null;
  content_hash: string | null;
  status: SocialMediaSourceStatus;
  extraction_method: string | null;
  error_code: string | null;
  error_message: string | null;
  chunk_count: number;
  attempt_count: number;
  imported_at: ISODate | null;
  created_at: ISODate;
  updated_at: ISODate;
}

export interface SocialMediaUsage {
  used: number;
  limit: number;
}

export interface SocialMediaListResponse {
  sources: SocialMediaSource[];
  usage: SocialMediaUsage;
  supported_platforms: SocialMediaPlatform[];
  max_content_chars: number;
}

export interface SocialMediaCreateResponse {
  source: SocialMediaSource;
  usage: SocialMediaUsage;
}

export interface SocialMediaSyncResponse {
  sources: SocialMediaSource[];
  queued: number;
}

export interface Agent {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  welcome_message: string | null;
  /** Same-server icon path (e.g. /static/icons/…) or null = default bubble. */
  icon_url: string | null;
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
  /** Present when the cited chunk came from a connected website page. */
  source_url?: string | null;
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
  /** Shareable hosted chat page, on the configured HOSTED_BASE_URL. */
  hosted_url: string;
}

export interface PublicAgentInfo {
  name: string;
  description: string | null;
  language: string;
  welcome_message: string;
  /** Absolute URL, or null when the agent uses the default bubble. */
  icon_url: string | null;
}

export interface PublicChatResponse {
  answer: string;
  sources: Source[];
  conversation_id: string;
}

export interface DeveloperApiKey {
  id: string;
  user_id: string;
  workspace_id: string;
  name: string;
  /** Masked prefix, e.g. "sk-botbase-a1b2". Never the full key. */
  key_prefix: string;
  /** Integer 0 | 1 from the backend. */
  is_active: 0 | 1;
  /** null = every agent in the workspace is allowed. */
  allowed_agents: string[] | null;
  request_count: number;
  last_used_at: ISODate | null;
  expires_at: ISODate | null;
  created_at: ISODate;
}

export interface DeveloperApiKeyCreated extends DeveloperApiKey {
  /** Full plaintext key — present on the 201 response only. */
  key: string;
  warning: string;
}

export interface TrainResponse {
  status: "processing" | "ready";
  message?: string;
}

export interface AgentChatRequest {
  message: string;
  conversation_id?: string;
}