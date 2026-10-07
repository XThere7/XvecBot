"use client";

import * as React from "react";
import { Ban, Code2, Pencil, RefreshCw, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { RelativeTime } from "@/components/ui/relative-time";
import { RowMenu } from "@/components/ui/dropdown-menu";
import { Toggle } from "@/components/ui/toggle";
import { formatNumber } from "@/lib/format";
import type { EmbedToken } from "@/types/api";

export type TokenTableProps = {
  tokens: EmbedToken[];
  loading: boolean;
  onEdit: (token: EmbedToken) => void;
  onDelete: (token: EmbedToken) => void;
  onRevoke: (token: EmbedToken) => void;
  onReactivate: (token: EmbedToken) => void;
  onCopySnippet: (token: EmbedToken) => void;
};

export function TokenTable({
  tokens,
  loading,
  onEdit,
  onDelete,
  onRevoke,
  onReactivate,
  onCopySnippet,
}: TokenTableProps) {
  const columns: DataTableColumn<EmbedToken>[] = [
    {
      id: "label",
      header: "Label",
      primary: true,
      cell: (token) => (
        <div className="min-w-0">
          <p className="truncate text-base text-primary">{token.label}</p>
          {/* Masked by the API: first 8 characters + "…". Never revealed here. */}
          <p className="mt-0.5 font-mono text-2xs text-tertiary">{token.token}</p>
        </div>
      ),
    },
    {
      id: "is_active",
      header: "Status",
      cell: (token) => (
        <div className="flex items-center gap-2">
          <Toggle
            checked={token.is_active}
            size="sm"
            label={`${token.label} is ${token.is_active ? "active" : "inactive"}`}
            onCheckedChange={(next) =>
              next ? onReactivate(token) : onRevoke(token)
            }
          />
          <span className="inline-flex items-center gap-1.5 text-xs text-secondary">
            <span
              aria-hidden
              className={
                token.is_active
                  ? "h-1.5 w-1.5 rounded-full bg-success-500"
                  : "h-1.5 w-1.5 rounded-full bg-neutral-500"
              }
            />
            {token.is_active ? "Active" : "Inactive"}
          </span>
        </div>
      ),
    },
    {
      id: "origins",
      header: "Allowed origins",
      cell: (token) =>
        token.allowed_origins && token.allowed_origins.length > 0 ? (
          <span className="flex flex-wrap gap-1">
            {token.allowed_origins.slice(0, 2).map((origin) => (
              <Badge key={origin} tone="neutral" className="font-mono">
                {origin}
              </Badge>
            ))}
            {token.allowed_origins.length > 2 && (
              <Badge tone="neutral">+{token.allowed_origins.length - 2}</Badge>
            )}
          </span>
        ) : (
          <span className="text-sm text-tertiary">Any origin</span>
        ),
    },
    {
      id: "request_count",
      header: "Requests",
      secondary: true,
      cell: (token) => (
        <span className="font-mono text-sm text-secondary">
          {formatNumber(token.request_count)}
        </span>
      ),
    },
    {
      id: "last_used_at",
      header: "Last used",
      secondary: true,
      cell: (token) =>
        token.last_used_at ? (
          <RelativeTime date={token.last_used_at} className="text-sm text-secondary" />
        ) : (
          <span className="text-sm text-tertiary">Never</span>
        ),
    },
    {
      id: "created_at",
      header: "Created",
      secondary: true,
      cell: (token) => (
        <RelativeTime date={token.created_at} className="text-sm text-secondary" />
      ),
    },
    {
      id: "actions",
      header: "Actions",
      align: "right",
      cell: (token) => (
        <RowMenu
          label={`Actions for ${token.label}`}
          items={[
            {
              label: "Copy snippet",
              icon: Code2,
              description: "Reveals the full token once more",
              onSelect: () => onCopySnippet(token),
            },
            { label: "Edit label & origins", icon: Pencil, onSelect: () => onEdit(token) },
            token.is_active
              ? {
                  label: "Revoke token",
                  icon: Ban,
                  tone: "danger",
                  description: "The widget stops responding immediately",
                  onSelect: () => onRevoke(token),
                }
              : {
                  label: "Reactivate token",
                  icon: RefreshCw,
                  onSelect: () => onReactivate(token),
                },
            {
              label: "Delete token",
              icon: Trash2,
              tone: "danger",
              onSelect: () => onDelete(token),
            },
          ]}
        />
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={tokens}
      rowKey={(token) => token.id}
      loading={loading}
      skeletonRows={4}
      emptyState={null}
    />
  );
}
