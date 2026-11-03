"use client";

import Link from "next/link";
import { Plus } from "lucide-react";
import { AgentCard } from "./agent-card";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorPanel } from "@/components/common/error-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { toast } from "@/lib/toast";
import { workspaceHref } from "@/lib/routes";
import { useBilling } from "@/hooks/use-billing";
import { useAgents, useToggleAgentActive } from "@/hooks/use-agents";
import { useKnowledgeReadiness } from "@/hooks/use-knowledge-readiness";

const GATE_MESSAGE =
  "Add knowledge first — upload and train a document, or connect a website. An agent with no knowledge base cannot answer.";

export function AgentsPanel({ wsId }: { wsId: string }) {
  const agentsQuery = useAgents(wsId);
  const knowledge = useKnowledgeReadiness(wsId);
  const billingQuery = useBilling(wsId);
  const toggleActive = useToggleAgentActive(wsId);

  const gateMet = knowledge.hasReadyKnowledge;
  const knowledgeLoading = knowledge.isLoading;

  const agents = agentsQuery.data ?? [];

  const agentUsage = billingQuery.data?.usage.agents;
  const atAgentLimit = agentUsage?.limit !== null && agentUsage
    ? agentUsage.used >= agentUsage.limit
    : false;
  const canCreateAgent = gateMet && !atAgentLimit;

  const newAgentButton = (
    <Button
      asChild={canCreateAgent}
      variant="primary"
      disabled={!canCreateAgent || knowledgeLoading}
      iconLeft={<Plus aria-hidden className="h-4 w-4" />}
    >
      {canCreateAgent ? (
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
      {!gateMet && !knowledgeLoading && (
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

      {gateMet && atAgentLimit && agentUsage && (
        <AlertBanner
          tone="warning"
          title="Agent limit reached"
          action={
            <Button asChild variant="secondary" size="sm">
              <Link href={workspaceHref(wsId, "billing")}>
                View plan &amp; usage
              </Link>
            </Button>
          }
        >
          You have used {agentUsage.used} of {agentUsage.limit} agents on the{" "}
          {billingQuery.data?.plan.name ?? "current"} plan. Delete an agent or
          upgrade to add another.
        </AlertBanner>
      )}

      {agentsQuery.isLoading || knowledgeLoading ? (
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
            title="Add knowledge first"
            description="An agent with no knowledge base can't answer questions. Upload and train a document, or connect a website, then come back."
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