"use client";

import Link from "next/link";
import { AdminDataTable } from "@/components/admin/admin-data-table";
import { ADMIN_HOME, formatEAT, formatNumber } from "@/lib/admin";

type WorkspaceRow = {
  id: string;
  name: string;
  owner_email: string;
  plan: string;
  agents: number;
  documents: number;
  chunks: number;
  last_activity: string | null;
  created_at: string;
};

export default function AdminWorkspacesPage() {
  return (
    <AdminDataTable<WorkspaceRow>
      title="Workspaces"
      path="/workspaces"
      sortKeys={["created_at", "name", "plan"]}
      columns={[
        { key: "name", header: "Name", render: (row) => row.name },
        { key: "owner", header: "Owner", render: (row) => row.owner_email },
        { key: "plan", header: "Plan", render: (row) => row.plan },
        { key: "agents", header: "Agents", render: (row) => formatNumber(row.agents) },
        { key: "documents", header: "Docs", render: (row) => formatNumber(row.documents) },
        { key: "chunks", header: "Chunks", render: (row) => formatNumber(row.chunks) },
        { key: "activity", header: "Last activity", render: (row) => formatEAT(row.last_activity) },
        { key: "created", header: "Created", render: (row) => formatEAT(row.created_at) },
      ]}
      actions={(row) => (
        <Link href={`${ADMIN_HOME}/workspaces/${row.id}`} className="text-xs text-accent-300 hover:underline">
          Open
        </Link>
      )}
    />
  );
}
