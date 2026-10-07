import { ChatPanel } from "@/components/chat/chat-panel";
import { TabContent } from "@/components/common/tab-nav";

export default async function AgentTestPage({
  params,
}: {
  params: Promise<{ wsId: string; agentId: string }>;
}) {
  const { wsId, agentId } = await params;

  return (
    <TabContent tabKey="test">
      <div className="max-w-3xl">
        <ChatPanel wsId={wsId} agentId={agentId} />
      </div>
    </TabContent>
  );
}