import { ConversationsPanel } from "@/components/agents/conversations-panel";
import { TabContent } from "@/components/common/tab-nav";

export default async function AgentConversationsPage({
  params,
}: {
  params: Promise<{ wsId: string; agentId: string }>;
}) {
  const { wsId, agentId } = await params;

  return (
    <TabContent tabKey="conversations">
      <ConversationsPanel wsId={wsId} agentId={agentId} />
    </TabContent>
  );
}