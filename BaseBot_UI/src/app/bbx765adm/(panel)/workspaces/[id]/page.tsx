"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { apiGet, apiPost } from "@/lib/api-client";
import { ADMIN_HOME, formatEAT } from "@/lib/admin";

type AgentRow = { id: string; name: string; model: string; is_active: number; created_at: string };
type WorkspaceDetail = {
  id: string;
  name: string;
  owner_email: string;
  plan: string;
  created_at: string;
  agents: AgentRow[];
  documents: { id: string; filename: string; status: string; size_bytes: number }[];
};

export default function AdminWorkspaceDetailPage() {
  const params = useParams<{ id: string }>();
  const [data, setData] = React.useState<WorkspaceDetail | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    apiGet<WorkspaceDetail>(`${ADMIN_HOME}/workspaces/${params.id}`, { skipAuthRedirect: true })
      .then(setData)
      .catch(() => setError("Could not load this workspace."));
  }, [params.id]);

  React.useEffect(load, [load]);

  async function toggle(agent: AgentRow) {
    const reason = window.prompt("Reason:") || "admin action";
    await apiPost(
      `${ADMIN_HOME}/workspaces/${params.id}/agents/${agent.id}/${agent.is_active ? "disable" : "enable"}`,
      { reason },
      { skipAuthRedirect: true },
    );
    load();
  }

  if (error) return <p className="text-sm text-danger-400">{error}</p>;
  if (!data) return <p className="text-sm text-secondary">Loading…</p>;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-lg text-primary">{data.name}</h2>
        <p className="text-sm text-secondary">
          {data.owner_email} · {data.plan} · created {formatEAT(data.created_at)}
        </p>
      </div>

      <section className="rounded-sm border border-subtle bg-surface p-4">
        <h3 className="mb-2 text-sm font-semibold text-primary">Agents</h3>
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-xs text-tertiary">
              <th className="py-1">Name</th>
              <th className="py-1">Model</th>
              <th className="py-1">Status</th>
              <th className="py-1">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.agents.map((agent) => (
              <tr key={agent.id} className="border-t border-subtle text-secondary">
                <td className="py-1.5">{agent.name}</td>
                <td className="py-1.5">{agent.model}</td>
                <td className="py-1.5">
                  {agent.is_active ? "active" : <span className="text-danger-400">disabled</span>}
                </td>
                <td className="py-1.5">
                  <button
                    type="button"
                    onClick={() => void toggle(agent)}
                    className={agent.is_active ? "text-xs text-danger-400 hover:underline" : "text-xs text-accent-300 hover:underline"}
                  >
                    {agent.is_active ? "Disable" : "Enable"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="rounded-sm border border-subtle bg-surface p-4">
        <h3 className="mb-2 text-sm font-semibold text-primary">Documents</h3>
        <ul className="flex flex-col gap-1 text-sm text-secondary">
          {data.documents.map((doc) => (
            <li key={doc.id} className="flex justify-between gap-3">
              <span>{doc.filename}</span>
              <span className={doc.status === "failed" ? "text-danger-400" : "text-tertiary"}>
                {doc.status} · {doc.size_bytes} B
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
