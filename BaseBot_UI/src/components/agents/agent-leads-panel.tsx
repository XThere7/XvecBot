"use client";

import * as React from "react";
import { Download, Trash2, Users } from "lucide-react";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { Modal } from "@/components/ui/modal";
import { SearchInput } from "@/components/ui/search-input";
import { Select } from "@/components/ui/select";
import { StatCard } from "@/components/ui/stat-card";
import { formatAbsoluteTime } from "@/lib/format";
import { toast } from "@/lib/toast";
import {
  downloadCsv,
  useDeleteLead,
  useLeads,
} from "@/hooks/use-engagement";
import type { Lead } from "@/types/api";

export function AgentLeadsPanel({
  wsId,
  agentId,
}: {
  wsId: string;
  agentId: string;
}) {
  const [search, setSearch] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [selected, setSelected] = React.useState<Lead | null>(null);
  const [pendingDelete, setPendingDelete] = React.useState<Lead | null>(null);
  const leads = useLeads(wsId, agentId, search, status);
  const deleteLead = useDeleteLead(wsId, agentId);

  const stats = leads.data?.stats;

  const columns: DataTableColumn<Lead>[] = [
    {
      id: "name",
      header: "Lead",
      primary: true,
      cell: (lead) => (
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-primary">
            {lead.full_name || "Unnamed lead"}
          </p>
          <p className="truncate text-2xs text-tertiary">
            {lead.email || lead.phone || "No contact details"}
          </p>
        </div>
      ),
    },
    {
      id: "company",
      header: "Company",
      cell: (lead) => lead.company || "—",
    },
    {
      id: "interest",
      header: "Interest",
      secondary: true,
      cell: (lead) => (
        <span className="line-clamp-2 text-xs text-secondary">
          {lead.interest || "—"}
        </span>
      ),
    },
    {
      id: "status",
      header: "Status",
      cell: (lead) => (
        <Badge tone={lead.status === "complete" ? "success" : "warning"}>
          {lead.status === "complete" ? "Complete" : "Partial"}
        </Badge>
      ),
    },
    {
      id: "consent",
      header: "Consent",
      cell: (lead) => (
        <Badge tone={lead.consent_given ? "info" : "neutral"}>
          {lead.consent_given ? "Given" : "Not recorded"}
        </Badge>
      ),
    },
    {
      id: "created",
      header: "Captured",
      align: "right",
      cell: (lead) => (
        <span className="text-xs text-tertiary">
          {formatAbsoluteTime(lead.created_at)}
        </span>
      ),
    },
  ];

  const exportCsv = async () => {
    try {
      await downloadCsv(
        `/workspaces/${wsId}/agents/${agentId}/leads/export`,
        "leads.csv",
      );
      toast.success({ title: "Leads exported" });
    } catch {
      toast.error({ title: "Could not export leads" });
    }
  };

  const remove = async () => {
    if (!pendingDelete) return;
    try {
      await deleteLead.mutateAsync(pendingDelete.id);
      toast.success({ title: "Lead deleted" });
      setPendingDelete(null);
      setSelected(null);
    } catch {
      toast.error({ title: "Could not delete the lead" });
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium text-primary">Captured leads</h2>
          <p className="text-sm text-secondary">
            Contact details collected by this agent, deduplicated by email or phone.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => void exportCsv()}
          iconLeft={<Download aria-hidden className="h-4 w-4" />}
        >
          Export CSV
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total leads" value={stats?.total ?? 0} loading={leads.isLoading} icon={Users} />
        <StatCard label="Complete" value={stats?.complete ?? 0} loading={leads.isLoading} />
        <StatCard label="Partial" value={stats?.partial ?? 0} loading={leads.isLoading} />
        <StatCard label="Captured (7 days)" value={stats?.last_7_days ?? 0} loading={leads.isLoading} hint="Rolling seven-day window" />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder="Search name, email, company…"
          label="Search leads"
        />
        <div className="w-40">
          <Select
            options={[
              { value: "", label: "All statuses" },
              { value: "complete", label: "Complete" },
              { value: "partial", label: "Partial" },
            ]}
            value={status}
            onValueChange={setStatus}
            placeholder="All statuses"
          />
        </div>
      </div>

      {leads.isError ? (
        <AlertBanner tone="danger" title="Leads could not be loaded">
          {leads.error instanceof Error ? leads.error.message : "Please try again."}
        </AlertBanner>
      ) : (
        <DataTable
          columns={columns}
          rows={leads.data?.items ?? []}
          rowKey={(lead) => lead.id}
          loading={leads.isLoading}
          onRowClick={setSelected}
          emptyState={
            <EmptyState
              icon={Users}
              title="No leads yet"
              description="When a visitor submits the lead form — in chat, on your site, or through a published form — their details appear here."
            />
          }
        />
      )}

      <Modal
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected?.full_name || "Lead"}
        description={selected?.email || selected?.phone || undefined}
        size="md"
        footer={
          selected ? (
            <div className="flex justify-between gap-3">
              <Button
                variant="dangerGhost"
                size="sm"
                onClick={() => setPendingDelete(selected)}
                iconLeft={<Trash2 aria-hidden className="h-4 w-4" />}
              >
                Delete lead
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setSelected(null)}>
                Close
              </Button>
            </div>
          ) : undefined
        }
      >
        {selected && (
          <div className="flex flex-col gap-4 text-sm">
            <dl className="grid grid-cols-2 gap-3">
              {[
                ["Email", selected.email],
                ["Phone", selected.phone],
                ["Company", selected.company],
                ["Budget", selected.budget],
                ["Interest", selected.interest],
                ["Status", selected.status],
                ["Consent", selected.consent_given ? "Given" : "Not recorded"],
                ["Captured", formatAbsoluteTime(selected.created_at)],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-2xs uppercase tracking-wide text-tertiary">{label}</dt>
                  <dd className="mt-0.5 break-words text-secondary">{value || "—"}</dd>
                </div>
              ))}
            </dl>
            {selected.notes && (
              <div>
                <p className="text-2xs uppercase tracking-wide text-tertiary">Notes</p>
                <p className="mt-1 whitespace-pre-wrap text-secondary">{selected.notes}</p>
              </div>
            )}
            {Object.keys(selected.custom_fields).length > 0 && (
              <div>
                <p className="text-2xs uppercase tracking-wide text-tertiary">Extra fields</p>
                <dl className="mt-1 flex flex-col gap-1">
                  {Object.entries(selected.custom_fields).map(([key, value]) => (
                    <div key={key} className="flex justify-between gap-3">
                      <dt className="text-tertiary">{key}</dt>
                      <dd className="text-secondary">{String(value)}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
            {selected.consent_text && (
              <p className="rounded-sm border border-subtle bg-surface-raised p-3 text-xs text-tertiary">
                Consent: {selected.consent_text}
              </p>
            )}
          </div>
        )}
      </Modal>

      <ConfirmationDialog
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title="Delete this lead?"
        body="The lead and its consent record will be permanently removed. This cannot be undone."
        confirmLabel="Delete lead"
        confirmLoading={deleteLead.isPending}
        onConfirm={() => void remove()}
      />
    </div>
  );
}
