import { DEFAULT_LANGUAGE, DEFAULT_MODEL } from "./constants";

export type ModelTier = "paid" | "free";

export type ModelOption = {
  value: string;
  label: string;
  tier: ModelTier;
  /** Shown next to the label. All free options were unavailable at spec time. */
  note?: string;
};

/**
 * There is no API that lists models. This list is verified against the running
 * backend and must be kept in sync with it (frontendbot.md §6.7).
 */
export const MODELS: ModelOption[] = [
  {
    value: "meta-llama/llama-3.1-8b-instruct",
    label: "Llama 3.1 8B Instruct",
    tier: "paid",
  },
  {
    value: "openrouter/auto",
    label: "OpenRouter Auto",
    tier: "paid",
  },
  {
    value: "meta-llama/llama-3.3-70b-instruct:free",
    label: "Llama 3.3 70B Instruct",
    tier: "free",
    note: "Currently unavailable",
  },
  {
    value: "qwen/qwen3-235b-a22b:free",
    label: "Qwen3 235B A22B",
    tier: "free",
    note: "Currently unavailable",
  },
  {
    value: "google/gemma-3-27b-it:free",
    label: "Gemma 3 27B IT",
    tier: "free",
    note: "Currently unavailable",
  },
  {
    value: "openrouter/free",
    label: "OpenRouter Auto (free)",
    tier: "free",
    note: "Daily free-request quota",
  },
];

export const PAID_MODELS = MODELS.filter((m) => m.tier === "paid");
export const FREE_MODELS = MODELS.filter((m) => m.tier === "free");

export const MODEL_GROUPS = [
  { label: "Paid", options: PAID_MODELS },
  { label: "Free (limited availability)", options: FREE_MODELS },
];

export const MODEL_BILLING_CAPTION =
  "Paid models give reliable answers. Free models may be rate-limited or temporarily unavailable.";

/** `maxLength=50`, default `English`. Anything else is silently coerced to English. */
export const LANGUAGES = [
  "English",
  "Swahili",
  "French",
  "Arabic",
  "Portuguese",
] as const;

export type Language = (typeof LANGUAGES)[number];

export const DEFAULT_LANGUAGE_OPTIONS = [...LANGUAGES];

export function modelLabel(value: string): string {
  return MODELS.find((m) => m.value === value)?.label ?? value;
}

export function isKnownModel(value: string): boolean {
  return MODELS.some((m) => m.value === value);
}

export function isKnownLanguage(value: string): boolean {
  return (LANGUAGES as readonly string[]).includes(value);
}

export function normaliseModel(value: string): string {
  return isKnownModel(value) ? value : DEFAULT_MODEL;
}

export function normaliseLanguage(value: string): string {
  return isKnownLanguage(value) ? value : DEFAULT_LANGUAGE;
}

export function temperatureCaption(value: number): string {
  if (value <= 0.2) return "Precise — sticks closely to the documents";
  if (value <= 0.5) return "Mostly precise with a little flexibility";
  if (value <= 0.8) return "Balanced";
  return "Creative — more variation in phrasing";
}

/** Generic starter questions shown in the empty Test panel. */
export const STARTER_QUESTIONS = [
  "What can you help me with?",
  "Summarise your most important information.",
  "How do I get started?",
] as const;