import type { Metadata } from "next";
import { LandingHeader } from "@/components/landing/landing-header";
import { Hero } from "@/components/landing/hero";
import { LogoMarquee } from "@/components/landing/logo-marquee";
import { HowItWorks } from "@/components/landing/how-it-works";
import { LandingFooter } from "@/components/landing/landing-footer";

export const metadata: Metadata = {
  title: "BotBase — Turn your documents into an AI chat widget",
  description:
    "BotBase turns your catalogue, price list or handbook into an AI assistant that answers from your own content. Paste one script tag and go live.",
};

/**
 * Phase 1 — the public BotBase landing page. It lives outside the (app) and
 * (auth) groups, so it never gets the sidebar, the top bar or the auth guard.
 * Every primary link points at the matching dashboard route, which bounces to
 * /login when there is no session.
 */
export default function LandingPage() {
  return (
    <div className="min-h-dvh bg-canvas text-primary">
      <LandingHeader />
      <main>
        <Hero />
        <LogoMarquee />
        <HowItWorks />
      </main>
      <LandingFooter />
    </div>
  );
}
