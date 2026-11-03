"use client";

import * as React from "react";
import {
  AlertTriangle,
  ExternalLink,
  Facebook,
  FileUp,
  Instagram,
  Music2,
  Pencil,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { formatAbsoluteTime } from "@/lib/format";
import type { SocialMediaPlatform, SocialMediaSource } from "@/types/api";
import {
  MEDIA_STATUS,
  PLATFORM_LABEL,
  mediaDisplayUrl,
  mediaExcerpt,
} from "./media-status";

const PLATFORM_ICONS: Record<SocialMediaPlatform, React.ElementType> = {
  tiktok: Music2,
  instagram: Instagram,
  facebook: Facebook,
};

export type MediaSourceCardProps = {
  source: SocialMediaSource;
  highlighted?: boolean;
  retrying?: boolean;
  onEdit: (source: SocialMediaSource) => void;
  onRetry: (source: SocialMediaSource) => void;
  onDelete: (source: SocialMediaSource) => void;
};

export function MediaSourceCard({
  source,
  highlighted = false,
  retrying = false,
  onEdit,
  onRetry,
  onDelete,
}: MediaSourceCardProps) {
  const status = MEDIA_STATUS[source.status];
  const PlatformIcon = PLATFORM_ICONS[source.platform];
  const excerpt = mediaExcerpt(source);
  const active = ["pending", "extracting", "indexing"].includes(source.status);

  return (
    <article
      id={`media-source-${source.id}`}
      className={cn(
        "scroll-mt-24 rounded-md border bg-surface p-4 shadow-elevation-1 transition-colors sm:p-5",
        highlighted
          ? "border-accent-500 ring-1 ring-accent-500/40"
          : "border-subtle",
      )}
      aria-busy={active || undefined}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <div
          aria-hidden
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-subtle bg-surface-raised text-secondary"
        >
          <PlatformIcon className="h-5 w-5" />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={status.tone} dot animated={status.animated}>
              {status.label}
            </Badge>
            <span className="text-xs text-tertiary">
              {PLATFORM_LABEL[source.platform]}
            </span>
            {source.status === "imported" && source.chunk_count > 0 && (
              <span className="text-xs text-tertiary">
                · {source.chunk_count} knowledge{" "}
                {source.chunk_count === 1 ? "chunk" : "chunks"}
              </span>
            )}
          </div>

          <h3 className="mt-2 truncate text-sm font-semibold text-primary">
            {source.title || `${PLATFORM_LABEL[source.platform]} post`}
          </h3>
          <p className="mt-0.5 truncate text-xs text-tertiary" title={source.url}>
            {mediaDisplayUrl(source.url)}
          </p>

          {(source.author_name || source.published_at) && (
            <p className="mt-1 text-xs text-tertiary">
              {source.author_name && <>by {source.author_name}</>}
              {source.author_name && source.published_at && " · "}
              {source.published_at && (
                <time dateTime={source.published_at}>
                  {formatAbsoluteTime(source.published_at)}
                </time>
              )}
            </p>
          )}

          {excerpt && (
            <p className="mt-3 line-clamp-3 whitespace-pre-line text-sm leading-5 text-secondary">
              {excerpt}
            </p>
          )}

          {source.status === "awaiting_input" && (
            <div className="mt-3 flex items-start gap-2 rounded-sm border border-warning-500/30 bg-warning-500/10 px-3 py-2 text-xs text-warning-400">
              <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                {source.error_message ||
                  "We could not read enough public text. Add the caption or upload a transcript."}
              </span>
            </div>
          )}

          {source.status === "failed" && (
            <div className="mt-3 flex items-start gap-2 rounded-sm border border-danger-500/30 bg-danger-500/10 px-3 py-2 text-xs text-danger-400">
              <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                {source.error_message ||
                  "The import failed. Retry, or paste the caption manually."}
              </span>
            </div>
          )}

          {source.status === "ready" && (
            <p className="mt-3 text-xs text-accent-300">
              Review the extracted text, then press Done to sync it to this
              agent.
            </p>
          )}

          {source.status === "imported" && (
            <p className="mt-3 text-xs text-success-400">
              This post can now be cited by this agent. Other agents cannot see
              it.
            </p>
          )}

          {active && (
            <div className="mt-3 h-1 overflow-hidden rounded-full bg-surface-raised">
              <div className="h-full w-1/2 animate-pulse rounded-full bg-accent-500/70" />
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 sm:justify-end">
          {source.status === "awaiting_input" && (
            <Button
              size="sm"
              variant="primary"
              iconLeft={<FileUp aria-hidden className="h-4 w-4" />}
              onClick={() => onEdit(source)}
            >
              Add caption
            </Button>
          )}

          {source.status === "ready" && (
            <Button
              size="sm"
              variant="secondary"
              iconLeft={<Pencil aria-hidden className="h-4 w-4" />}
              onClick={() => onEdit(source)}
            >
              Review text
            </Button>
          )}

          {source.status === "imported" && (
            <Button
              size="sm"
              variant="ghost"
              iconLeft={<Pencil aria-hidden className="h-4 w-4" />}
              onClick={() => onEdit(source)}
            >
              View text
            </Button>
          )}

          {source.status === "failed" && (
            <>
              <Button
                size="sm"
                variant="secondary"
                loading={retrying}
                iconLeft={<RefreshCw aria-hidden className="h-4 w-4" />}
                onClick={() => onRetry(source)}
              >
                Retry
              </Button>
              <Button
                size="sm"
                variant="ghost"
                iconLeft={<FileUp aria-hidden className="h-4 w-4" />}
                onClick={() => onEdit(source)}
              >
                Add text
              </Button>
            </>
          )}

          {(source.status === "ready" || source.status === "imported") && (
            <Button asChild size="sm" variant="ghost">
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Open original ${PLATFORM_LABEL[source.platform]} post`}
              >
                <ExternalLink aria-hidden className="h-4 w-4" />
                Open post
              </a>
            </Button>
          )}

          {!active && (
            <Button
              size="sm"
              variant="dangerGhost"
              iconLeft={<Trash2 aria-hidden className="h-4 w-4" />}
              onClick={() => onDelete(source)}
            >
              Remove
            </Button>
          )}
        </div>
      </div>
    </article>
  );
}
