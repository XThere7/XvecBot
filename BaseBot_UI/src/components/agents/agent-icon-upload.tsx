"use client";

/* eslint-disable @next/next/no-img-element -- previews are blob: URLs and
   icons come from the API origin; next/image cannot optimize either. */
import * as React from "react";
import { ImagePlus, Loader2, Trash2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { API_BASE_URL, ApiRequestError, apiDelete, apiPost } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { useAgent, agentKeys } from "@/hooks/use-agents";
import { toast } from "@/lib/toast";
import { agentSchemaApi } from "@/schemas/agent";
import type { Agent } from "@/types/api";

const ACCEPT = "image/png,image/jpeg,image/webp,image/gif";
const MAX_BYTES = 2 * 1024 * 1024;

/** Absolute URL for a stored icon path (backend returns same-server paths). */
export function iconSrc(iconUrl: string | null | undefined): string | null {
  if (!iconUrl) return null;
  if (/^https?:\/\//i.test(iconUrl)) return iconUrl;
  return `${API_BASE_URL}${iconUrl}`;
}

/** Prefer the server's detail message (e.g. the 2 MB / type errors). */
function serverMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiRequestError) {
    const body = err.body as { detail?: unknown } | undefined;
    if (body && typeof body.detail === "string" && body.detail) return body.detail;
  }
  return fallback;
}

export function AgentIconUpload({ wsId, agentId }: { wsId: string; agentId: string }) {
  const queryClient = useQueryClient();
  const agentQuery = useAgent(wsId, agentId);
  const [preview, setPreview] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const agent = agentQuery.data;
  const current = iconSrc(agent?.icon_url);

  React.useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  }, [preview]);

  async function refresh(agent: Agent) {
    const parsed = agentSchemaApi.parse(agent);
    queryClient.setQueryData(agentKeys.detail(wsId, agentId), parsed);
    await queryClient.invalidateQueries({ queryKey: agentKeys.list(wsId) });
  }

  function pickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    setError(null);
    if (!file) return;
    if (!file.type || !ACCEPT.split(",").includes(file.type)) {
      setError("Only PNG, JPG, WebP, and GIF images are allowed.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("Image must be under 2 MB.");
      return;
    }
    if (preview) URL.revokeObjectURL(preview);
    setPreview(URL.createObjectURL(file));
    void upload(file);
  }

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const updated = await apiPost<Agent>(
        `/workspaces/${wsId}/agents/${agentId}/icon`,
        form,
      );
      await refresh(updated);
      setPreview(null);
      toast.success({ title: "Bot icon updated" });
    } catch (err) {
      setPreview(null);
      setError(serverMessage(err, "Upload failed. Try again."));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      const updated = await apiDelete<Agent>(
        `/workspaces/${wsId}/agents/${agentId}/icon`,
      );
      await refresh(updated);
      toast.success({ title: "Bot icon removed" });
    } catch {
      setError("Could not remove the icon. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-md border border-subtle bg-surface p-6 shadow-elevation-1">
      <h2 className="text-xl text-primary">Bot icon</h2>
      <p className="mt-1 text-sm text-secondary">
        The bubble button on your customers&apos; websites shows this image.
        Without one, the widget keeps its default icon.
      </p>

      <div className="mt-4 flex items-center gap-4">
        <div className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-full border border-subtle bg-canvas">
          {preview || current ? (
            <img
              src={preview ?? current ?? ""}
              alt="Bot icon preview"
              className="h-full w-full object-cover"
            />
          ) : (
            <ImagePlus aria-hidden className="h-6 w-6 text-tertiary" />
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={pickFile}
            disabled={busy}
          />
          <Button
            variant="secondary"
            size="sm"
            disabled={busy}
            onClick={() => inputRef.current?.click()}
            iconLeft={
              busy ? (
                <Loader2 aria-hidden className="h-4 w-4 animate-spin" />
              ) : (
                <ImagePlus aria-hidden className="h-4 w-4" />
              )
            }
          >
            {current ? "Change icon" : "Upload icon"}
          </Button>
          {current ? (
            <Button variant="ghost" size="sm" disabled={busy} onClick={remove}>
              <Trash2 aria-hidden className="h-4 w-4" />
              Remove
            </Button>
          ) : null}
        </div>
      </div>

      <p className="mt-3 text-2xs text-tertiary">
        PNG, JPG, WebP or GIF · max 2 MB · shown as a circle in the chat bubble.
      </p>
      {error ? (
        <p role="alert" className="mt-2 text-sm text-danger-400">
          {error}
        </p>
      ) : null}
    </section>
  );
}
