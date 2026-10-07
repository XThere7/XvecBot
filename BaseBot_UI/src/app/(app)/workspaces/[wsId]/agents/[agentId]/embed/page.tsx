import { EmbedPanel } from "@/components/embed/embed-panel";
import { TabContent } from "@/components/common/tab-nav";

export default async function AgentEmbedPage({
  params,
}: {
  params: Promise<{ wsId: string; agentId: string }>;
}) {
  const { wsId, agentId } = await params;

  return (
    <TabContent tabKey="embed">
      <EmbedPanel wsId={wsId} agentId={agentId} />
    </TabContent>
  );
}