import type { Metadata } from "next";
import { PricingPage } from "@/components/billing/pricing-page";

export const metadata: Metadata = {
  title: "Pricing — BotBase",
  description:
    "Free, Standard and Pro plans for BotBase. Start with a 21-day Pro trial, then keep one AI agent, 100 chat messages and 100 MB of knowledge storage on Free.",
};

export default function Page() {
  return <PricingPage />;
}
