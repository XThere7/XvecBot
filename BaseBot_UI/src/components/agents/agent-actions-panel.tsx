"use client";

import * as React from "react";
import Link from "next/link";
import {
  ClipboardList,
  FileText,
  LifeBuoy,
  Lock,
  Play,
  Settings2,
  Sparkles,
  Users,
} from "lucide-react";
import { ActionConfigModal } from "./action-config-modal";
import { ActionFieldForm } from "@/components/actions/action-field-form";
import { AgentLeadsPanel } from "./agent-leads-panel";
import { AgentSupportPanel } from "./agent-support-panel";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/lib/toast";
import { workspaceHref } from "@/lib/routes";
import {
  useActionForm,
  useAgentActions,
  useSubmitAction,
  useUpsertAction,
} from "@/hooks/use-engagement";
import type { ActionCatalogEntry, ActionType } from "@/types/api";

const ICONS: Record<ActionType, React.ElementType> = {
  lead_capture: Users,
  data_collection: ClipboardList,
  custom_forms: FileText,
  knowledge_support: LifeBuoy,
};

function ActionTestModal({
  open,
  onClose,
  wsId,
  agentId,
  entry,
}: {
  open: boolean;
  onClose: () => void;
  wsId: string;
  agentId: string;
  entry: ActionCatalogEntry | null;
}) {
  const form = useActionForm(wsId, agentId, entry?.action?.id ?? null);
  const submit = useSubmitAction(wsId, agentId);
  const [result, setResult] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open) setResult(null);
  }, [open]);

  if (!entry) return null;

  const submitForm = async (values: Record<string, unknown>) => {
    try {
      const response = await submit.mutateAsync({
        actionId: entry.action?.id ?? "",
        data: values,
      });
      setResult(response.label);
      toast.success({ title: response.label });
    } catch (error) {
      const detail = (error as { body?: { detail?: unknown } })?.body?.detail as
        | { errors?: string[]; message?: string }
        | string
        | undefined;
      const message =
        typeof detail === "string"
          ? detail
          : detail?.errors?.join(" ") || "The action could not be completed.";
      setResult(message);
      toast.error({ title: "Action failed" });
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Test ${entry.name}`}
      description="This uses the real backend, validation and storage — not a preview."
      size="md"
      footer={
        <div className="flex justify-end">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      }
    >
      {result ? (
        <AlertBanner tone="success" title={result}>
          The record was written to your workspace. Open the Leads or Capture tab to
          review it.
        </AlertBanner>
      ) : form.isLoading ? (
        <Skeleton height={180} className="rounded-md" />
      ) : form.isError || !form.data ? (
        <AlertBanner tone="danger" title="Could not load the action form">
          {form.error instanceof Error ? form.error.message : "Please try again."}
        </AlertBanner>
      ) : (
        <ActionFieldForm
          fields={form.data.fields}
          submitLabel={form.data.submit_label || "Test action"}
          requireConsent={Boolean(form.data.require_consent)}
          consentText={form.data.consent_text}
          loading={submit.isPending}
          compact
          onSubmit={submitForm}
        />
      )}
    </Modal>
  );
}

export function AgentActionsPanel({
  wsId,
  agentId,
}: {
  wsId: string;
  agentId: string;
}) {
  const actions = useAgentActions(wsId, agentId);
  const upsert = useUpsertAction(wsId, agentId);
  const [section, setSection] = React.useState<"catalog" | "leads" | "support">(
    "catalog",
  );
  const [configEntry, setConfigEntry] = React.useState<ActionCatalogEntry | null>(null);
  const [testEntry, setTestEntry] = React.useState<ActionCatalogEntry | null>(null);

  const toggle = async (entry: ActionCatalogEntry, next: boolean) => {
    try {
      await upsert.mutateAsync({
        actionType: entry.action_type,
        body: {
          is_active: next,
          ...(entry.action ? {} : { config: entry.default_config }),
        },
      });
      toast.success({
        title: next ? `${entry.name} enabled` : `${entry.name} disabled`,
      });
    } catch (error) {
      const detail = (error as { body?: { detail?: { message?: string } } })?.body
        ?.detail;
      toast.error({
        title: detail?.message || "Could not update this action",
      });
    }
  };

  const sections = [
    { id: "catalog" as const, label: "Actions" },
    { id: "leads" as const, label: "Leads" },
    { id: "support" as const, label: "Support" },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-medium text-primary">Agent Actions</h1>
          <p className="mt-1 max-w-2xl text-sm text-secondary">
            Give this agent real capabilities: capture sales leads, collect
            structured data, publish forms and escalate to a human. Actions are
            executed by the backend with plan enforcement and tenant isolation.
          </p>
        </div>
        <Badge tone="accent" icon={<Sparkles aria-hidden className="h-3.5 w-3.5" />}>
          Standard+ for sales actions
        </Badge>
      </div>

      <div
        role="tablist"
        aria-label="Action sections"
        className="flex flex-wrap gap-1 border-b border-subtle"
      >
        {sections.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={section === item.id}
            onClick={() => setSection(item.id)}
            className={
              section === item.id
                ? "border-b-2 border-accent-500 px-3 py-2 text-sm font-medium text-primary"
                : "border-b-2 border-transparent px-3 py-2 text-sm text-tertiary hover:text-primary"
            }
          >
            {item.label}
          </button>
        ))}
      </div>

      {section === "catalog" && (
        <>
          {actions.isError ? (
            <AlertBanner tone="danger" title="Actions could not be loaded">
              {actions.error instanceof Error
                ? actions.error.message
                : "Please try again."}
            </AlertBanner>
          ) : actions.isLoading ? (
            <div className="grid gap-4 md:grid-cols-2">
              {Array.from({ length: 4 }).map((_, index) => (
                <Skeleton key={index} height={180} className="rounded-md" />
              ))}
            </div>
          ) : (actions.data?.catalog.length ?? 0) === 0 ? (
            <EmptyState
              icon={Sparkles}
              title="No actions available"
              description="The action catalogue is empty. This should not happen — check the backend log."
            />
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {actions.data?.catalog.map((entry) => {
                const Icon = ICONS[entry.action_type];
                const configured = Boolean(entry.action);
                const active = configured && Boolean(entry.action?.is_active);
                return (
                  <section
                    key={entry.action_type}
                    className="flex flex-col gap-4 rounded-md border border-subtle bg-surface p-5 shadow-elevation-1"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-3">
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-subtle bg-surface-raised text-accent-400">
                          <Icon aria-hidden className="h-4 w-4" />
                        </span>
                        <div>
                          <p className="text-2xs uppercase tracking-wide text-tertiary">
                            {entry.category}
                          </p>
                          <h2 className="text-base font-medium text-primary">
                            {entry.name}
                          </h2>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        {entry.plan_available ? (
                          <Badge tone={active ? "success" : configured ? "neutral" : "info"}>
                            {active ? "Active" : configured ? "Disabled" : "Not set up"}
                          </Badge>
                        ) : (
                          <Badge tone="warning" icon={<Lock aria-hidden className="h-3 w-3" />}>
                            Locked
                          </Badge>
                        )}
                      </div>
                    </div>

                    <p className="text-sm leading-5 text-secondary">{entry.description}</p>

                    {!entry.plan_available && (
                      <AlertBanner
                        tone="warning"
                        action={
                          <Button asChild variant="secondary" size="sm">
                            <Link href={workspaceHref(wsId, "billing")}>View plans</Link>
                          </Button>
                        }
                      >
                        {entry.locked_reason}
                      </AlertBanner>
                    )}

                    {configured && entry.plan_available && (
                      <div className="flex items-center justify-between gap-3 rounded-sm border border-subtle bg-surface-raised px-3 py-2">
                        <span className="text-xs text-secondary">Enabled for chat</span>
                        <input
                          type="checkbox"
                          aria-label={`Enable ${entry.name}`}
                          checked={Boolean(entry.action?.is_active)}
                          onChange={(event) =>
                            void toggle(entry, event.target.checked)
                          }
                          disabled={upsert.isPending}
                          className="h-4 w-4 accent-accent-500"
                        />
                      </div>
                    )}

                    <div className="mt-auto flex flex-wrap gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => setConfigEntry(entry)}
                        disabled={!entry.plan_available}
                        iconLeft={<Settings2 aria-hidden className="h-4 w-4" />}
                      >
                        {configured ? "Configure" : "Set up"}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setTestEntry(entry)}
                        disabled={!entry.plan_available || !configured}
                        iconLeft={<Play aria-hidden className="h-4 w-4" />}
                      >
                        Test
                      </Button>
                    </div>
                  </section>
                );
              })}
            </div>
          )}

          <div className="rounded-md border border-subtle bg-surface-raised p-4 text-xs leading-5 text-tertiary">
            <strong className="font-medium text-secondary">How actions run:</strong>{" "}
            the agent can either perform an action with information the visitor
            already provided, or ask the visitor to complete a form in chat. The
            backend validates every value against the fields above, stores the
            record in your workspace, and returns a visible confirmation.
          </div>
        </>
      )}

      {section === "leads" && <AgentLeadsPanel wsId={wsId} agentId={agentId} />}
      {section === "support" && <AgentSupportPanel wsId={wsId} agentId={agentId} />}

      <ActionConfigModal
        open={configEntry !== null}
        onClose={() => setConfigEntry(null)}
        wsId={wsId}
        agentId={agentId}
        entry={configEntry}
      />
      <ActionTestModal
        open={testEntry !== null}
        onClose={() => setTestEntry(null)}
        wsId={wsId}
        agentId={agentId}
        entry={testEntry}
      />
    </div>
  );
}
