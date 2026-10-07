export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "XvecBot";
export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "";

/** Poll loop (§6.4) — 3 s, never shortened. */
export const TRAINING_POLL_INTERVAL_MS = 3000;
/** Hard cap so we never poll forever. */
export const TRAINING_POLL_CAP_MS = 10 * 60 * 1000;

export const MAX_MESSAGE_LENGTH = 4000;
export const MESSAGE_COUNTER_WARN = 3800;

export const MAX_NAME_LENGTH = 100;
export const MAX_DESCRIPTION_LENGTH = 500;
export const MAX_LABEL_LENGTH = 100;
export const MAX_EMAIL_LENGTH = 255;
export const MIN_PASSWORD_LENGTH = 8;

export const ALLOWED_FILE_EXTENSIONS = [".pdf", ".txt", ".docx"] as const;
/** Recommended client-side cap. The upload route itself has no server-side cap. */
export const MAX_FILE_SIZE_MB = 50;

export const DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant.";
export const DEFAULT_MODEL = "meta-llama/llama-3.1-8b-instruct";
export const DEFAULT_TEMPERATURE = 0.7;
export const DEFAULT_LANGUAGE = "English";

export const DEFAULT_WIDGET_POSITION = "right";
export const DEFAULT_WIDGET_COLOR = "#6366f1";

export const TOAST_DURATION = {
  success: 3000,
  info: 4000,
  warning: 4000,
  error: 6000,
  errorWithAction: 8000,
} as const;

export const MAX_VISIBLE_TOASTS = 4;

export const SESSION_EXPIRED_MESSAGE = "Your session expired. Please sign in again.";

export const QUERY_STALE_TIME_MS = 60_000;