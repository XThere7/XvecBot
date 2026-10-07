"use client";

import * as React from "react";
import { RotateCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { IndeterminateProgress } from "@/components/ui/indeterminate-progress";
import { pluralise } from "@/lib/format";
import type { DocStatus } from "@/types/api";

const STATUS_COPY: Record<DocStatus, { label: string; tone: "neutral" | "warning" | "success" | "danger"; animated?: boolean }> = {
  uploaded: { label: "Uploaded", tone: "neutral" },
  processing: { label: "Training…", tone: "warning", animated: true },
  ready: { label: "Ready", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
};

export type TrainingStatusIndicatorProps = {
  status: DocStatus;
  chunkCount?: number;
  onRetry?: () => void;
  retrying?: boolean;
  /** Past the 10-minute poll cap. */
  slow?: boolean;
};

/**
 * The four document statuses, and only four. `processing` is the single
 * animated state and it respects prefers-reduced-motion via the CSS layer.
 */
export function TrainingStatusIndicator({
  status,
  chunkCount,
  onRetry,
  retrying = false,
  slow = false,
}: TrainingStatusIndicatorProps) {
  const config = STATUS_COPY[status];

  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={config.tone} dot animated={config.animated}>
          {config.label}
        </Badge>

        {status === "ready" && (
          /* 0 chunks is shown on purpose — it means nothing searchable was produced. */
          <span className="text-2xs text-tertiary">{pluralise(chunkCount ?? 0, "chunk")}</span>
        )}

        {status === "failed" && onRetry && (
          <Button
            variant="ghost"
            size="sm"
            loading={retrying}
            iconLeft={!retrying && <RotateCw aria-hidden className="h-3.5 w-3.5" />}
            onClick={onRetry}
          >
            Retry
          </Button>
        )}
      </div>

      {status === "processing" && (
        <>
          <IndeterminateProgress />
          <span className="text-2xs text-tertiary">
            {slow ? "Taking longer than expected" : "Indexing your document"}
          </span>
        </>
      )}
    </div>
  );
}