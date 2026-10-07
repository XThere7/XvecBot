"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { KeyRound, Plus } from "lucide-react";
import { OneTimeTokenModal, type OneTimeToken } from "./one-time-token-modal";
import { SnippetChecklist } from "./snippet-checklist";
import { TokenFormModal } from "./token-form-modal";
import { TokenTable } from "./token-table";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { CodeSnippet } from "@/components/ui/code-snippet";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorPanel } from "@/components/common/error-panel";
import { NotFoundPanel } from "@/components/common/not-found-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/ui/stat-card";
import { Tooltip } from "@/components/ui/tooltip";
import { apiGet } from "@/lib/api-client";
import { formatNumber } from "@/lib/format";
import { toast } from "@/lib/toast";
import { useAgent } from "@/hooks/use-agents";
import {
  isSnippetMissing,
  useDeleteToken,
  useEmbedSnippet,
  useEmbedTokens,
  useToggleToken,
  useUpdateToken,
} from "@/hooks/use-embed-tokens";
import type { EmbedSnippet, EmbedToken } from "@/types/api";

export function EmbedPanel(props: { wsId: string; agentId: string }) {
  return (
    <React.Suspense fallback={<Skeleton variant="card" height={180} />}>
      <EmbedPanelInner {...props} />
    </React.Suspense>
  );
}

function EmbedPanelInner({
  wsId,
  agentId,
}: {
  wsId: string;
  agentId: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const snippetParam = searchParams.get("snippet");

  const agentQuery = useAgent(wsId, agentId);
  const tokensQuery = useEmbedTokens(wsId, agentId);
  const toggleToken = useToggleToken(wsId, agentId);
  const deleteToken = useDeleteToken(wsId, agentId);
  const updateToken = useUpdateToken(wsId, agentId);

  const snippetQuery = useEmbedSnippet(wsId, agentId, snippetParam, Boolean(snippetParam));

  const [formOpen, setFormOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<EmbedToken | null>(null);
  const [oneTime, setOneTime] = React.useState<OneTimeToken | null>(null);
  const [confirm, setConfirm] = React.useState<
    | { kind: "delete"; token: EmbedToken }
    | { kind: "revoke"; token: EmbedToken }
    | null
  >(null);

  const agent = agentQuery.data;
  // Agent.is_active is the integer 0 | 1.
  const agentActive = Boolean(agent?.is_active);

  const tokens = tokensQuery.data ?? [];
  const totalRequests = tokens.reduce((sum, token) => sum + (token.request_count ?? 0), 0);

  const closeOneTime = () => {
    // Null the credential as soon as the modal is dismissed.
    setOneTime(null);
  };

  const handleCreated = async (token: EmbedToken) => {
    // 201 is the only moment the full token exists in the browser. The snippet
    // is fetched immediately so both halves are on screen at once.
    let snippet = "";
    try {
      const response = await apiGet<EmbedSnippet>(
        `/workspaces/${wsId}/agents/${agentId}/tokens/${token.id}/snippet`,
      );
      snippet = response.snippet;
    } catch {
      snippet = "";
    }
    setOneTime({ token: token.token, label: token.label, snippet });
  };

  const handleRevoke = async (token: EmbedToken) => {
    setConfirm({ kind: "revoke", token });
  };

  const confirmRevoke = async () => {
    if (!confirm || confirm.kind !== "revoke") return;
    try {
      await updateToken.mutateAsync({ tokenId: confirm.token.id, is_active: false });
      toast.success({
        title: "Token revoked",
        description: "The widget will stop responding immediately.",
      });
      setConfirm(null);
    } catch {
      toast.error({ title: "Could not revoke the token" });
    }
  };

  const confirmDelete = async () => {
    if (!confirm || confirm.kind !== "delete") return;
    try {
      await deleteToken.mutateAsync(confirm.token.id);
      toast.success({ title: "Embed token deleted" });
      setConfirm(null);
    } catch {
      toast.error({ title: "Could not delete the token" });
    }
  };

  const createButton = (
    <Button
      variant="primary"
      disabled={!agentActive}
      iconLeft={<Plus aria-hidden className="h-4 w-4" />}
      onClick={() => {
        setEditing(null);
        setFormOpen(true);
      }}
    >
      Create embed token
    </Button>
  );

  const clearSnippetParam = () => {
    const params = new URLSearchParams(searchParams.toString());
    params.delete("snippet");
    router.replace(`?${params.toString()}`);
  };

  if (tokensQuery.isError) {
    return (
      <ErrorPanel
        title="We could not load embed tokens"
        statusCode={(tokensQuery.error as { status?: number })?.status}
        onRetry={() => void tokensQuery.refetch()}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="grid gap-4 sm:grid-cols-2">
          <StatCard label="Widget requests" value={formatNumber(totalRequests)} hint="Every widget call, including the info fetch" />
          <StatCard label="Tokens" value={tokens.length} />
        </div>
        {agentActive ? (
          createButton
        ) : (
          <Tooltip content="Activate the agent before creating a token">
            {createButton}
          </Tooltip>
        )}
      </div>

      {!agentActive && agent && (
        <AlertBanner tone="warning" title="This agent is inactive">
          A live widget for an inactive agent returns 403. Activate the agent
          before creating or testing a token.
        </AlertBanner>
      )}

      {snippetParam && (
        <section className="rounded-md border border-subtle bg-surface p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg text-primary">Embed snippet</h2>
            <Button variant="ghost" size="sm" onClick={clearSnippetParam}>
              Close
            </Button>
          </div>

          {snippetQuery.isLoading ? (
            <div className="mt-4">
              <Skeleton variant="code" />
            </div>
          ) : snippetQuery.isError ? (
            isSnippetMissing(snippetQuery.error) ? (
              <div className="mt-4">
                <NotFoundPanel
                  title="Token not found"
                  description="This token no longer exists."
                  backHref={`/workspaces/${wsId}/agents/${agentId}?tab=embed`}
                  backLabel="Back to tokens"
                />
              </div>
            ) : (
              <div className="mt-4">
                <ErrorPanel
                  compact
                  title="Could not load the snippet"
                  onRetry={() => void snippetQuery.refetch()}
                />
              </div>
            )
          ) : snippetQuery.data ? (
            <div className="mt-4 flex flex-col gap-4">
              <CodeSnippet
                code={snippetQuery.data.snippet}
                context={
                  <>
                    <span>Paste before &lt;/body&gt;</span>
                    <span>Works on any website — no build step</span>
                  </>
                }
              />
              <div className="rounded-lg border border-subtle bg-inset px-3 py-2.5">
                <p className="text-2xs text-tertiary">Full token</p>
                <code className="mt-1 block overflow-x-auto font-mono text-xs text-primary">
                  {snippetQuery.data.token}
                </code>
              </div>
              <SnippetChecklist resetKey={snippetQuery.data.token} />
            </div>
          ) : null}
        </section>
      )}

      {tokens.length === 0 && !tokensQuery.isLoading ? (
        <EmptyState
          icon={KeyRound}
          title="No embed tokens yet"
          description="An embed token is the key that lets your website talk to this agent. Create one to get your embed code."
          action={
            agentActive ? (
              <Button
                variant="primary"
                iconLeft={<Plus aria-hidden className="h-4 w-4" />}
                onClick={() => {
                  setEditing(null);
                  setFormOpen(true);
                }}
              >
                Create embed token
              </Button>
            ) : (
              <Tooltip content="Activate the agent before creating a token">
                {createButton}
              </Tooltip>
            )
          }
        />
      ) : (
        <TokenTable
          tokens={tokens}
          loading={tokensQuery.isLoading}
          onEdit={(token) => {
            setEditing(token);
            setFormOpen(true);
          }}
          onDelete={(token) => setConfirm({ kind: "delete", token })}
          onRevoke={handleRevoke}
          onReactivate={(token) =>
            toggleToken.mutate(
              { tokenId: token.id, isActive: true },
              {
                onSuccess: () => toast.success({ title: "Token re-activated" }),
                onError: () => toast.error({ title: "Could not re-activate the token" }),
              },
            )
          }
          onCopySnippet={(token) => {
            const params = new URLSearchParams(searchParams.toString());
            params.set("tab", "embed");
            params.set("snippet", token.id);
            router.replace(`?${params.toString()}`);
          }}
        />
      )}

      <TokenFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        wsId={wsId}
        agentId={agentId}
        editing={editing}
        onCreated={(token) => void handleCreated(token)}
      />

      <OneTimeTokenModal value={oneTime} onClose={closeOneTime} />

      <ConfirmationDialog
        open={confirm?.kind === "delete"}
        onClose={() => setConfirm(null)}
        title="Delete embed token?"
        body={
          confirm?.kind === "delete" ? (
            <p>
              The widget on{" "}
              <strong className="font-medium text-primary">{confirm.token.label}</strong>{" "}
              will stop working immediately. If you only want to pause it,
              revoke it instead — that can be undone.
            </p>
          ) : null
        }
        confirmLabel="Delete token"
        confirmLoading={deleteToken.isPending}
        onConfirm={() => void confirmDelete()}
      />

      <ConfirmationDialog
        open={confirm?.kind === "revoke"}
        onClose={() => setConfirm(null)}
        title="Revoke embed token?"
        body={
          confirm?.kind === "revoke" ? (
            <p>
              The widget on{" "}
              <strong className="font-medium text-primary">{confirm.token.label}</strong>{" "}
              will stop responding immediately, for every visitor. You can
              re-activate it later.
            </p>
          ) : null
        }
        confirmLabel="Revoke token"
        confirmLoading={updateToken.isPending}
        onConfirm={() => void confirmRevoke()}
      />
    </div>
  );
}