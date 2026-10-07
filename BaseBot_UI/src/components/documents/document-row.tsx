"use client";

import * as React from "react";
import { Play, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { RowMenu } from "@/components/ui/dropdown-menu";
import { RelativeTime } from "@/components/ui/relative-time";
import { TrainingStatusIndicator } from "./training-status-indicator";
import { formatBytes } from "@/lib/format";
import type { WorkspaceDocument } from "@/types/api";

export type DocumentRowProps = {
  document: WorkspaceDocument;
  retrying: boolean;
  slow: boolean;
  onTrain: (document: WorkspaceDocument) => void;
  onDelete: (document: WorkspaceDocument) => void;
};

/**
 * One document row: filename + type + size, the training lifecycle, the upload
 * time and the row actions. Kept separate from the table shell so the row can
 * be reused by the stacked-card mobile layout.
 */
export function DocumentRow({
  document,
  retrying,
  slow,
  onTrain,
  onDelete,
}: DocumentRowProps) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
      <div className="min-w-0 flex-1">
        <p className="truncate text-base text-primary">{document.filename}</p>
        <div className="mt-1 flex items-center gap-2">
          <Badge tone="neutral">{document.file_type.toUpperCase()}</Badge>
          <span className="text-2xs text-tertiary">
            {formatBytes(document.size_bytes)}
          </span>
        </div>
      </div>

      <div className="min-w-0 sm:w-56">
        <TrainingStatusIndicator
          status={document.status}
          chunkCount={document.chunk_count}
          onRetry={document.status === "failed" ? () => onTrain(document) : undefined}
          retrying={retrying}
          slow={slow}
        />
      </div>

      <div className="hidden sm:block sm:w-24">
        <RelativeTime date={document.created_at} className="text-sm text-secondary" />
      </div>

      <div className="flex shrink-0 items-center sm:justify-end">
        <RowMenu
          label={`Actions for ${document.filename}`}
          items={[
            {
              label: "Train now",
              icon: Play,
              disabled: document.status === "processing",
              description:
                document.status === "ready"
                  ? "Already trained — this re-indexes the document"
                  : undefined,
              onSelect: () => onTrain(document),
            },
            {
              label: "Delete document",
              icon: Trash2,
              tone: "danger",
              onSelect: () => onDelete(document),
            },
          ]}
        />
      </div>
    </div>
  );
}

export function DocumentRowSkeleton() {
  return (
    <div className="flex items-center gap-4">
      <div className="min-w-0 flex-1">
        <div className="skeleton-shimmer h-4 w-2/3 rounded-sm" />
        <div className="skeleton-shimmer mt-2 h-3 w-1/4 rounded-sm" />
      </div>
      <div className="skeleton-shimmer h-6 w-24 rounded-chip" />
      <div className="skeleton-shimmer hidden h-4 w-24 rounded-sm sm:block" />
    </div>
  );
}
