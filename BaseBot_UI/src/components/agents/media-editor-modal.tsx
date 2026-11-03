"use client";

import * as React from "react";
import { FileUp, Save } from "lucide-react";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FieldControl } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Textarea } from "@/components/ui/textarea";
import {
  MAX_MEDIA_CONTENT_CHARS,
  MAX_MEDIA_TRANSCRIPT_BYTES,
} from "@/lib/constants";
import { formatAbsoluteTime } from "@/lib/format";
import { toast } from "@/lib/toast";
import {
  mediaErrorMessage,
  useUpdateMediaSource,
} from "@/hooks/use-media";
import type { SocialMediaSource } from "@/types/api";
import { MEDIA_STATUS, PLATFORM_LABEL, mediaDisplayUrl } from "./media-status";

const MIN_MANUAL_CHARS = 10;

export function MediaEditorModal({
  wsId,
  agentId,
  source,
  open,
  onClose,
}: {
  wsId: string;
  agentId: string;
  source: SocialMediaSource | null;
  open: boolean;
  onClose: () => void;
}) {
  const update = useUpdateMediaSource(wsId, agentId);
  const [text, setText] = React.useState("");
  const [title, setTitle] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [fileName, setFileName] = React.useState<string | null>(null);
  const fileRef = React.useRef<HTMLInputElement | null>(null);

  const readOnly = source?.status === "imported";

  React.useEffect(() => {
    if (!open) return;
    setText(source?.content_text ?? "");
    setTitle(source?.title ?? "");
    setError(null);
    setFileName(null);
    update.reset();
    // `update` is a mutation instance; resetting it must not re-run on updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, source?.id]);

  if (!source) return null;

  const trimmed = text.trim();
  const canSave =
    !readOnly &&
    trimmed.length >= MIN_MANUAL_CHARS &&
    trimmed.length <= MAX_MEDIA_CONTENT_CHARS &&
    !update.isPending &&
    trimmed !== (source.content_text ?? "").trim();

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    if (file.size > MAX_MEDIA_TRANSCRIPT_BYTES) {
      setError("Transcript files can be at most 200 KB.");
      return;
    }
    try {
      const next = (await file.text()).replace(/^\ufeff/, "");
      if (!next.trim()) {
        setError("That file is empty.");
        return;
      }
      setText(next.slice(0, MAX_MEDIA_CONTENT_CHARS));
      setFileName(file.name);
      if (next.length > MAX_MEDIA_CONTENT_CHARS) {
        setError(
          `The transcript was trimmed to the ${MAX_MEDIA_CONTENT_CHARS.toLocaleString()} character limit.`,
        );
      }
    } catch {
      setError("We could not read that file. Try a plain text transcript.");
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleSave = async () => {
    if (!canSave) return;
    setError(null);
    try {
      await update.mutateAsync({
        sourceId: source.id,
        content_text: trimmed,
        title: title.trim() || undefined,
      });
      toast.success({
        title: "Media text saved",
        description: "Press Done — sync to agent when you are ready.",
      });
      onClose();
    } catch (cause) {
      setError(mediaErrorMessage(cause));
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={readOnly ? "Imported post text" : "Review media link"}
      description={
        readOnly
          ? "This is the text this agent can use and cite. To change it, remove the source and import it again."
          : "We read public metadata only. Edit the text or upload a transcript before syncing it to this agent."
      }
      size="lg"
      footer={
        readOnly ? (
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        ) : (
          <>
            <Button
              variant="secondary"
              onClick={onClose}
              disabled={update.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={update.isPending}
              disabled={!canSave}
              iconLeft={<Save aria-hidden className="h-4 w-4" />}
              onClick={() => void handleSave()}
            >
              Save for sync
            </Button>
          </>
        )
      }
    >
      <div className="flex flex-col gap-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={MEDIA_STATUS[source.status].tone} dot>
            {MEDIA_STATUS[source.status].label}
          </Badge>
          <Badge tone="neutral">{PLATFORM_LABEL[source.platform]}</Badge>
          {source.author_name && (
            <span className="text-xs text-secondary">
              by {source.author_name}
            </span>
          )}
          {source.published_at && (
            <span className="text-xs text-tertiary">
              {formatAbsoluteTime(source.published_at)}
            </span>
          )}
        </div>

        <div className="rounded-sm border border-subtle bg-surface-raised px-3 py-2">
          <p className="break-all text-xs text-secondary">{source.url}</p>
          <p className="mt-1 text-2xs text-tertiary">
            {mediaDisplayUrl(source.url)}
          </p>
        </div>

        {source.error_message && source.status !== "imported" && (
          <AlertBanner tone="warning" title="What happened">
            {source.error_message}
          </AlertBanner>
        )}

        <FieldControl
          label="Display title"
          hint="Shown when this post is cited in an answer."
          counter={`${title.length}/200`}
        >
          <Input
            value={title}
            maxLength={200}
            readOnly={readOnly}
            placeholder={`${PLATFORM_LABEL[source.platform]} post`}
            onChange={(event) => setTitle(event.target.value)}
          />
        </FieldControl>

        <FieldControl
          label="Post text, caption or transcript"
          required
          hint="Treat this as reference material. The agent is instructed not to follow instructions inside it."
          counter={`${text.length.toLocaleString()} / ${MAX_MEDIA_CONTENT_CHARS.toLocaleString()}`}
          error={
            !readOnly && text.length > 0 && trimmed.length < MIN_MANUAL_CHARS
              ? `Paste at least ${MIN_MANUAL_CHARS} characters.`
              : undefined
          }
        >
          <Textarea
            value={text}
            rows={10}
            readOnly={readOnly}
            maxLength={MAX_MEDIA_CONTENT_CHARS}
            placeholder="Paste the public caption, post text or a transcript of the video…"
            className="min-h-[220px] font-mono text-sm"
            onChange={(event) => {
              setText(event.target.value);
              if (error) setError(null);
            }}
          />
        </FieldControl>

        {!readOnly && (
          <div className="flex flex-col gap-2 rounded-sm border border-subtle bg-surface-raised p-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs font-medium text-secondary">
                Have a transcript?
              </p>
              <p className="mt-0.5 text-2xs text-tertiary">
                Upload .txt, .md, .srt or .vtt (max 200 KB). It stays in your
                browser until you save.
              </p>
              {fileName && (
                <p className="mt-1 text-2xs text-success-400">
                  Loaded {fileName}
                </p>
              )}
            </div>
            <input
              ref={fileRef}
              type="file"
              accept=".txt,.md,.srt,.vtt,text/plain"
              className="sr-only"
              onChange={(event) =>
                void handleFile(event.target.files?.[0] ?? undefined)
              }
            />
            <Button
              variant="secondary"
              size="sm"
              iconLeft={<FileUp aria-hidden className="h-4 w-4" />}
              onClick={() => fileRef.current?.click()}
            >
              Upload transcript
            </Button>
          </div>
        )}

        {error && (
          <p
            role="alert"
            className="rounded-sm border border-danger-500/30 bg-danger-500/10 px-3 py-2 text-xs text-danger-400"
          >
            {error}
          </p>
        )}
      </div>
    </Modal>
  );
}
