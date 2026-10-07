import { ConversationThreadView } from "@/components/agents/conversation-thread-view";

export default async function ConversationThreadPage({
  params,
}: {
  params: Promise<{ wsId: string; agentId: string; convId: string }>;
}) {
  const { wsId, agentId, convId } = await params;

  return (
    <ConversationThreadView wsId={wsId} agentId={agentId} convId={convId} />
  );
}