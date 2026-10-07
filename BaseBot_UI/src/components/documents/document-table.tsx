"use client";

import * as React from "react";
import { MoreHorizontal, Play, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { RowMenu } from "@/components/ui/dropdown-menu";
import { RelativeTime } from "@/components/ui/relative-time";
import { TrainingStatusIndicator } from "./training-status-indicator";
import { EmptyState } from "@/components/ui/empty-state";
import { FileSpreadsheet } from "lucide-react";
import { formatBytes } from "@/lib/format";
import type { WorkspaceDocument } from "@/types/api";

export type PendingUpload = {
  localId: string;
  filename: string;
  sizeBytes: number;
  state: "uploading" | "failed";
  error?: string;
};

export type DocumentTableProps = {
  documents: WorkspaceDocument[];
  pending: PendingUpload[];
  onCancelPending: (localId: string) => void;
  onDelete: (document: WorkspaceDocument) => void;
  onTrain: (document: WorkspaceDocument) => void;
  retryingIds: string[];
  slowIds: string[];
  loading: boolean;
  emptyState: React.ReactNode;
};

export function DocumentTable({
  documents,
  pending,
  onCancelPending,
  onDelete,
  onTrain,
  retryingIds,
  slowIds,
  loading,
  emptyState,
}: DocumentTableProps) {
  const columns: DataTableColumn<WorkspaceDocument>[] = [
    {
      id: "filename",
      header: "Document",
      primary: true,
      cell: (document) => (
        <div className="min-w-0">
          <p className="truncate text-base text-primary">{document.filename}</p>
          <div className="mt-1 flex items-center gap-2">
            <Badge tone="neutral">{document.file_type.toUpperCase()}</Badge>
            <span className="text-2xs text-tertiary">
              {formatBytes(document.size_bytes)}
            </span>
          </div>
        </div>
      ),
    },
    {
      id: "status",
      header: "Status",
      cell: (document) => (
        <TrainingStatusIndicator
          status={document.status}
          chunkCount={document.chunk_count}
          onRetry={document.status === "failed" ? () => onTrain(document) : undefined}
          retrying={retryingIds.includes(document.id)}
          slow={slowIds.includes(document.id)}
        />
      ),
    },
    {
      id: "created_at",
      header: "Uploaded",
      secondary: true,
      cell: (document) => (
        <RelativeTime date={document.created_at} className="text-sm text-secondary" />
      ),
    },
    {
      id: "actions",
      header: "Actions",
      align: "right",
      cell: (document) => (
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
      ),
    },
  ];

  const showEmpty = !loading && documents.length === 0 && pending.length === 0;

  return (
    <div className="flex flex-col gap-3">
      <DataTable
        columns={columns}
        rows={documents}
        rowKey={(document) => document.id}
        loading={loading}
        skeletonRows={4}
        emptyState={emptyState}
      />

      {/* Optimistic rows: visible immediately, removed locally on cancel. */}
      {pending.length > 0 && !showEmpty && (
        <ul className="flex flex-col gap-2">
          {pending.map((row) => (
            <li
              key={row.localId}
              className="flex items-center justify-between gap-3 rounded-md border border-subtle bg-surface px-4 py-3"
            >
              <div className="min-w-0">
                <p className="truncate text-base text-primary">{row.filename}</p>
                <p className="mt-0.5 text-2xs text-tertiary">
                  {formatBytes(row.sizeBytes)}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {row.state === "uploading" ? (
                  <Badge tone="neutral" dot>
                    Upload…
                  </Badge>
                ) : (
                  <span className="text-2xs text-danger-400">{row.error}</span>
                )}
                <button
                  type="button"
                  onClick={() => onCancelPending(row.localId)}
                  aria-label={`Remove ${row.filename}`}
                  title="Hide this row — the upload may still complete"
                  className="rounded-sm p-1 text-tertiary transition-colors hover:bg-surface-hover hover:text-primary"
                >
                  <MoreHorizontal aria-hidden className="h-4 w-4" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function DocumentsEmptyState({ onUpload }: { onUpload: () => void }) {
  return (
    <EmptyState
      icon={FileSpreadsheet}
      title="No documents yet"
      description="Upload your first document to give your agents something to answer from. PDF, TXT or DOCX."
      actionLabel="Upload document"
      onAction={onUpload}
    />
  );
}