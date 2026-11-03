"use client";

import { AdminDataTable } from "@/components/admin/admin-data-table";
import { ADMIN_HOME, formatEAT, formatNumber } from "@/lib/admin";

type DocumentRow = {
  id: string;
  filename: string;
  file_type: string;
  status: string;
  size_bytes: number;
  chunk_count: number;
  owner_email: string;
  created_at: string;
};

export default function AdminKnowledgePage() {
  return (
    <div className="flex flex-col gap-8">
      <AdminDataTable<DocumentRow>
        title="Documents"
        path="/knowledge/documents"
        sortKeys={["created_at", "status", "size_bytes", "filename"]}
        columns={[
          { key: "filename", header: "File", render: (row) => row.filename },
          { key: "owner", header: "Owner", render: (row) => row.owner_email },
          {
            key: "status",
            header: "Status",
            render: (row) =>
              row.status === "failed" ? (
                <span className="text-danger-400">{row.status}</span>
              ) : (
                row.status
              ),
          },
          { key: "size", header: "Size", render: (row) => formatNumber(row.size_bytes) },
          { key: "chunks", header: "Chunks", render: (row) => formatNumber(row.chunk_count) },
          { key: "created", header: "Uploaded", render: (row) => formatEAT(row.created_at) },
        ]}
      />
      <AdminDataTable<DocumentRow & { url: string; pages_indexed: number; error_message: string | null }>
        title="Website sources"
        path="/knowledge/websites"
        columns={[
          { key: "url", header: "URL", render: (row) => row.url },
          { key: "owner", header: "Owner", render: (row) => row.owner_email },
          {
            key: "status",
            header: "Status",
            render: (row) =>
              row.status === "failed" ? (
                <span className="text-danger-400" title={row.error_message ?? ""}>
                  {row.status}
                </span>
              ) : (
                row.status
              ),
          },
          { key: "pages", header: "Pages", render: (row) => formatNumber(row.pages_indexed) },
          { key: "created", header: "Added", render: (row) => formatEAT(row.created_at) },
        ]}
      />
    </div>
  );
}
