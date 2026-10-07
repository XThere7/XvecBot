"use client";

import Link from "next/link";
import { Plus } from "lucide-react";
import { AgentCard } from "./agent-card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorPanel } from "@/components/common/error-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { toast } from "@/lib/toast";
import { workspaceHref } from "@/lib/routes";
import { useAgents, useToggleAgentActive } from "@/hooks/use-agents";
import { useDocuments } from "@/hooks/use-documents";

const GATE_MESSAGE =
  "Train at least one document first — an agent with no knowledge base cannot answer.";

export function AgentsPanel({ wsId }: { wsId: string }) {
  const agentsQuery = useAgents(wsId);
  const documentsQuery = useDocuments(wsId);
  const toggleActive = useToggleAgentActive(wsId);

  const readyCount = (documentsQuery.data ?? []).filter(
    (doc) => doc.status === "ready",
  ).length;
  const gateMet = readyCount > 0;
  const documentsLoading = documentsQuery.isLoading;

  const agents = agentsQuery.data ?? [];

  const newAgentButton = (
    <Button
      asChild={gateMet}
      variant="primary"
      disabled={!gateMet || documentsLoading}
      iconLeft={<Plus aria-hidden className="h-4 w-4" />}
    >
      {gateMet ? (
        <Link href={`/workspaces/${wsId}/agents/new`}>New agent</Link>
      ) : (
        <span>New agent</span>
      )}
    </Button>
  );

  if (agentsQuery.isError) {
    return (
      <ErrorPanel
        title="We could not load your agents"
        statusCode={(agentsQuery.error as { status?: number })?.status}
        onRetry={() => void agentsQuery.refetch()}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {!gateMet && !documentsLoading && (
        <div className="flex flex-col gap-3 rounded-md border border-subtle bg-surface px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-secondary">{GATE_MESSAGE}</p>
          <div className="flex shrink-0 items-center gap-2">
            <Tooltip content={GATE_MESSAGE}>{newAgentButton}</Tooltip>
            <Button asChild variant="secondary">
              <Link href={workspaceHref(wsId, "documents")}>Go to Documents</Link>
            </Button>
          </div>
        </div>
      )}

      {agentsQuery.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} variant="card" />
          ))}
        </div>
      ) : agents.length === 0 ? (
        gateMet ? (
          <EmptyState
            title="No agents yet"
            description="An agent is your AI assistant — a name, a personality and the knowledge it answers from."
            action={
              <Button
                asChild
                variant="primary"
                iconLeft={<Plus aria-hidden className="h-4 w-4" />}
              >
                <Link href={`/workspaces/${wsId}/agents/new`}>New agent</Link>
              </Button>
            }
          />
        ) : (
          <EmptyState
            title="Train a document first"
            description="An agent with no knowledge base can't answer questions. Train at least one document, then come back."
            action={
              <Button asChild variant="primary">
                <Link href={workspaceHref(wsId, "documents")}>Go to Documents</Link>
              </Button>
            }
          />
        )
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {agents.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              wsId={wsId}
              onToggleActive={(next) =>
                toggleActive.mutate({ agentId: agent.id, isActive: next }, {
                  onError: () =>
                    toast.error({
                      title: next
                        ? "Could not activate the agent"
                        : "Could not deactivate the agent",
                    }),
                })
              }
              toggling={
                toggleActive.isPending && toggleActive.variables?.agentId === agent.id
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}