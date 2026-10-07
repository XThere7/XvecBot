import { AgentOverview } from "@/components/agents/agent-overview";
import { ChatPanel } from "@/components/chat/chat-panel";
import { ConversationsPanel } from "@/components/agents/conversations-panel";
import { EmbedPanel } from "@/components/embed/embed-panel";
import { TabContent } from "@/components/common/tab-nav";

/**
 * `/workspaces/[wsId]/agents/[agentId]` renders the tab selected by `?tab=`.
 * `/test`, `/conversations` and `/embed` are the deep-link forms of the same
 * tabs and render the same panels.
 */
export default async function AgentPage({
  params,
  searchParams,
}: {
  params: Promise<{ wsId: string; agentId: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { wsId, agentId } = await params;
  const query = await searchParams;
  const tab = typeof query.tab === "string" ? query.tab : "overview";

  return (
    <TabContent tabKey={tab}>
      {tab === "test" ? (
        <div className="max-w-3xl">
          <ChatPanel wsId={wsId} agentId={agentId} />
        </div>
      ) : tab === "conversations" ? (
        <ConversationsPanel wsId={wsId} agentId={agentId} />
      ) : tab === "embed" ? (
        <EmbedPanel wsId={wsId} agentId={agentId} />
      ) : (
        <AgentOverview wsId={wsId} agentId={agentId} />
      )}
    </TabContent>
  );
}
