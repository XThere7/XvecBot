"use client";

import { ExternalLink, Globe2 } from "lucide-react";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorPanel } from "@/components/common/error-panel";
import { IndeterminateProgress } from "@/components/ui/indeterminate-progress";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useWebsitePages } from "@/hooks/use-websites";
import { PAGE_STATUS, SOURCE_STATUS, websiteHost } from "./website-status";
import type { WebsitePage, WebsiteSource } from "@/types/api";

function pageLabel(page: WebsitePage): string {
  if (page.title?.trim()) return page.title.trim();
  try {
    const parsed = new URL(page.url);
    return `${parsed.pathname}${parsed.search}` || websiteHost(page.url);
  } catch {
    return page.url;
  }
}

export function WebsitePagesModal({
  wsId,
  source,
  open,
  onClose,
}: {
  wsId: string;
  source: WebsiteSource | null;
  open: boolean;
  onClose: () => void;
}) {
  const pagesQuery = useWebsitePages(wsId, source?.id, {
    enabled: open,
    poll:
      open &&
      (source?.status === "syncing" || source?.status === "pending"),
  });
  const pages = pagesQuery.data ?? [];
  const sourceStatus = source ? SOURCE_STATUS[source.status] : null;
  const indexed = pages.filter((page) => page.status === "indexed").length;
  const failed = pages.filter((page) => page.status === "failed").length;
  const queued = pages.filter((page) => page.status === "discovered").length;

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={source?.name ?? "Website pages"}
      description={
        source ? (
          <a
            href={source.url}
            target="_blank"
            rel="noreferrer"
            title={source.url}
            className="inline-flex max-w-full items-center gap-1 break-all hover:text-accent-300 hover:underline"
          >
            <span className="truncate">{source.url}</span>
            <ExternalLink aria-hidden className="h-3 w-3 shrink-0" />
          </a>
        ) : undefined
      }
      footer={
        <Button variant="secondary" onClick={onClose}>
          Close
        </Button>
      }
    >
      {source && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2">
            {sourceStatus && (
              <Badge tone={sourceStatus.tone} dot animated={sourceStatus.animated}>
                {sourceStatus.label}
              </Badge>
            )}
            {!pagesQuery.isLoading && (
              <>
                <Badge tone="success">{indexed} indexed</Badge>
                {queued > 0 && <Badge tone="info">{queued} queued</Badge>}
                {failed > 0 && <Badge tone="danger">{failed} failed</Badge>}
              </>
            )}
            <span className="text-2xs text-tertiary">
              {Math.max(source.pages_indexed, indexed)} of up to 50 pages
              available to agents
            </span>
          </div>

          {source.status === "syncing" && (
            <div>
              <IndeterminateProgress label="Website scan in progress" />
              <p className="mt-2 text-xs text-secondary" role="status">
                Pages appear here as the scan finds and indexes them.
              </p>
            </div>
          )}

          {source.status === "failed" && source.error_message && (
            <AlertBanner tone="danger" title="The last scan did not finish">
              <span className="break-words">{source.error_message}</span>
            </AlertBanner>
          )}

          {pagesQuery.isError ? (
            <ErrorPanel
              compact
              title="We could not load this website's pages"
              statusCode={(pagesQuery.error as { status?: number })?.status}
              onRetry={() => void pagesQuery.refetch()}
            />
          ) : pagesQuery.isLoading ? (
            <Skeleton variant="table" rows={5} />
          ) : pages.length === 0 ? (
            <EmptyState
              size="sm"
              icon={Globe2}
              title="No pages discovered yet"
              description={
                source.status === "syncing"
                  ? "The crawler is still looking for public pages. This list updates automatically."
                  : "This source did not return any indexable HTML pages. Try a different page or check the site's robots.txt rules."
              }
            />
          ) : (
            <ul aria-label="Website pages" className="flex flex-col">
              {pages.map((page) => {
                const status = PAGE_STATUS[page.status];
                return (
                  <li
                    key={page.id}
                    className="flex flex-col gap-2 border-t border-subtle py-3 first:border-t-0 first:pt-0 last:pb-0 sm:flex-row sm:items-start sm:justify-between sm:gap-4"
                  >
                    <div className="min-w-0">
                      <a
                        href={page.url}
                        target="_blank"
                        rel="noreferrer"
                        title={page.url}
                        className="group inline-flex max-w-full items-center gap-1.5 text-sm text-primary hover:text-accent-300"
                      >
                        <span className="truncate group-hover:underline">
                          {pageLabel(page)}
                        </span>
                        <ExternalLink
                          aria-hidden
                          className="h-3 w-3 shrink-0 text-tertiary"
                        />
                      </a>
                      <p className="mt-0.5 break-all text-2xs text-tertiary">
                        {page.url}
                      </p>
                      {page.status === "failed" && page.error_message && (
                        <p className="mt-1 line-clamp-2 text-xs text-danger-400">
                          {page.error_message}
                        </p>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-2 sm:flex-col sm:items-end">
                      <Badge tone={status.tone} dot animated={status.animated}>
                        {status.label}
                      </Badge>
                      {page.status === "indexed" && (
                        <span className="text-2xs text-tertiary">
                          {page.chunk_count} chunk
                          {page.chunk_count === 1 ? "" : "s"}
                        </span>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </Modal>
  );
}
