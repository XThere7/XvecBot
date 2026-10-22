"use client";

import * as React from "react";
import { Ban, Pencil, RefreshCw, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { RelativeTime } from "@/components/ui/relative-time";
import { RowMenu } from "@/components/ui/dropdown-menu";
import { Toggle } from "@/components/ui/toggle";
import { formatNumber, parseApiDate } from "@/lib/format";
import type { Agent, DeveloperApiKey } from "@/types/api";

export type ApiKeyTableProps = {
  keys: DeveloperApiKey[];
  agentsById: Map<string, Agent>;
  loading: boolean;
  onEdit: (key: DeveloperApiKey) => void;
  onRevoke: (key: DeveloperApiKey) => void;
  onReactivate: (key: DeveloperApiKey) => void;
  onDelete: (key: DeveloperApiKey) => void;
};

function isExpired(key: DeveloperApiKey): boolean {
  const expiry = parseApiDate(key.expires_at);
  return Boolean(expiry && expiry.getTime() <= Date.now());
}

function accessLabel(key: DeveloperApiKey): string {
  if (key.allowed_agents === null) return "All agents";
  if (key.allowed_agents.length === 0) return "No agents";
  return `${key.allowed_agents.length} agent${key.allowed_agents.length === 1 ? "" : "s"}`;
}

export function ApiKeyTable({
  keys,
  agentsById,
  loading,
  onEdit,
  onRevoke,
  onReactivate,
  onDelete,
}: ApiKeyTableProps) {
  const columns: DataTableColumn<DeveloperApiKey>[] = [
    {
      id: "name",
      header: "Key",
      primary: true,
      cell: (key) => (
        <div className="min-w-0">
          <p className="truncate text-base text-primary">{key.name}</p>
          <p className="mt-0.5 font-mono text-2xs text-tertiary">
            {key.key_prefix}…
          </p>
        </div>
      ),
    },
    {
      id: "status",
      header: "Status",
      cell: (key) => {
        const expired = isExpired(key);
        const active = Boolean(key.is_active) && !expired;
        return (
          <div className="flex items-center gap-2">
            <Toggle
              checked={Boolean(key.is_active)}
              size="sm"
              disabled={expired}
              label={`${key.name} is ${active ? "active" : "inactive"}`}
              onCheckedChange={(next) =>
                next ? onReactivate(key) : onRevoke(key)
              }
            />
            {expired ? (
              <Badge tone="warning">Expired</Badge>
            ) : (
              <span className="inline-flex items-center gap-1.5 text-xs text-secondary">
                <span
                  aria-hidden
                  className={`h-1.5 w-1.5 rounded-full ${
                    active ? "bg-success-500" : "bg-neutral-500"
                  }`}
                />
                {active ? "Active" : "Revoked"}
              </span>
            )}
          </div>
        );
      },
    },
    {
      id: "access",
      header: "Access",
      cell: (key) => {
        if (key.allowed_agents === null) {
          return <Badge tone="info">All agents</Badge>;
        }
        return (
          <div className="flex flex-wrap gap-1" title={accessLabel(key)}>
            {key.allowed_agents.slice(0, 2).map((agentId) => (
              <Badge key={agentId} tone="neutral">
                {agentsById.get(agentId)?.name ?? "Unknown agent"}
              </Badge>
            ))}
            {key.allowed_agents.length > 2 && (
              <Badge tone="neutral">+{key.allowed_agents.length - 2}</Badge>
            )}
            {key.allowed_agents.length === 0 && (
              <Badge tone="warning">No agents</Badge>
            )}
          </div>
        );
      },
    },
    {
      id: "request_count",
      header: "Requests",
      secondary: true,
      cell: (key) => (
        <span className="font-mono text-sm text-secondary">
          {formatNumber(key.request_count)}
        </span>
      ),
    },
    {
      id: "last_used_at",
      header: "Last used",
      secondary: true,
      cell: (key) =>
        key.last_used_at ? (
          <RelativeTime date={key.last_used_at} className="text-sm text-secondary" />
        ) : (
          <span className="text-sm text-tertiary">Never</span>
        ),
    },
    {
      id: "expires_at",
      header: "Expires",
      secondary: true,
      cell: (key) =>
        key.expires_at ? (
          <RelativeTime date={key.expires_at} className="text-sm text-secondary" />
        ) : (
          <span className="text-sm text-tertiary">Never</span>
        ),
    },
    {
      id: "actions",
      header: "Actions",
      align: "right",
      cell: (key) => (
        <RowMenu
          label={`Actions for ${key.name}`}
          items={[
            {
              label: "Edit name & access",
              icon: Pencil,
              onSelect: () => onEdit(key),
            },
            key.is_active
              ? {
                  label: "Revoke key",
                  icon: Ban,
                  tone: "danger",
                  description: "API calls stop immediately",
                  onSelect: () => onRevoke(key),
                }
              : {
                  label: "Reactivate key",
                  icon: RefreshCw,
                  disabled: isExpired(key),
                  description: isExpired(key) ? "This key has expired" : undefined,
                  onSelect: () => onReactivate(key),
                },
            {
              label: "Delete key",
              icon: Trash2,
              tone: "danger",
              description: "Permanently removes the key",
              onSelect: () => onDelete(key),
            },
          ]}
        />
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={keys}
      rowKey={(key) => key.id}
      loading={loading}
      skeletonRows={4}
      emptyState={null}
    />
  );
}
