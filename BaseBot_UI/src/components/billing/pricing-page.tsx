"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, ShieldCheck, Sparkles } from "lucide-react";
import { LandingFooter } from "@/components/landing/landing-footer";
import { LandingHeader } from "@/components/landing/landing-header";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { ErrorPanel } from "@/components/common/error-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { PLAN_BLURB, PLAN_CTA, planHighlights } from "@/lib/plan-copy";
import { usePlans } from "@/hooks/use-billing";
import { PlanCard } from "./plan-card";
import { PaymentsComingSoonDialog } from "./payments-coming-soon-dialog";

const FAQ = [
  {
    question: "Do I need a card to start?",
    answer:
      "No. Every new account includes a 21-day Pro trial with full access. After the trial the account moves to Free automatically. There is no card on file and no automatic charge.",
  },
  {
    question: "What happens when I reach a limit?",
    answer:
      "The affected action pauses at the limit. Your workspace, documents, agents and conversation history stay accessible, and the monthly chat-message allowance resets on the first of the next month (UTC).",
  },
  {
    question: "Can I upgrade later?",
    answer:
      "Yes. Standard is TZS 7,800 per month and Pro is TZS 15,800 per month. Upgrades will open here once payments go live; your existing documents, agents and conversations stay exactly as they are.",
  },
  {
    question: "Do unused chat messages roll over?",
    answer:
      "No. The chat-message allowance is per account, per calendar month, and resets at the start of the next month. It does not accumulate.",
  },
];

export function PricingPage() {
  const plansQuery = usePlans();
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const plans = plansQuery.data?.plans ?? [];

  return (
    <div className="min-h-dvh bg-canvas text-primary">
      <LandingHeader />

      <main className="pt-16">
        <section className="mx-auto w-full max-w-[1200px] px-4 pb-10 pt-14 sm:px-6 sm:pt-20">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-subtle bg-surface px-3 py-1 text-2xs font-medium uppercase tracking-wide text-secondary">
              <Sparkles aria-hidden className="h-3.5 w-3.5 text-accent-300" />
              Pricing
            </div>
            <h1 className="mt-5 text-3xl tracking-tight text-primary sm:text-4xl">
              Simple pricing, in Tanzanian shillings.
            </h1>
            <p className="mt-4 text-base leading-7 text-secondary">
              Try every Pro feature free for 21 days. After the trial, keep
              what you need on Free or move to Standard or Pro when payments
              go live. No surprise charges, ever.
            </p>
          </div>

          <div className="mt-8">
            <AlertBanner
              tone="info"
              title={`21-day free trial with full Pro access${
                plansQuery.data?.trial
                  ? ` — ${plansQuery.data.trial.duration_days} days`
                  : ""
              }`}
            >
              No card required. Your account stays on Free after the trial
              unless you choose a paid plan. Standard and Pro are listed with
              their final TZS prices and limits so you can plan ahead.
            </AlertBanner>
          </div>
        </section>

        <section
          aria-label="Plans"
          className="mx-auto w-full max-w-[1200px] px-4 pb-14 sm:px-6"
        >
          {plansQuery.isLoading ? (
            <div className="grid gap-4 lg:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} variant="card" height={520} />
              ))}
            </div>
          ) : plansQuery.isError ? (
            <ErrorPanel
              title="We could not load the plans"
              message="Check your connection and try again."
              onRetry={() => void plansQuery.refetch()}
            />
          ) : (
            <div className="grid gap-4 lg:grid-cols-3">
              {plans.map((plan) => (
                <PlanCard
                  key={plan.id}
                  plan={plan}
                  blurb={PLAN_BLURB[plan.id]}
                  highlights={planHighlights(plan)}
                  action={
                    plan.id === "free" ? (
                      <Button
                        asChild
                        fullWidth
                        variant="secondary"
                        iconRight={<ArrowRight aria-hidden className="h-4 w-4" />}
                      >
                        <Link href="/register">Start free</Link>
                      </Button>
                    ) : (
                      <Button
                        fullWidth
                        variant={plan.recommended ? "primary" : "secondary"}
                        onClick={() => setDialogOpen(true)}
                      >
                        {PLAN_CTA[plan.id]}
                      </Button>
                    )
                  }
                />
              ))}
            </div>
          )}

          <p className="mt-4 text-center text-2xs text-tertiary">
            All prices are in TZS. Paid plans are billed monthly once payments
            are enabled. Features marked{" "}
            <span className="text-warning-400">Soon</span> are not available
            yet and are included in the plan as they ship.
          </p>
        </section>

        <section className="border-y border-subtle bg-surface">
          <div className="mx-auto grid w-full max-w-[1200px] gap-8 px-4 py-14 sm:px-6 lg:grid-cols-[0.9fr_1.1fr]">
            <div>
              <p className="text-2xs font-medium uppercase tracking-wide text-tertiary">
                Fair limits, clearly shown
              </p>
              <h2 className="mt-2 text-2xl tracking-tight text-primary">
                Your workspace stays yours at every limit.
              </h2>
              <p className="mt-3 max-w-md text-sm leading-6 text-secondary">
                BotBase never silently charges you for going over a limit.
                When an allowance is used up, the affected action pauses and
                the dashboard tells you exactly why, when it resets, and what
                to do next.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              {[
                {
                  title: "Usage is visible",
                  body: "Every workspace shows agents, documents, pages, websites, chat messages and storage against its plan in real time.",
                },
                {
                  title: "The reset date",
                  body: "Chat-message allowances reset on the first of each month (UTC). Your documents and history stay put.",
                },
                {
                  title: "No surprise charges",
                  body: "At a limit, the affected action simply waits. There is no automatic overage billing.",
                },
              ].map((item) => (
                <div
                  key={item.title}
                  className="rounded-md border border-subtle bg-surface-raised p-4"
                >
                  <ShieldCheck
                    aria-hidden
                    className="h-5 w-5 text-accent-300"
                  />
                  <h3 className="mt-3 text-sm font-medium text-primary">
                    {item.title}
                  </h3>
                  <p className="mt-1.5 text-xs leading-5 text-secondary">
                    {item.body}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="mx-auto w-full max-w-[900px] px-4 py-14 sm:px-6">
          <h2 className="text-2xl tracking-tight text-primary">
            Questions, answered
          </h2>
          <div className="mt-6 flex flex-col divide-y divide-subtle rounded-lg border border-subtle bg-surface">
            {FAQ.map((item) => (
              <div key={item.question} className="px-5 py-5">
                <h3 className="text-sm font-medium text-primary">
                  {item.question}
                </h3>
                <p className="mt-1.5 text-sm leading-6 text-secondary">
                  {item.answer}
                </p>
              </div>
            ))}
          </div>
        </section>
      </main>

      <LandingFooter />
      <PaymentsComingSoonDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
      />
    </div>
  );
}
