"use client";

import * as React from "react";
import { Globe2 } from "lucide-react";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { ErrorPanel } from "@/components/common/error-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { truncate } from "@/lib/format";
import { toast } from "@/lib/toast";
import {
  useDeleteWebsiteSource,
  useRefreshWebsiteSource,
  useWebsiteSources,
  websiteErrorMessage,
} from "@/hooks/use-websites";
import { WebsitePagesModal } from "./website-pages-modal";
import { WebsiteSourceCard } from "./website-source-card";
import type { WebsiteSource, WebsiteSourceStatus } from "@/types/api";

export function WebsiteSourcesSection({ wsId }: { wsId: string }) {
  const query = useWebsiteSources(wsId);
  const refresh = useRefreshWebsiteSource(wsId);
  const remove = useDeleteWebsiteSource(wsId);

  const [viewingId, setViewingId] = React.useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = React.useState<WebsiteSource | null>(
    null,
  );

  const sources = React.useMemo(() => query.data ?? [], [query.data]);
  const viewingSource = sources.find((source) => source.id === viewingId) ?? null;
  const refreshingId = refresh.isPending ? refresh.variables : undefined;

  // Toast only on a real transition, so loading the page never replays old
  // completions. The source row is the terminal-state authority.
  const previousStatuses = React.useRef(
    new Map<string, WebsiteSourceStatus>(),
  );
  React.useEffect(() => {
    const next = new Map<string, WebsiteSourceStatus>();
    for (const source of sources) {
      const previous = previousStatuses.current.get(source.id);
      if (
        (previous === "syncing" || previous === "pending") &&
        source.status === "synced"
      ) {
        toast.success({
          title: `${source.name} is ready`,
          description:
            source.pages_indexed > 0
              ? `${source.pages_indexed} page${
                  source.pages_indexed === 1 ? "" : "s"
                } indexed and available to your agents.`
              : "The scan finished, but no indexable pages were found.",
          id: `website-${source.id}`,
        });
      } else if (
        (previous === "syncing" || previous === "pending") &&
        source.status === "failed"
      ) {
        toast.error({
          title: `Could not finish scanning ${source.name}`,
          description: truncate(
            source.error_message ?? "Open the source for details and retry.",
            180,
          ),
          id: `website-${source.id}`,
        });
      }
      next.set(source.id, source.status);
    }
    previousStatuses.current = next;
  }, [sources]);

  const handleRefresh = (source: WebsiteSource) => {
    refresh.mutate(source.id, {
      onSuccess: () => {
        toast.info({
          title: "Refresh started",
          description: `Scanning ${source.name} again for changed pages.`,
        });
      },
      onError: (error) => {
        toast.error({
          title: "Could not refresh this website",
          description: websiteErrorMessage(error),
        });
      },
    });
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    try {
      await remove.mutateAsync(pendingDelete.id);
      toast.success({ title: "Website disconnected" });
      setPendingDelete(null);
      if (viewingId === pendingDelete.id) setViewingId(null);
    } catch (error) {
      toast.error({
        title: "Could not disconnect this website",
        description: websiteErrorMessage(error),
      });
    }
  };

  if (query.isLoading && !query.data) return null;

  if (query.isError && sources.length === 0) {
    return (
      <ErrorPanel
        compact
        title="We could not load your connected websites"
        statusCode={(query.error as { status?: number })?.status}
        onRetry={() => void query.refetch()}
      />
    );
  }

  if (sources.length === 0) return null;

  return (
    <section aria-labelledby="connected-websites-heading" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2
            id="connected-websites-heading"
            className="flex items-center gap-2 text-xl text-primary"
          >
            <Globe2 aria-hidden className="h-5 w-5 text-accent-400" />
            Connected websites
          </h2>
          <p className="mt-1 text-sm text-secondary">
            Indexed pages from these sites are part of this workspace&apos;s
            knowledge and can be cited by agents.
          </p>
        </div>
        <Badge tone="neutral">
          {sources.length} site{sources.length === 1 ? "" : "s"}
        </Badge>
      </div>

      {query.isError && (
        <AlertBanner
          tone="warning"
          title="The website list may be out of date"
          action={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void query.refetch()}
            >
              Retry
            </Button>
          }
        >
          We could not refresh the list. Showing the last loaded sources.
        </AlertBanner>
      )}

      <div
        className={cn(
          "grid gap-4",
          sources.length > 1 && "xl:grid-cols-2",
        )}
      >
        {query.isLoading
          ? Array.from({ length: Math.max(sources.length, 1) }).map((_, index) => (
              <Skeleton key={index} variant="card" />
            ))
          : sources.map((source) => (
              <WebsiteSourceCard
                key={source.id}
                source={source}
                onViewPages={() => setViewingId(source.id)}
                onRefresh={() => handleRefresh(source)}
                onDelete={() => setPendingDelete(source)}
                refreshing={refreshingId === source.id}
              />
            ))}
      </div>

      <WebsitePagesModal
        wsId={wsId}
        source={viewingSource}
        open={Boolean(viewingSource)}
        onClose={() => setViewingId(null)}
      />

      <ConfirmationDialog
        open={Boolean(pendingDelete)}
        onClose={() => setPendingDelete(null)}
        title="Disconnect website?"
        body={
          pendingDelete ? (
            <p>
              This permanently removes{" "}
              <strong className="font-medium text-primary">
                {pendingDelete.name}
              </strong>{" "}
              and{" "}
              {pendingDelete.pages_indexed > 0
                ? `all ${pendingDelete.pages_indexed} indexed page${
                    pendingDelete.pages_indexed === 1 ? "" : "s"
                  }`
                : "any indexed content"}{" "}
              from this workspace&apos;s knowledge. Agents will no longer be able
              to answer from this site. This cannot be undone.
            </p>
          ) : null
        }
        confirmLabel="Disconnect website"
        confirmLoading={remove.isPending}
        onConfirm={() => void confirmDelete()}
      />
    </section>
  );
}
