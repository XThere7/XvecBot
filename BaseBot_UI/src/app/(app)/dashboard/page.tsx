"use client";

import * as React from "react";
import Link from "next/link";
import { useQueries } from "@tanstack/react-query";
import { FileStack, MessageSquare, Plus, Radio } from "lucide-react";
import { ActivityFeed, type ActivityItem } from "@/components/common/activity-feed";
import { OnboardingChecklist } from "@/components/common/onboarding-checklist";
import { PageHeader } from "@/components/common/page-header";
import { AgentCard } from "@/components/agents/agent-card";
import { WorkspaceCard, WorkspaceCardSkeleton } from "@/components/common/workspace-card";
import { Button } from "@/components/ui/button";
import { ErrorPanel } from "@/components/common/error-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/ui/stat-card";
import { apiGet } from "@/lib/api-client";
import { agentHref, workspaceHref } from "@/lib/routes";
import { useWorkspaces } from "@/hooks/use-workspaces";
import type { Agent, EmbedToken, WorkspaceDocument } from "@/types/api";

export default function DashboardPage() {
  const workspacesQuery = useWorkspaces();
  const workspaces = React.useMemo(
    () => workspacesQuery.data ?? [],
    [workspacesQuery.data],
  );

  // N+1 by design — the API has no summary endpoint and the expected account
  // size is ≤ 10 workspaces.
  const results = useQueries({
    queries: workspaces.flatMap((workspace) => [
      {
        queryKey: ["workspaces", "detail", workspace.id, "documents"],
        queryFn: () =>
          apiGet<WorkspaceDocument[]>(`/workspaces/${workspace.id}/documents`),
      },
      {
        queryKey: ["workspaces", "detail", workspace.id, "agents"],
        queryFn: () => apiGet<Agent[]>(`/workspaces/${workspace.id}/agents`),
      },
    ]),
  });

  const agentQueries = useQueries({
    queries: workspaces.flatMap((workspace, workspaceIndex) => {
      const agents = (results[workspaceIndex * 2 + 1]?.data as Agent[] | undefined) ?? [];
      return agents.map((agent) => ({
        queryKey: ["workspaces", "detail", workspace.id, "agents", "detail", agent.id, "tokens"],
        queryFn: () =>
          apiGet<EmbedToken[]>(`/workspaces/${workspace.id}/agents/${agent.id}/tokens`),
      }));
    }),
  });

  const allAgents = React.useMemo(
    () =>
      workspaces.flatMap((workspace, index) => {
        const agents = (results[index * 2 + 1]?.data as Agent[] | undefined) ?? [];
        return agents.map((agent) => ({ workspace, agent }));
      }),
    [workspaces, results],
  );

  const allDocuments = React.useMemo(
    () =>
      workspaces.flatMap((workspace, index) => {
        const docs = (results[index * 2]?.data as WorkspaceDocument[] | undefined) ?? [];
        return docs.map((doc) => ({ workspace, doc }));
      }),
    [workspaces, results],
  );

  const tokenData = agentQueries.map((query) => query.data as EmbedToken[] | undefined);
  const tokensLoaded = tokenData.length > 0 && tokenData.every(Boolean);
  const widgetRequests = tokensLoaded
    ? tokenData.reduce<number>(
        (sum, tokens) =>
          sum + (tokens ?? []).reduce((acc, token) => acc + (token.request_count ?? 0), 0),
        0,
      )
    : null;

  const readyDocuments = allDocuments.filter((entry) => entry.doc.status === "ready");
  const activeAgents = allAgents.filter((entry) => Boolean(entry.agent.is_active));

  const firstWorkspace = workspaces[0];
  const hasReadyDocument = readyDocuments.length > 0;
  const hasAgent = allAgents.length > 0;

  const onboardingSteps = [
    {
      id: "workspace",
      title: "Create a workspace",
      description: "A workspace holds your documents and the agents built from them.",
      complete: Boolean(firstWorkspace),
      href: firstWorkspace ? workspaceHref(firstWorkspace.id, "documents") : "/workspaces/new",
      cta: firstWorkspace ? "Open workspace" : "Create workspace",
    },
    {
      id: "document",
      title: "Upload a document",
      description: "PDF, TXT or DOCX. We train it automatically after the upload.",
      complete: hasReadyDocument,
      href: firstWorkspace ? workspaceHref(firstWorkspace.id, "documents") : undefined,
      cta: "Upload document",
      lockedReason: firstWorkspace
        ? undefined
        : "Create a workspace first — documents live inside a workspace.",
    },
    {
      id: "agent",
      title: "Create your first agent",
      description: "An agent is your AI assistant — a name, a personality, your knowledge.",
      complete: hasAgent,
      href:
        firstWorkspace && hasReadyDocument
          ? `/workspaces/${firstWorkspace.id}/agents/new`
          : undefined,
      cta: "New agent",
      lockedReason: hasReadyDocument
        ? undefined
        : "Train at least one document first — an agent with no knowledge base cannot answer.",
    },
  ];

  const activity: ActivityItem[] = React.useMemo(
    () =>
      [
        ...allDocuments.map(({ workspace, doc }) => ({
          id: `doc-${doc.id}`,
          kind: "document" as const,
          title: `Uploaded ${doc.filename}`,
          meta: `${workspace.name} · ${doc.status}`,
          createdAt: doc.created_at,
          href: workspaceHref(workspace.id, "documents"),
        })),
        ...allAgents.map(({ workspace, agent }) => ({
          id: `agent-${agent.id}`,
          kind: "agent" as const,
          title: `Created agent ${agent.name}`,
          meta: `${workspace.name} · ${agent.language}`,
          createdAt: agent.created_at,
          href: agentHref(workspace.id, agent.id, "overview"),
        })),
      ]
        .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))
        .slice(0, 8),
    [allDocuments, allAgents],
  );

  if (workspacesQuery.isError) {
    return (
      <ErrorPanel
        title="We could not load your workspaces"
        statusCode={(workspacesQuery.error as { status?: number })?.status}
        onRetry={() => void workspacesQuery.refetch()}
      />
    );
  }

  const showOnboarding = workspacesQuery.isSuccess && workspaces.length === 0;

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Dashboard"
        description="What your bot is doing right now, and the next action."
        actions={
          <Button asChild variant="primary" iconLeft={<Plus aria-hidden className="h-4 w-4" />}>
            <Link href="/workspaces/new">New workspace</Link>
          </Button>
        }
      />

      {workspacesQuery.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <StatCard key={i} label="—" value="" loading />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Workspaces" value={workspaces.length} icon={FileStack} />
          <StatCard
            label="Agents (active)"
            value={`${activeAgents.length} / ${allAgents.length}`}
            icon={MessageSquare}
          />
          <StatCard
            label="Ready documents"
            value={readyDocuments.length}
            icon={FileStack}
          />
          <StatCard
            label="Widget requests"
            value={widgetRequests ?? "—"}
            hint={
              widgetRequests === null
                ? "Could not load token counters"
                : "Every widget call, including the info fetch"
            }
            icon={Radio}
          />
        </div>
      )}

      {showOnboarding && (
        <OnboardingChecklist steps={onboardingSteps} />
      )}

      {!showOnboarding && workspaces.length > 0 && (
        <>
          <section className="flex flex-col gap-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-xl text-primary">Workspaces</h2>
              <Button asChild variant="ghost" size="sm">
                <Link href="/workspaces">View all</Link>
              </Button>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {workspacesQuery.isLoading
                ? Array.from({ length: 3 }).map((_, i) => (
                    <WorkspaceCardSkeleton key={i} />
                  ))
                : workspaces.slice(0, 3).map((workspace, index) => (
                    <WorkspaceCard
                      key={workspace.id}
                      workspace={workspace}
                      stats={{
                        agents: ((results[index * 2 + 1]?.data as Agent[] | undefined) ?? [])
                          .length,
                        readyDocuments: (
                          (results[index * 2]?.data as WorkspaceDocument[] | undefined) ?? []
                        ).filter((doc) => doc.status === "ready").length,
                      }}
                    />
                  ))}
            </div>
          </section>

          <section className="flex flex-col gap-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-xl text-primary">Recent agents</h2>
              {firstWorkspace && (
                <Button asChild variant="ghost" size="sm">
                  <Link href={workspaceHref(firstWorkspace.id, "agents")}>View all</Link>
                </Button>
              )}
            </div>

            {allAgents.length === 0 ? (
              <div className="rounded-md border border-subtle bg-surface px-6 py-8">
                <p className="text-base text-primary">No agents yet</p>
                <p className="mt-1.5 text-sm text-secondary">
                  {hasReadyDocument
                    ? "An agent is your AI assistant — a name, a personality and the knowledge it answers from."
                    : "Train at least one document before creating an agent — an agent with no knowledge base cannot answer."}
                </p>
                {hasReadyDocument && firstWorkspace && (
                  <Button
                    asChild
                    variant="primary"
                    size="sm"
                    className="mt-4"
                    iconLeft={<Plus aria-hidden className="h-4 w-4" />}
                  >
                    <Link href={`/workspaces/${firstWorkspace.id}/agents/new`}>
                      New agent
                    </Link>
                  </Button>
                )}
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {allAgents.slice(0, 5).map(({ workspace, agent }) => (
                  <AgentCard key={agent.id} agent={agent} wsId={workspace.id} />
                ))}
              </div>
            )}
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-md border border-subtle bg-surface p-5">
              <h2 className="text-lg text-primary">Recent activity</h2>
              {workspacesQuery.isLoading ? (
                <div className="mt-4">
                  <Skeleton rows={4} height={16} />
                </div>
              ) : (
                <ActivityFeed items={activity} className="mt-3" />
              )}
            </div>

            <div className="rounded-md border border-subtle bg-surface p-5">
              <h2 className="text-lg text-primary">Next steps</h2>
              <ol className="mt-3 flex flex-col gap-3">
                {!hasReadyDocument && (
                  <li className="flex items-start gap-3 text-sm text-secondary">
                    <FileStack aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-tertiary" />
                    <span>
                      Upload a document to{" "}
                      <Link
                        href={workspaceHref(firstWorkspace.id, "documents")}
                        className="text-accent-300 hover:underline"
                      >
                        {firstWorkspace.name}
                      </Link>{" "}
                      so your agents have something to answer from.
                    </span>
                  </li>
                )}
                {hasReadyDocument && !hasAgent && (
                  <li className="flex items-start gap-3 text-sm text-secondary">
                    <MessageSquare aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-tertiary" />
                    <span>
                      Create an agent —{" "}
                      <Link
                        href={`/workspaces/${firstWorkspace.id}/agents/new`}
                        className="text-accent-300 hover:underline"
                      >
                        new agent
                      </Link>
                      .
                    </span>
                  </li>
                )}
                {hasAgent && (
                  <li className="flex items-start gap-3 text-sm text-secondary">
                    <Radio aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-tertiary" />
                    <span>
                      Generate an embed token to put this agent on your website.
                    </span>
                  </li>
                )}
              </ol>
            </div>
          </section>
        </>
      )}
    </div>
  );
}