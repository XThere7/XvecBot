"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  CheckCircle2,
  Link2,
  Plus,
  Share2,
  Sparkles,
} from "lucide-react";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorPanel } from "@/components/common/error-panel";
import { FieldControl } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/lib/toast";
import {
  mediaDuplicateSourceId,
  mediaErrorMessage,
  useCreateMediaSource,
  useDeleteMediaSource,
  useMediaSources,
  useRetryMediaSource,
  useSyncMediaSources,
} from "@/hooks/use-media";
import {
  mediaFormSchema,
  normaliseMediaInput,
} from "@/schemas/media";
import type {
  SocialMediaSource,
  SocialMediaSourceStatus,
} from "@/types/api";
import { MediaEditorModal } from "./media-editor-modal";
import { MediaSourceCard } from "./media-source-card";
import { MEDIA_STATUS } from "./media-status";

const ACTIVE_STATUSES: SocialMediaSourceStatus[] = [
  "pending",
  "extracting",
  "indexing",
];

export function AgentMediaPanel({
  wsId,
  agentId,
}: {
  wsId: string;
  agentId: string;
}) {
  const searchParams = useSearchParams();
  const query = useMediaSources(wsId, agentId);
  const create = useCreateMediaSource(wsId, agentId);
  const retry = useRetryMediaSource(wsId, agentId);
  const sync = useSyncMediaSources(wsId, agentId);
  const remove = useDeleteMediaSource(wsId, agentId);

  const [formOpen, setFormOpen] = React.useState(false);
  const [url, setUrl] = React.useState("");
  const [urlError, setUrlError] = React.useState<string | null>(null);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [duplicateId, setDuplicateId] = React.useState<string | null>(null);
  const [highlightedId, setHighlightedId] = React.useState<string | null>(
    null,
  );
  const [editorId, setEditorId] = React.useState<string | null>(null);
  const [pendingDelete, setPendingDelete] =
    React.useState<SocialMediaSource | null>(null);
  const urlRef = React.useRef<HTMLInputElement | null>(null);
  const statusRef = React.useRef(
    new Map<string, SocialMediaSourceStatus>(),
  );
  const hasSnapshotRef = React.useRef(false);

  const data = query.data;
  const sources = React.useMemo(() => data?.sources ?? [], [data?.sources]);
  const usage = data?.usage;
  const readySources = React.useMemo(
    () => sources.filter((source) => source.status === "ready"),
    [sources],
  );
  const awaitingCount = sources.filter(
    (source) => source.status === "awaiting_input",
  ).length;
  const importedCount = sources.filter(
    (source) => source.status === "imported",
  ).length;
  const limitReached = Boolean(
    usage && usage.limit > 0 && usage.used >= usage.limit,
  );
  const usagePercent =
    usage && usage.limit > 0
      ? Math.min(100, Math.round((usage.used / usage.limit) * 100))
      : 0;
  const editorSource =
    sources.find((source) => source.id === editorId) ?? null;

  // The header's "Add media link" action deep-links to ?add=1. Open the form
  // once for that navigation without trapping the user in it.
  React.useEffect(() => {
    if (searchParams.get("add") === "1" && !limitReached) {
      setFormOpen(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  React.useEffect(() => {
    if (formOpen) {
      const timer = window.setTimeout(() => urlRef.current?.focus(), 50);
      return () => window.clearTimeout(timer);
    }
  }, [formOpen]);

  // Polling is the source of truth for background work. Announce transitions
  // once so a user who tabbed away still learns the review is ready.
  React.useEffect(() => {
    const next = new Map<string, SocialMediaSourceStatus>();
    for (const source of sources) next.set(source.id, source.status);

    if (hasSnapshotRef.current) {
      for (const source of sources) {
        const previous = statusRef.current.get(source.id);
        if (!previous || previous === source.status) continue;
        if (source.status === "ready") {
          toast.info({
            title: "Ready to import",
            description:
              "Review the extracted text, then press Done — sync to agent.",
            id: `media-ready-${source.id}`,
          });
        } else if (source.status === "awaiting_input") {
          toast.warning({
            title: "Caption needed",
            description:
              "This platform did not expose enough public text. Add a caption or transcript.",
            id: `media-input-${source.id}`,
          });
        } else if (source.status === "imported") {
          toast.success({
            title: "Media imported",
            description:
              "This agent can now answer from and cite this post.",
            id: `media-imported-${source.id}`,
          });
        } else if (source.status === "failed") {
          toast.error({
            title: "Media import failed",
            description:
              source.error_message ??
              "Retry, or paste the caption or transcript manually.",
            id: `media-failed-${source.id}`,
          });
        }
      }
    }
    statusRef.current = next;
    hasSnapshotRef.current = true;
  }, [sources]);

  const highlightSource = (sourceId: string) => {
    setHighlightedId(sourceId);
    window.setTimeout(() => {
      document
        .getElementById(`media-source-${sourceId}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 30);
    window.setTimeout(() => {
      setHighlightedId((current) => (current === sourceId ? null : current));
    }, 2400);
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    setDuplicateId(null);
    const parsed = mediaFormSchema.safeParse({ url });
    if (!parsed.success) {
      setUrlError(parsed.error.issues[0]?.message ?? "Check the link.");
      return;
    }
    setUrlError(null);

    let absolute: string;
    try {
      absolute = normaliseMediaInput(parsed.data.url);
    } catch {
      setUrlError("Enter a valid public post link.");
      return;
    }

    try {
      await create.mutateAsync(absolute);
      setUrl("");
      setFormOpen(false);
      toast.success({
        title: "Link added",
        description: "Reading its public caption and metadata now.",
      });
    } catch (cause) {
      const duplicate = mediaDuplicateSourceId(cause);
      setDuplicateId(duplicate);
      setFormError(mediaErrorMessage(cause));
    }
  };

  const handleRetry = async (source: SocialMediaSource) => {
    try {
      const updated = await retry.mutateAsync(source.id);
      if (updated.status === "ready") {
        toast.info({
          title: "Ready to import",
          description: "Review the text, then press Done — sync to agent.",
        });
      } else {
        toast.info({
          title: "Retrying public extraction",
          description: "We will update this source when the check finishes.",
        });
      }
    } catch (cause) {
      toast.error({
        title: "Could not retry this source",
        description: mediaErrorMessage(cause),
      });
    }
  };

  const handleSync = async () => {
    if (readySources.length === 0) return;
    try {
      const result = await sync.mutateAsync(
        readySources.map((source) => source.id),
      );
      toast.info({
        title: `Syncing ${result.queued} ${
          result.queued === 1 ? "post" : "posts"
        }`,
        description:
          "This agent will cite them once indexing is complete.",
      });
    } catch (cause) {
      toast.error({
        title: "Could not sync media",
        description: mediaErrorMessage(cause),
      });
    }
  };

  const handleDelete = async () => {
    if (!pendingDelete) return;
    try {
      await remove.mutateAsync(pendingDelete.id);
      toast.success({
        title: "Media removed",
        description: "Its knowledge and citations were removed from this agent.",
      });
      if (editorId === pendingDelete.id) setEditorId(null);
      setPendingDelete(null);
    } catch (cause) {
      toast.error({
        title: "Could not remove this source",
        description: mediaErrorMessage(cause),
      });
    }
  };

  const retryBusyId =
    retry.isPending && typeof retry.variables === "string"
      ? retry.variables
      : null;

  return (
    <section
      aria-labelledby="agent-media-heading"
      className="flex flex-col gap-5"
    >
      <div className="rounded-md border border-subtle bg-surface p-5 shadow-elevation-1 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <div
              aria-hidden
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-accent-500/30 bg-accent-500/10 text-accent-300"
            >
              <Share2 className="h-5 w-5" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2
                  id="agent-media-heading"
                  className="text-base font-semibold text-primary"
                >
                  Social media posts
                </h2>
                {sources.length > 0 && (
                  <Badge tone="neutral">
                    {sources.length}{" "}
                    {sources.length === 1 ? "source" : "sources"}
                  </Badge>
                )}
              </div>
              <p className="mt-1 max-w-2xl text-sm leading-5 text-secondary">
                Import a public TikTok, Instagram or Facebook post into{" "}
                <span className="font-medium text-primary">this agent</span>.
                Its text enters the same knowledge and citation pipeline as
                documents. Other agents and workspace chat cannot see it.
              </p>
              <p className="mt-2 text-xs leading-5 text-tertiary">
                Public links only. No account connection, password or
                logged-in scraping. If a platform hides its caption, you can
                paste a caption or upload a transcript.
              </p>
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <Button
              variant={formOpen ? "secondary" : "primary"}
              size="sm"
              iconLeft={
                formOpen ? undefined : (
                  <Plus aria-hidden className="h-4 w-4" />
                )
              }
              disabled={limitReached && !formOpen}
              title={
                limitReached
                  ? "This agent's social media source limit is full."
                  : undefined
              }
              onClick={() => {
                setFormOpen((open) => !open);
                setFormError(null);
                setDuplicateId(null);
              }}
            >
              {formOpen ? "Close form" : "Add media link"}
            </Button>
          </div>
        </div>

        {usage && (
          <div className="mt-5 rounded-sm border border-subtle bg-surface-raised px-3 py-2.5">
            <div className="flex items-center justify-between gap-3 text-xs">
              <span className="text-secondary">
                {usage.used} of {usage.limit} source
                {usage.limit === 1 ? "" : "s"} used in this agent
              </span>
              <span className="text-tertiary">
                {Math.max(0, usage.limit - usage.used)} remaining
              </span>
            </div>
            <div
              className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface"
              role="progressbar"
              aria-label="Social media sources used in this agent"
              aria-valuemin={0}
              aria-valuemax={usage.limit}
              aria-valuenow={usage.used}
            >
              <div
                className={
                  limitReached
                    ? "h-full rounded-full bg-warning-500"
                    : "h-full rounded-full bg-accent-500"
                }
                style={{ width: `${usagePercent}%` }}
              />
            </div>
          </div>
        )}

        {limitReached && (
          <AlertBanner
            tone="warning"
            title="This agent's media limit is full"
            className="mt-4"
          >
            Remove a source from this agent before adding another. Existing plan
            prices and document limits are unchanged.
          </AlertBanner>
        )}

        {formOpen && (
          <form
            onSubmit={(event) => void handleSubmit(event)}
            className="mt-5 rounded-md border border-subtle bg-surface-raised p-4 sm:p-5"
            noValidate
          >
            <div className="flex flex-col gap-4">
              <FieldControl
                label="Public post URL"
                required
                error={urlError ?? undefined}
                hint="Paste a link to one specific TikTok video/photo, Instagram post/reel, or Facebook post. Short links (vm.tiktok.com, fb.watch) also work."
              >
                <Input
                  ref={urlRef}
                  type="url"
                  inputMode="url"
                  autoComplete="off"
                  spellCheck={false}
                  placeholder="https://www.instagram.com/p/…"
                  value={url}
                  aria-invalid={Boolean(urlError)}
                  disabled={create.isPending}
                  onChange={(event) => {
                    setUrl(event.target.value);
                    if (urlError) setUrlError(null);
                    if (formError) setFormError(null);
                    if (duplicateId) setDuplicateId(null);
                  }}
                />
              </FieldControl>

              <div className="flex flex-wrap items-center gap-2 text-2xs text-tertiary">
                <span>Supported:</span>
                <Badge tone="neutral">TikTok</Badge>
                <Badge tone="neutral">Instagram</Badge>
                <Badge tone="neutral">Facebook</Badge>
              </div>

              {formError && (
                <div
                  role="alert"
                  className="flex flex-col gap-2 rounded-sm border border-danger-500/30 bg-danger-500/10 px-3 py-2.5 text-xs text-danger-400 sm:flex-row sm:items-center sm:justify-between"
                >
                  <span className="flex items-start gap-2">
                    <AlertTriangle
                      aria-hidden
                      className="mt-0.5 h-4 w-4 shrink-0"
                    />
                    {formError}
                  </span>
                  {duplicateId && (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        highlightSource(duplicateId);
                        setFormOpen(false);
                      }}
                    >
                      View existing source
                    </Button>
                  )}
                </div>
              )}

              <div className="flex flex-wrap items-center justify-end gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setFormOpen(false)}
                  disabled={create.isPending}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  loading={create.isPending}
                  iconLeft={<Link2 aria-hidden className="h-4 w-4" />}
                >
                  Add link
                </Button>
              </div>
            </div>
          </form>
        )}
      </div>

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-primary">Media library</h3>
          <p className="mt-0.5 text-xs text-tertiary">
            Review extracted text, retry a failed import, or remove a source.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {importedCount > 0 && (
            <Badge tone="success">
              {importedCount} imported
            </Badge>
          )}
          {readySources.length > 0 && (
            <Badge tone="accent">
              {readySources.length} ready
            </Badge>
          )}
          {awaitingCount > 0 && (
            <Badge tone="warning">
              {awaitingCount} need{awaitingCount === 1 ? "s" : ""} text
            </Badge>
          )}
        </div>
      </div>

      {query.isPending ? (
        <div className="flex flex-col gap-3">
          <Skeleton height={132} className="rounded-md" />
          <Skeleton height={132} className="rounded-md" />
        </div>
      ) : query.isError ? (
        <ErrorPanel
          title="We could not load this agent's media"
          message={mediaErrorMessage(query.error)}
          statusCode={(query.error as { status?: number })?.status}
          onRetry={() => void query.refetch()}
        />
      ) : sources.length === 0 ? (
        <EmptyState
          icon={Share2}
          size="sm"
          title="No social posts in this agent yet"
          description="Add a public post link. We read only permitted public metadata, then you review the text before it becomes knowledge."
          action={
            <Button
              variant="primary"
              iconLeft={<Plus aria-hidden className="h-4 w-4" />}
              onClick={() => setFormOpen(true)}
              disabled={limitReached}
            >
              Add media link
            </Button>
          }
        />
      ) : (
        <div className="flex flex-col gap-3">
          {sources.map((source) => (
            <MediaSourceCard
              key={source.id}
              source={source}
              highlighted={highlightedId === source.id}
              retrying={retryBusyId === source.id}
              onEdit={(value) => setEditorId(value.id)}
              onRetry={(value) => void handleRetry(value)}
              onDelete={setPendingDelete}
            />
          ))}
        </div>
      )}

      {awaitingCount > 0 && readySources.length === 0 && (
        <AlertBanner
          tone="warning"
          title={`${awaitingCount} ${
            awaitingCount === 1 ? "link needs" : "links need"
          } text before Done`}
        >
          Add a caption or upload a transcript for the affected sources.
          Done is enabled after at least one source is ready to import.
        </AlertBanner>
      )}

      {readySources.length > 0 && (
        <div className="sticky bottom-3 z-10 rounded-md border border-accent-500/40 bg-surface/95 p-3 shadow-elevation-3 backdrop-blur sm:p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-2.5">
              <Sparkles
                aria-hidden
                className="mt-0.5 h-4 w-4 shrink-0 text-accent-300"
              />
              <div>
                <p className="text-sm font-medium text-primary">
                  {readySources.length}{" "}
                  {readySources.length === 1 ? "source is" : "sources are"}{" "}
                  ready to import
                </p>
                <p className="mt-0.5 text-xs text-secondary">
                  Press Done to chunk, embed and make{" "}
                  {readySources.length === 1 ? "it" : "them"} available to this
                  agent with citations.
                </p>
              </div>
            </div>
            <Button
              variant="primary"
              loading={sync.isPending}
              disabled={sync.isPending}
              iconLeft={<CheckCircle2 aria-hidden className="h-4 w-4" />}
              onClick={() => void handleSync()}
            >
              Done — sync to agent
            </Button>
          </div>
        </div>
      )}

      {ACTIVE_STATUSES.some((status) =>
        sources.some((source) => source.status === status),
      ) && (
        <p className="sr-only" role="status" aria-live="polite">
          {sources
            .filter((source) => ACTIVE_STATUSES.includes(source.status))
            .map(
              (source) =>
                `${source.title ?? "Media source"}: ${
                  MEDIA_STATUS[source.status].label
                }.`,
            )
            .join(" ")}
        </p>
      )}

      <MediaEditorModal
        wsId={wsId}
        agentId={agentId}
        source={editorSource}
        open={Boolean(editorSource)}
        onClose={() => setEditorId(null)}
      />

      <ConfirmationDialog
        open={Boolean(pendingDelete)}
        onClose={() => setPendingDelete(null)}
        title="Remove this media source?"
        body={
          <div className="flex flex-col gap-3">
            <p>
              This removes{" "}
              <strong className="font-medium text-primary">
                {pendingDelete?.title ?? "this post"}
              </strong>{" "}
              from this agent&apos;s knowledge, including its indexed chunks and
              citations.
            </p>
            <p>
              Other agents and workspace documents are not affected. You can add
              the link again later.
            </p>
          </div>
        }
        confirmLabel="Remove source"
        confirmLoading={remove.isPending}
        onConfirm={() => void handleDelete()}
      />
    </section>
  );
}
