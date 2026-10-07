"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Trash2 } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { TabNav } from "@/components/common/tab-nav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { ErrorPanel } from "@/components/common/error-panel";
import { NotFoundPanel } from "@/components/common/not-found-panel";
import { ActiveBadge, Toggle } from "@/components/ui/toggle";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import {
  agentHref,
  DEFAULT_AGENT_TAB,
  isAgentTab,
  workspaceHref,
  type AgentTab,
} from "@/lib/routes";
import { toast } from "@/lib/toast";
import { modelLabel } from "@/lib/reference-data";
import { useAgent, useDeleteAgent, useToggleAgentActive } from "@/hooks/use-agents";

const TABS: { id: AgentTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "test", label: "Test" },
  { id: "conversations", label: "Conversations" },
  { id: "embed", label: "Embed" },
];

/**
 * Agent header: name, active toggle with its consequence spelled out, and the
 * tab navigation. Tabs live in the URL (`?tab=`).
 */
export function AgentHeader({
  wsId,
  agentId,
}: {
  wsId: string;
  agentId: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab") ?? undefined;
  const active: AgentTab = isAgentTab(tabParam) ? tabParam : DEFAULT_AGENT_TAB;
  const agentQuery = useAgent(wsId, agentId);
  const toggleActive = useToggleAgentActive(wsId);
  const deleteAgent = useDeleteAgent(wsId);
  const [confirmOpen, setConfirmOpen] = React.useState(false);

  const agent = agentQuery.data;
  // Agent.is_active arrives as the integer 0 | 1 — normalise before rendering.
  const isActive = Boolean(agent?.is_active);

  if (agentQuery.isError) {
    const status = (agentQuery.error as { status?: number })?.status;
    if (status === 404) {
      return (
        <NotFoundPanel
          title="Agent not found"
          description="This agent no longer exists, or it belongs to another account."
          backHref={workspaceHref(wsId, "agents")}
          backLabel="Back to agents"
        />
      );
    }
    if (status === 403) {
      return (
        <NotFoundPanel
          title="You don't have access to this agent"
          description="The workspace this agent belongs to is not owned by your account."
          backHref={workspaceHref(wsId, "agents")}
          backLabel="Back to agents"
        />
      );
    }
    return (
      <ErrorPanel
        title="We could not load this agent"
        statusCode={status}
        onRetry={() => void agentQuery.refetch()}
      />
    );
  }

  const confirmDelete = async () => {
    if (!agent) return;
    try {
      await deleteAgent.mutateAsync(agent.id);
      toast.success({ title: "Agent deleted" });
      router.replace(workspaceHref(wsId, "agents"));
    } catch {
      toast.error({ title: "Could not delete the agent" });
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={agent?.name ?? "Agent"}
        description={agent?.description ?? "Configure, test and deploy this agent."}
        meta={
          agent ? (
            <>
              <ActiveBadge active={isActive} />
              <Badge tone="neutral">{agent.language}</Badge>
              <Badge tone="neutral" title={agent.model}>
                {modelLabel(agent.model)}
              </Badge>
            </>
          ) : undefined
        }
        actions={
          agent ? (
            <>
              <Button asChild variant="secondary" size="sm">
                <Link href={workspaceHref(wsId, "agents")}>All agents</Link>
              </Button>
              <Tooltip content="Permanently deletes this agent, its conversations and its embed tokens.">
                <Button
                  variant="dangerGhost"
                  size="sm"
                  iconLeft={<Trash2 aria-hidden className="h-4 w-4" />}
                  onClick={() => setConfirmOpen(true)}
                >
                  Delete agent
                </Button>
              </Tooltip>
            </>
          ) : undefined
        }
      >
        {agent ? (
          <div className="flex flex-wrap items-center gap-3">
            <Toggle
              checked={isActive}
              onCheckedChange={(next) =>
                toggleActive.mutate(
                  { agentId, isActive: next },
                  {
                    onError: () =>
                      toast.error({
                        title: next
                          ? "Could not activate the agent"
                          : "Could not deactivate the agent",
                      }),
                  },
                )
              }
              loading={toggleActive.isPending}
              label={isActive ? "Agent is active" : "Agent is inactive"}
            />
            <p className="text-xs text-tertiary">
              Turning this off makes the live widget stop responding immediately.
            </p>
          </div>
        ) : (
          <Skeleton width={280} height={20} />
        )}

        <TabNav
          active={active}
          ariaLabel="Agent sections"
          className="mt-2"
          tabs={TABS.map((tab) => ({
            id: tab.id,
            label: tab.label,
            href: agentHref(wsId, agentId, tab.id),
          }))}
        />
      </PageHeader>

      <ConfirmationDialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Delete agent?"
        body={
          <p>
            This permanently deletes{" "}
            <strong className="font-medium text-primary">{agent?.name}</strong>,
            all of its conversations, and all of its embed tokens. Any website
            still using those tokens will stop working immediately. This cannot
            be undone.
          </p>
        }
        confirmLabel="Delete agent"
        confirmLoading={deleteAgent.isPending}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}