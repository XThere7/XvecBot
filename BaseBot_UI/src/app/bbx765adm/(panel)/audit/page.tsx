"use client";

import { AdminDataTable } from "@/components/admin/admin-data-table";
import { ADMIN_HOME, formatEAT } from "@/lib/admin";

type AuditRow = {
  id: string;
  ts: string;
  actor_email: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  summary: string;
  ip: string | null;
};

export default function AdminAuditPage() {
  return (
    <div className="flex flex-col gap-4">
      <AdminDataTable<AuditRow>
        title="Audit log (append-only)"
        path="/audit"
        sortKeys={["ts", "action", "actor_email"]}
        columns={[
          { key: "ts", header: "When", render: (row) => formatEAT(row.ts) },
          { key: "actor", header: "Actor", render: (row) => row.actor_email ?? "—" },
          { key: "action", header: "Action", render: (row) => row.action },
          { key: "target", header: "Target", render: (row) => `${row.target_type ?? ""} ${row.target_id ?? ""}` },
          { key: "summary", header: "Summary", render: (row) => row.summary },
          { key: "ip", header: "IP", render: (row) => row.ip ?? "—" },
        ]}
      />
      <p className="text-xs text-tertiary">
        Rows are append-only at the database level; exports (CSV) are themselves
        audited.
      </p>
    </div>
  );
}
