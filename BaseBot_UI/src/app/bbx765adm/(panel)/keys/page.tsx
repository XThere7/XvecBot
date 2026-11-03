"use client";

import { AdminDataTable } from "@/components/admin/admin-data-table";
import { ADMIN_HOME, formatEAT, formatNumber } from "@/lib/admin";

type KeyRow = {
  id: string;
  kind?: string;
  name?: string;
  label?: string;
  owner_email: string;
  key_prefix?: string;
  token_prefix?: string;
  is_active: number;
  request_count: number;
  last_used_at: string | null;
  created_at: string;
};

export default function AdminKeysPage() {
  return (
    <div className="flex flex-col gap-4">
      <AdminDataTable<KeyRow>
        title="API keys and embed tokens"
        path="/keys"
        columns={[
          {
            key: "kind",
            header: "Type",
            render: (row) => row.kind ?? (row.key_prefix ? "developer" : "embed"),
          },
          { key: "owner", header: "Owner", render: (row) => row.owner_email },
          {
            key: "name",
            header: "Name / label",
            render: (row) => row.name ?? row.label ?? "—",
          },
          {
            key: "prefix",
            header: "Prefix",
            render: (row) => row.key_prefix ?? row.token_prefix ?? "—",
          },
          {
            key: "active",
            header: "Active",
            render: (row) =>
              row.is_active ? "yes" : <span className="text-danger-400">revoked</span>,
          },
          { key: "requests", header: "Requests", render: (row) => formatNumber(row.request_count) },
          { key: "last", header: "Last used", render: (row) => formatEAT(row.last_used_at) },
          { key: "created", header: "Created", render: (row) => formatEAT(row.created_at) },
        ]}
      />
      <p className="text-xs text-tertiary">
        Only prefixes are shown — full secrets are never returned by the API.
        Revocation lives in the API (keys.manage permission).
      </p>
    </div>
  );
}
