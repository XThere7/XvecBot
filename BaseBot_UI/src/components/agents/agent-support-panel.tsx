"use client";

import * as React from "react";
import { LifeBuoy } from "lucide-react";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { Select } from "@/components/ui/select";
import { StatCard } from "@/components/ui/stat-card";
import { formatAbsoluteTime } from "@/lib/format";
import { toast } from "@/lib/toast";
import { useEscalations, useUpdateEscalation } from "@/hooks/use-engagement";
import type { Escalation } from "@/types/api";

export function AgentSupportPanel({
  wsId,
  agentId,
}: {
  wsId: string;
  agentId: string;
}) {
  const [status, setStatus] = React.useState("");
  const escalations = useEscalations(wsId, agentId, status);
  const update = useUpdateEscalation(wsId, agentId);
  const stats = escalations.data?.stats;

  const changeStatus = async (
    escalation: Escalation,
    next: "open" | "contacted" | "closed",
  ) => {
    try {
      await update.mutateAsync({ id: escalation.id, status: next });
      toast.success({ title: `Marked ${next}` });
    } catch {
      toast.error({ title: "Could not update the escalation" });
    }
  };

  const columns: DataTableColumn<Escalation>[] = [
    {
      id: "reason",
      header: "Request",
      primary: true,
      cell: (row) => (
        <div className="min-w-0 max-w-md">
          <p className="line-clamp-2 text-sm text-primary">{row.reason}</p>
          <p className="mt-0.5 text-2xs text-tertiary">
            {row.contact_email || row.contact_phone || "No contact details provided"}
          </p>
        </div>
      ),
    },
    {
      id: "contact",
      header: "Contact",
      secondary: true,
      cell: (row) => row.contact_name || "—",
    },
    {
      id: "status",
      header: "Status",
      cell: (row) => (
        <Badge
          tone={
            row.status === "open"
              ? "warning"
              : row.status === "contacted"
                ? "info"
                : "success"
          }
        >
          {row.status}
        </Badge>
      ),
    },
    {
      id: "created",
      header: "Created",
      align: "right",
      cell: (row) => (
        <span className="text-xs text-tertiary">{formatAbsoluteTime(row.created_at)}</span>
      ),
    },
    {
      id: "actions",
      header: "",
      align: "right",
      cell: (row) => (
        <div className="flex justify-end">
          <div className="w-36">
            <Select
              options={[
                { value: "open", label: "Open" },
                { value: "contacted", label: "Contacted" },
                { value: "closed", label: "Closed" },
              ]}
              value={row.status}
              onValueChange={(next) =>
                void changeStatus(row, next as "open" | "contacted" | "closed")
              }
              disabled={update.isPending}
            />
          </div>
        </div>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium text-primary">Support escalations</h2>
          <p className="text-sm text-secondary">
            Conversations where a visitor asked for a human, or the agent created
            an escalation through the support action.
          </p>
        </div>
        <div className="w-40">
          <Select
            options={[
              { value: "", label: "All statuses" },
              { value: "open", label: "Open" },
              { value: "contacted", label: "Contacted" },
              { value: "closed", label: "Closed" },
            ]}
            value={status}
            onValueChange={setStatus}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total" value={stats?.total ?? 0} loading={escalations.isLoading} icon={LifeBuoy} />
        <StatCard label="Open" value={stats?.open ?? 0} loading={escalations.isLoading} />
        <StatCard label="Contacted" value={stats?.contacted ?? 0} loading={escalations.isLoading} />
        <StatCard label="Closed" value={stats?.closed ?? 0} loading={escalations.isLoading} />
      </div>

      {escalations.isError ? (
        <AlertBanner tone="danger" title="Escalations could not be loaded">
          {escalations.error instanceof Error ? escalations.error.message : "Please try again."}
        </AlertBanner>
      ) : (
        <DataTable
          columns={columns}
          rows={escalations.data?.items ?? []}
          rowKey={(row) => row.id}
          loading={escalations.isLoading}
          emptyState={
            <EmptyState
              icon={LifeBuoy}
              title="No escalations"
              description="When a visitor asks for a human — for example “I need to speak to someone” — the request is queued here with the conversation context."
              action={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void escalations.refetch()}
                >
                  Refresh
                </Button>
              }
            />
          }
        />
      )}
    </div>
  );
}
