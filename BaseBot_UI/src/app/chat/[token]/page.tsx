import type { Metadata } from "next";
import { HostedChat } from "@/components/hosted/hosted-chat";

/**
 * Public, capability-token chat page. It intentionally sits outside the
 * authenticated (app) layout: visitors must never be sent to the dashboard
 * login, and the token must not be exposed to analytics or search engines.
 */
export const metadata: Metadata = {
  title: "Chat",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default async function HostedChatPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <HostedChat token={token} />;
}
