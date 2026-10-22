"use client";

import * as React from "react";
import { KeyRound, Plus, ShieldCheck, Terminal } from "lucide-react";
import { ApiKeyFormModal } from "./api-key-form-modal";
import { ApiKeyTable } from "./api-key-table";
import { OneTimeApiKeyModal } from "./one-time-api-key-modal";
import { ErrorPanel } from "@/components/common/error-panel";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { CopyButton } from "@/components/ui/copy-button";
import { EmptyState } from "@/components/ui/empty-state";
import { StatCard } from "@/components/ui/stat-card";
import { API_BASE_URL } from "@/lib/api-client";
import { formatNumber } from "@/lib/format";
import { toast } from "@/lib/toast";
import { useAgents } from "@/hooks/use-agents";
import {
  useApiKeys,
  useDeleteApiKey,
  useUpdateApiKey,
} from "@/hooks/use-api-keys";
import type { DeveloperApiKey, DeveloperApiKeyCreated } from "@/types/api";

type ConfirmAction =
  | { kind: "revoke"; key: DeveloperApiKey }
  | { kind: "delete"; key: DeveloperApiKey }
  | null;

const CHAT_CURL = `curl -X POST "${API_BASE_URL}/api/v1/chat" \\
  -H "X-API-Key: sk-botbase-..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "agent_id": "<agent-id>",
    "message": "What are your opening hours?",
    "conversation_id": null
  }'`;

/**
 * Workspace Developer tab. Keys are a server-to-server credential, so this
 * panel is explicit about never shipping them to a browser or mobile client.
 */
export function DeveloperPanel({ wsId }: { wsId: string }) {
  const keysQuery = useApiKeys(wsId);
  const agentsQuery = useAgents(wsId);
  const updateKey = useUpdateApiKey(wsId);
  const deleteKey = useDeleteApiKey(wsId);

  const [formOpen, setFormOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<DeveloperApiKey | null>(null);
  const [oneTime, setOneTime] = React.useState<DeveloperApiKeyCreated | null>(
    null,
  );
  const [confirm, setConfirm] = React.useState<ConfirmAction>(null);

  const keys = keysQuery.data ?? [];
  const agents = React.useMemo(() => agentsQuery.data ?? [], [agentsQuery.data]);
  const agentsById = React.useMemo(
    () => new Map(agents.map((agent) => [agent.id, agent])),
    [agents],
  );

  const activeCount = keys.filter((key) => Boolean(key.is_active)).length;
  const totalRequests = keys.reduce(
    (total, key) => total + (key.request_count ?? 0),
    0,
  );

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };

  const openEdit = (key: DeveloperApiKey) => {
    setEditing(key);
    setFormOpen(true);
  };

  const handleReactivate = (key: DeveloperApiKey) => {
    updateKey.mutate(
      { keyId: key.id, is_active: 1 },
      {
        onSuccess: () => toast.success({ title: "API key re-activated" }),
        onError: () => toast.error({ title: "Could not re-activate the key" }),
      },
    );
  };

  const confirmRevoke = async () => {
    if (!confirm || confirm.kind !== "revoke") return;
    try {
      await updateKey.mutateAsync({
        keyId: confirm.key.id,
        is_active: 0,
      });
      toast.success({
        title: "API key revoked",
        description: "Requests using this key will fail immediately.",
      });
      setConfirm(null);
    } catch {
      toast.error({ title: "Could not revoke the API key" });
    }
  };

  const confirmDelete = async () => {
    if (!confirm || confirm.kind !== "delete") return;
    try {
      await deleteKey.mutateAsync(confirm.key.id);
      toast.success({ title: "API key deleted" });
      setConfirm(null);
    } catch {
      toast.error({ title: "Could not delete the API key" });
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium text-primary">Developer API</h2>
          <p className="mt-1 max-w-2xl text-sm leading-5 text-secondary">
            Build your own integration with a long-lived key. Keys are scoped to
            this workspace and can be restricted to specific agents.
          </p>
        </div>
        <Button
          variant="primary"
          iconLeft={<Plus aria-hidden className="h-4 w-4" />}
          onClick={openCreate}
        >
          Create API key
        </Button>
      </div>

      <AlertBanner
        tone="info"
        icon={ShieldCheck}
        title="Server-to-server credential"
      >
        Never put an API key in browser JavaScript, a public mobile app, or a
        chat widget. Use a backend you control to call the API, and rotate the
        key immediately if it is exposed.
      </AlertBanner>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Active keys"
          value={formatNumber(activeCount)}
          icon={KeyRound}
          loading={keysQuery.isLoading}
          hint={`${keys.length} total`}
        />
        <StatCard
          label="API requests"
          value={formatNumber(totalRequests)}
          icon={Terminal}
          loading={keysQuery.isLoading}
          hint="Across every key in this workspace"
        />
        <StatCard
          label="Agents available"
          value={formatNumber(agents.length)}
          icon={ShieldCheck}
          loading={agentsQuery.isLoading}
          hint="Keys can be limited to a subset"
        />
      </div>

      <section aria-labelledby="api-keys-heading" className="flex flex-col gap-3">
        <div>
          <h3 id="api-keys-heading" className="text-base font-medium text-primary">
            API keys
          </h3>
          <p className="mt-0.5 text-xs text-tertiary">
            Only the prefix is stored in your dashboard. Full keys are shown once
            at creation.
          </p>
        </div>

        {keysQuery.isError ? (
          <ErrorPanel
            compact
            title="Could not load API keys"
            message="Check your connection and try again."
            onRetry={() => void keysQuery.refetch()}
          />
        ) : keys.length === 0 && !keysQuery.isLoading ? (
          <EmptyState
            icon={Terminal}
            title="No API keys yet"
            description="Create a key to call your agents from a backend service, mobile backend, CRM, or messaging bot."
            action={
              <Button
                variant="primary"
                iconLeft={<Plus aria-hidden className="h-4 w-4" />}
                onClick={openCreate}
              >
                Create your first key
              </Button>
            }
          />
        ) : (
          <ApiKeyTable
            keys={keys}
            agentsById={agentsById}
            loading={keysQuery.isLoading}
            onEdit={openEdit}
            onRevoke={(key) => setConfirm({ kind: "revoke", key })}
            onReactivate={handleReactivate}
            onDelete={(key) => setConfirm({ kind: "delete", key })}
          />
        )}
      </section>

      <section
        aria-labelledby="api-docs-heading"
        className="rounded-lg border border-subtle bg-surface p-5"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 id="api-docs-heading" className="text-base font-medium text-primary">
              Quick start
            </h3>
            <p className="mt-0.5 text-xs leading-5 text-tertiary">
              Create a key above, then call the chat endpoint from your server.
              The response includes the answer, citations, and a conversation ID
              for follow-up messages.
            </p>
          </div>
          <CopyButton value={CHAT_CURL} label="Copy example" />
        </div>

        <pre className="mt-3 overflow-x-auto rounded-md border border-subtle bg-inset p-3 font-mono text-xs leading-5 text-secondary">
          {CHAT_CURL}
        </pre>

        <div className="mt-4 grid gap-3 text-xs leading-5 text-tertiary sm:grid-cols-2">
          <div className="rounded-md border border-subtle bg-inset px-3 py-2.5">
            <p className="font-mono text-2xs text-accent-300">
              GET /api/v1/agents
            </p>
            <p className="mt-1">
              Lists the active agents this key may call.
            </p>
          </div>
          <div className="rounded-md border border-subtle bg-inset px-3 py-2.5">
            <p className="font-mono text-2xs text-accent-300">
              POST /api/v1/chat
            </p>
            <p className="mt-1">
              Send{" "}
              <code className="font-mono text-secondary">
                agent_id
              </code>
              ,{" "}
              <code className="font-mono text-secondary">message</code>, and an
              optional{" "}
              <code className="font-mono text-secondary">
                conversation_id
              </code>
              .
            </p>
          </div>
        </div>
        <p className="mt-3 text-2xs text-tertiary">
          Rate limit: 60 requests per minute per key. Errors use a stable{" "}
          <code className="font-mono">{`{"error": "..."}`}</code> body.
        </p>
      </section>

      <ApiKeyFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        wsId={wsId}
        editing={editing}
        onCreated={setOneTime}
      />

      <OneTimeApiKeyModal value={oneTime} onClose={() => setOneTime(null)} />

      <ConfirmationDialog
        open={confirm?.kind === "revoke"}
        onClose={() => setConfirm(null)}
        title="Revoke API key?"
        body={
          confirm?.kind === "revoke" ? (
            <p>
              Requests using{" "}
              <strong className="font-medium text-primary">
                {confirm.key.name}
              </strong>{" "}
              will fail immediately. You can re-activate the key later unless it
              has expired.
            </p>
          ) : null
        }
        confirmLabel="Revoke key"
        confirmLoading={updateKey.isPending}
        onConfirm={() => void confirmRevoke()}
      />

      <ConfirmationDialog
        open={confirm?.kind === "delete"}
        onClose={() => setConfirm(null)}
        title="Delete API key?"
        body={
          confirm?.kind === "delete" ? (
            <p>
              <strong className="font-medium text-primary">
                {confirm.key.name}
              </strong>{" "}
              will be permanently removed. Any integration using it will break,
              and this cannot be undone.
            </p>
          ) : null
        }
        confirmLabel="Delete key"
        confirmLoading={deleteKey.isPending}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
