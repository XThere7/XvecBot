import type { BadgeTone } from "@/components/ui/badge";
import type {
  SocialMediaPlatform,
  SocialMediaSourceStatus,
} from "@/types/api";

export const MEDIA_STATUS: Record<
  SocialMediaSourceStatus,
  { label: string; tone: BadgeTone; animated?: boolean; description: string }
> = {
  pending: {
    label: "Pending",
    tone: "neutral",
    animated: true,
    description: "Queued for public metadata extraction.",
  },
  extracting: {
    label: "Extracting",
    tone: "info",
    animated: true,
    description: "Reading the public caption and metadata.",
  },
  awaiting_input: {
    label: "Awaiting user input",
    tone: "warning",
    description: "Add the caption or transcript so this post can be imported.",
  },
  ready: {
    label: "Ready to import",
    tone: "accent",
    description: "Review the text, then press Done to sync it to this agent.",
  },
  indexing: {
    label: "Indexing",
    tone: "info",
    animated: true,
    description: "Adding this post to the agent's knowledge and citations.",
  },
  imported: {
    label: "Imported",
    tone: "success",
    description: "This post is available to this agent with a citation.",
  },
  failed: {
    label: "Failed",
    tone: "danger",
    description: "The import stopped. Retry or add the text manually.",
  },
};

export const PLATFORM_LABEL: Record<SocialMediaPlatform, string> = {
  tiktok: "TikTok",
  instagram: "Instagram",
  facebook: "Facebook",
};

export function mediaHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function mediaDisplayUrl(url: string): string {
  try {
    const parsed = new URL(url);
    const value = `${parsed.hostname.replace(/^www\./, "")}${parsed.pathname}`;
    return value.length > 72 ? `${value.slice(0, 69)}…` : value;
  } catch {
    return url;
  }
}

export function mediaExcerpt(source: {
  content_text: string | null;
}): string | null {
  if (!source.content_text?.trim()) return null;
  const text = source.content_text.trim();
  return text.length > 220 ? `${text.slice(0, 217).trimEnd()}…` : text;
}
