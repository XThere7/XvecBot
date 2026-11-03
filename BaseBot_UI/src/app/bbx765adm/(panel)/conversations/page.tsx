"use client";

import { AdminDataTable } from "@/components/admin/admin-data-table";
import { ADMIN_HOME, formatEAT, formatNumber } from "@/lib/admin";

type ConversationRow = {
  id: string;
  title: string;
  workspace_id: string;
  agent_id: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
};

export default function AdminConversationsPage() {
  return (
    <div className="flex flex-col gap-4">
      <AdminDataTable<ConversationRow>
        title="Conversations (aggregate — no content)"
        path="/conversations"
        columns={[
          { key: "title", header: "Title", render: (row) => row.title || "Untitled" },
          { key: "workspace", header: "Workspace", render: (row) => row.workspace_id },
          { key: "messages", header: "Messages", render: (row) => formatNumber(row.message_count) },
          { key: "updated", header: "Last activity", render: (row) => formatEAT(row.updated_at) },
        ]}
        actions={(row) => (
          <a
            href={`${ADMIN_HOME}/conversations/${row.id}`}
            className="text-xs text-accent-300 hover:underline"
          >
            View content
          </a>
        )}
      />
      <p className="text-xs text-tertiary">
        Viewing message content requires the conversations.read permission and
        is written to the audit log. There is no bulk content export.
      </p>
    </div>
  );
}
