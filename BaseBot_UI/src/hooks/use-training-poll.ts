"use client";

import * as React from "react";
import { ApiRequestError, apiGet } from "@/lib/api-client";
import {
  TRAINING_POLL_CAP_MS,
  TRAINING_POLL_INTERVAL_MS,
} from "@/lib/constants";
import { documentStatusSchema } from "@/schemas/document";
import type { DocStatus, WorkspaceDocument } from "@/types/api";

export type TrainingPollOptions = {
  wsId: string;
  /** The document list. Only non-terminal rows are polled. */
  documents: WorkspaceDocument[] | undefined;
  /** Patch a row in the cached list. */
  onUpdate: (docId: string, status: DocStatus, chunkCount: number) => void;
  /** Fired exactly once per document, emitted by list state — not per observer. */
  onComplete?: (docId: string, chunkCount: number) => void;
  onFailed?: (docId: string) => void;
  /** 404 — the document was deleted elsewhere. */
  onRemoved?: (docId: string) => void;
  /** Still processing after the 10-minute cap. */
  onTimeout?: (docId: string) => void;
};

const isPolling = (doc: WorkspaceDocument) =>
  doc.status === "uploaded" || doc.status === "processing";

/**
 * The document training poll loop (frontendbot.md §6.4).
 *
 *  - one tick every 3000 ms
 *  - runs for documents in `uploaded` or `processing`
 *  - stops only on ready | failed, on 404, on unmount, or at the 10-minute cap
 *  - never stops on a network error or a 5xx — the next tick retries
 *  - a 409 from train never starts a second poller: the list already lists the
 *    document as processing, so this loop adopts it
 */
export function useTrainingPoll({
  wsId,
  documents,
  onUpdate,
  onComplete,
  onFailed,
  onRemoved,
  onTimeout,
}: TrainingPollOptions) {
  const pendingIds = React.useMemo(
    () => (documents ?? []).filter(isPolling).map((doc) => doc.id),
    [documents],
  );
  const key = pendingIds.join(",");

  // Refs, not state: the effect restarts whenever the pending set changes and
  // the "toast once per document" guarantee must survive that.
  const startedRef = React.useRef(new Map<string, number>());
  const notifiedRef = React.useRef(new Set<string>());
  const timedOutRef = React.useRef(new Set<string>());
  const pendingRef = React.useRef<string[]>(pendingIds);
  pendingRef.current = pendingIds;

  const callbacks = React.useRef({ onUpdate, onComplete, onFailed, onRemoved, onTimeout });
  callbacks.current = { onUpdate, onComplete, onFailed, onRemoved, onTimeout };

  const [timedOutIds, setTimedOutIds] = React.useState<string[]>([]);

  React.useEffect(() => {
    // Drop bookkeeping for documents that are gone or already terminal.
    const live = new Set(pendingIds);
    for (const id of Array.from(startedRef.current.keys())) {
      if (!live.has(id)) startedRef.current.delete(id);
    }
    setTimedOutIds((current) => current.filter((id) => live.has(id)));
    if (pendingIds.length === 0) return;
    for (const id of pendingIds) {
      if (!startedRef.current.has(id)) startedRef.current.set(id, Date.now());
    }
    // `key` is the serialised pending set. Re-running on the array identity
    // would restart the bookkeeping on every list refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  React.useEffect(() => {
    if (!wsId || pendingIds.length === 0) return;

    // The effect is keyed on the serialised pending set (`key`); `pendingIds`
    // is only read for its length guard and to bail when nothing is polling.
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const forget = (docId: string) => {
      startedRef.current.delete(docId);
      timedOutRef.current.delete(docId);
      // Cleared so a later retry of the same document can announce itself once.
      notifiedRef.current.delete(docId);
      setTimedOutIds((current) => current.filter((id) => id !== docId));
    };

    const tick = async () => {
      if (!alive) return;
      const ids = pendingRef.current;

      await Promise.all(
        ids.map(async (docId) => {
          if (!alive) return;
          if (timedOutRef.current.has(docId)) return;
          const startedAt = startedRef.current.get(docId) ?? Date.now();

          try {
            const status = documentStatusSchema.parse(
              await apiGet(`/workspaces/${wsId}/documents/${docId}/status`),
            );
            if (!alive) return;

            callbacks.current.onUpdate(docId, status.status, status.chunk_count);

            if (status.status === "ready" || status.status === "failed") {
              if (!notifiedRef.current.has(docId)) {
                notifiedRef.current.add(docId);
                if (status.status === "ready") {
                  callbacks.current.onComplete?.(docId, status.chunk_count);
                } else {
                  callbacks.current.onFailed?.(docId);
                }
              }
              forget(docId);
              return;
            }

            if (Date.now() - startedAt > TRAINING_POLL_CAP_MS) {
              timedOutRef.current.add(docId);
              setTimedOutIds((current) =>
                current.includes(docId) ? current : [...current, docId],
              );
              callbacks.current.onTimeout?.(docId);
            }
          } catch (error) {
            if (error instanceof ApiRequestError && error.status === 404) {
              if (!notifiedRef.current.has(docId)) {
                notifiedRef.current.add(docId);
                callbacks.current.onRemoved?.(docId);
              }
              forget(docId);
              return;
            }
            // Transient network error or 5xx: retry on the next tick.
          }
        }),
      );

      if (alive) timer = setTimeout(tick, TRAINING_POLL_INTERVAL_MS);
    };

    timer = setTimeout(tick, TRAINING_POLL_INTERVAL_MS);

    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wsId, key]);

  return { timedOutIds };
}