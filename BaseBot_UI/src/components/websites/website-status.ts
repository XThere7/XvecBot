import type { BadgeTone } from "@/components/ui/badge";
import type {
  WebsitePageStatus,
  WebsiteRefreshPolicy,
  WebsiteSourceStatus,
} from "@/types/api";

export const SOURCE_STATUS: Record<
  WebsiteSourceStatus,
  { label: string; tone: BadgeTone; animated?: boolean }
> = {
  pending: { label: "Queued", tone: "neutral" },
  syncing: { label: "Scanning", tone: "info", animated: true },
  synced: { label: "Ready", tone: "success" },
  failed: { label: "Needs attention", tone: "danger" },
};

export const PAGE_STATUS: Record<
  WebsitePageStatus,
  { label: string; tone: BadgeTone; animated?: boolean }
> = {
  discovered: { label: "Queued", tone: "info", animated: true },
  indexed: { label: "Indexed", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  removed: { label: "Removed", tone: "neutral" },
};

export const REFRESH_POLICY_LABEL: Record<WebsiteRefreshPolicy, string> = {
  manual: "Manual",
  weekly: "Weekly",
  daily: "Daily",
};

export function websiteHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** Host + path, so multiple sections of one site stay distinguishable. */
export function websiteDisplayUrl(url: string): string {
  try {
    const parsed = new URL(url);
    const host = parsed.host.replace(/^www\./, "");
    const path = parsed.pathname === "/" ? "" : parsed.pathname;
    return `${host}${path}${parsed.search}`;
  } catch {
    return url;
  }
}
