"use client";

import {
  ExternalLink,
  FileSearch,
  Globe2,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RowMenu } from "@/components/ui/dropdown-menu";
import { IndeterminateProgress } from "@/components/ui/indeterminate-progress";
import { RelativeTime } from "@/components/ui/relative-time";
import { cn } from "@/lib/cn";
import {
  REFRESH_POLICY_LABEL,
  SOURCE_STATUS,
  websiteDisplayUrl,
} from "./website-status";
import type { WebsiteSource } from "@/types/api";

export function WebsiteSourceCard({
  source,
  onViewPages,
  onRefresh,
  onDelete,
  refreshing = false,
}: {
  source: WebsiteSource;
  onViewPages: () => void;
  onRefresh: () => void;
  onDelete: () => void;
  refreshing?: boolean;
}) {
  const status = SOURCE_STATUS[source.status];
  const syncing = source.status === "syncing";

  return (
    <article className="flex flex-col rounded-md border border-subtle bg-surface p-4 sm:p-5">
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-subtle bg-surface-raised text-accent-400"
        >
          <Globe2 className="h-4 w-4" />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-base font-semibold text-primary">
              {source.name}
            </h3>
            <Badge tone={status.tone} dot animated={status.animated}>
              {status.label}
            </Badge>
          </div>
          <a
            href={source.url}
            target="_blank"
            rel="noreferrer"
            title={source.url}
            className="mt-0.5 inline-flex max-w-full items-center gap-1 text-xs text-tertiary transition-colors hover:text-accent-300 hover:underline"
          >
            <span className="truncate">{websiteDisplayUrl(source.url)}</span>
            <ExternalLink aria-hidden className="h-3 w-3 shrink-0" />
          </a>
        </div>

        <RowMenu
          label={`Actions for ${source.name}`}
          items={[
            {
              label: "View pages",
              icon: FileSearch,
              onSelect: onViewPages,
            },
            {
              label: "Refresh now",
              icon: RefreshCw,
              disabled: syncing || refreshing,
              description: syncing
                ? "Wait for the current scan to finish"
                : "Scan the site again for changed pages",
              onSelect: onRefresh,
            },
            {
              label: "Delete website",
              icon: Trash2,
              tone: "danger",
              disabled: syncing || refreshing,
              description:
                syncing || refreshing
                  ? "Unavailable while the site is scanning"
                  : undefined,
              onSelect: onDelete,
            },
          ]}
        />
      </div>

      {syncing && (
        <div className="mt-4">
          <IndeterminateProgress label="Website scan in progress" />
          <p className="mt-2 text-xs text-secondary" role="status">
            Scanning public pages. This can take a few minutes for larger sites.
          </p>
        </div>
      )}

      <dl className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
        <div className="flex items-baseline gap-1.5">
          <dt className="text-tertiary">Indexed</dt>
          <dd className="font-medium text-primary">
            {source.pages_indexed} page{source.pages_indexed === 1 ? "" : "s"}
          </dd>
        </div>
        <div className="flex items-baseline gap-1.5">
          <dt className="text-tertiary">Found</dt>
          <dd className={cn("font-medium", syncing ? "text-secondary" : "text-primary")}>
            {source.pages_discovered > 0
              ? `${source.pages_discovered} page${
                  source.pages_discovered === 1 ? "" : "s"
                }`
              : syncing
                ? "Discovering…"
                : "None yet"}
          </dd>
        </div>
        <div className="flex items-baseline gap-1.5">
          <dt className="text-tertiary">Last synced</dt>
          <dd className="text-secondary">
            {source.last_synced_at ? (
              <RelativeTime date={source.last_synced_at} live />
            ) : (
              "Not yet"
            )}
          </dd>
        </div>
        <div className="flex items-baseline gap-1.5">
          <dt className="text-tertiary">Refresh</dt>
          <dd className="text-tertiary">
            {REFRESH_POLICY_LABEL[source.refresh_policy]}
          </dd>
        </div>
      </dl>

      {(source.status === "failed" || source.status === "partial") &&
        source.error_message && (
        <AlertBanner
          tone={source.status === "partial" ? "warning" : "danger"}
          title={
            source.status === "partial"
              ? "The scan finished with limitations"
              : "We could not finish scanning this website"
          }
          className="mt-4"
          action={
            <Button
              variant="secondary"
              size="sm"
              loading={refreshing}
              onClick={onRefresh}
            >
              Retry
            </Button>
          }
        >
          <span className="line-clamp-3 break-words">{source.error_message}</span>
        </AlertBanner>
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-subtle pt-3">
        <Button
          variant="secondary"
          size="sm"
          onClick={onViewPages}
          iconLeft={<FileSearch aria-hidden className="h-4 w-4" />}
        >
          View pages
        </Button>
        <p className="text-2xs text-tertiary">
          {source.pages_indexed > 0
            ? "These pages are available to agents in this workspace."
            : "Pages become available to agents once indexed."}
        </p>
      </div>
    </article>
  );
}
