"use client";

import * as React from "react";
import Link from "next/link";
import { Sparkles } from "lucide-react";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { ErrorPanel } from "@/components/common/error-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { formatBytes, parseApiDate } from "@/lib/format";
import { PLAN_BLURB, PLAN_CTA, planHighlights } from "@/lib/plan-copy";
import { useBilling } from "@/hooks/use-billing";
import type { UsageCounter } from "@/types/api";
import { PlanBadge } from "./plan-badge";
import { PlanCard } from "./plan-card";
import { PaymentsComingSoonDialog } from "./payments-coming-soon-dialog";
import { UsageMeter } from "./usage-meter";

function formatDate(value: string | null | undefined): string {
  const date = parseApiDate(value);
  if (!date) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    // Billing periods are calendar months in UTC. Formatting in the
    // viewer's zone would show 31 October for a 1 November reset.
    timeZone: "UTC",
  }).format(date);
}

function atLimit(counter: UsageCounter): boolean {
  return counter.limit !== null && counter.used >= counter.limit;
}

function meterHint(counter: UsageCounter, atLimitLabel: string): string {
  if (counter.limit === null) return "Unlimited on this plan";
  if (atLimit(counter)) return atLimitLabel;
  return `${(counter.limit - counter.used).toLocaleString("en-GB")} available`;
}

/**
 * Workspace Plan tab: current subscription, live usage and the catalogue.
 * Every number comes from the billing endpoint; the page never guesses a limit.
 */
export function BillingPanel({ wsId }: { wsId: string }) {
  const billing = useBilling(wsId);
  const [upgradeOpen, setUpgradeOpen] = React.useState(false);

  if (billing.isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton width={220} height={28} />
        <Skeleton variant="card" />
        <div className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} variant="card" />
          ))}
        </div>
      </div>
    );
  }

  if (billing.isError || !billing.data) {
    return (
      <ErrorPanel
        title="We could not load your plan"
        statusCode={(billing.error as { status?: number })?.status}
        onRetry={() => void billing.refetch()}
      />
    );
  }

  const data = billing.data;
  const { plan, usage } = data;
  const agentsAtLimit = atLimit(usage.agents);
  const docsAtLimit = atLimit(usage.documents);
  const pagesAtLimit = atLimit(usage.pages_indexed);
  const websitesAtLimit = atLimit(usage.website_sources);
  const keysAtLimit = atLimit(usage.api_keys);
  const embedAtLimit = atLimit(usage.embed_tokens);
  const chatAtLimit = atLimit(usage.chat_messages);
  const storageAtLimit = usage.storage.used_bytes >= usage.storage.limit_bytes;
  const anyLimitReached =
    agentsAtLimit ||
    docsAtLimit ||
    pagesAtLimit ||
    websitesAtLimit ||
    keysAtLimit ||
    embedAtLimit ||
    chatAtLimit ||
    storageAtLimit;
  const resetDate = formatDate(usage.chat_messages.resets_at);
  const trialEnd = formatDate(data.trial_ends_at);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-lg font-medium text-primary">Plan &amp; usage</h2>
          <PlanBadge plan={plan.id} />
          {data.is_trial && (
            <span className="rounded-full border border-accent-500/40 bg-accent-tint px-2.5 py-0.5 text-2xs font-medium uppercase tracking-wide text-accent-300">
              Trial
            </span>
          )}
        </div>
        <p className="mt-1 max-w-2xl text-sm leading-5 text-secondary">
          Every limit is visible here before you reach it. Nothing is charged
          automatically.
        </p>
      </div>

      {data.is_trial ? (
        <AlertBanner
          tone="info"
          icon={Sparkles}
          title={`Pro trial — ${data.days_remaining ?? 0} day${
            data.days_remaining === 1 ? "" : "s"
          } left`}
        >
          Your account has full Pro access until {trialEnd}. No card is on
          file. After the trial, the account moves to Free automatically and
          the limits below apply — your data stays intact.
        </AlertBanner>
      ) : (
        <AlertBanner
          tone="info"
          icon={Sparkles}
          title="Paid plans are not available yet"
        >
          Standard and Pro are shown for transparency with their final TZS
          prices and limits. Paid upgrades will open here once payments go
          live — no card is on file and there is no automatic charge.
        </AlertBanner>
      )}

      {anyLimitReached && (
        <AlertBanner tone="warning" title="You have reached a plan limit">
          <ul className="ml-4 list-disc space-y-1">
            {agentsAtLimit && (
              <li>
                {usage.agents.used} of {usage.agents.limit} agents used. Delete
                an agent or upgrade to add another.
              </li>
            )}
            {docsAtLimit && (
              <li>
                {usage.documents.used} of {usage.documents.limit} documents
                used. Delete a document or upgrade for more.
              </li>
            )}
            {pagesAtLimit && (
              <li>
                {usage.pages_indexed.used} of {usage.pages_indexed.limit}{" "}
                indexed pages used. Remove a website page or upgrade for more.
              </li>
            )}
            {websitesAtLimit && (
              <li>
                {usage.website_sources.used} of {usage.website_sources.limit}{" "}
                website sources used. Remove a source or upgrade for more.
              </li>
            )}
            {keysAtLimit && (
              <li>
                Developer API keys are used up. Revoke a key or upgrade for
                more.
              </li>
            )}
            {embedAtLimit && (
              <li>
                Embed tokens are used up. Deactivate a token or upgrade for
                more.
              </li>
            )}
            {chatAtLimit && (
              <li>
                Monthly chat messages are used up. New messages pause until{" "}
                {resetDate}; your documents and conversations stay available.
              </li>
            )}
            {storageAtLimit && (
              <li>
                Knowledge storage is full. Delete a document or upgrade to
                upload more.
              </li>
            )}
          </ul>
          <div className="mt-3">
            <Button asChild variant="secondary" size="sm">
              <a href="#plans">Compare plans</a>
            </Button>
          </div>
        </AlertBanner>
      )}

      <section
        aria-labelledby="current-plan-heading"
        className="rounded-lg border border-subtle bg-surface p-5 shadow-elevation-1"
      >
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-2xs font-medium uppercase tracking-wide text-tertiary">
              Current plan
            </p>
            <h3
              id="current-plan-heading"
              className="mt-1 flex items-center gap-2 text-xl font-semibold text-primary"
            >
              {data.is_trial ? "Pro trial" : plan.name}
              <span className="text-sm font-normal text-secondary">
                {data.is_trial ? "Full Pro access" : plan.price_label}
                {!data.is_trial && plan.period === "month"
                  ? " / month"
                  : ""}
              </span>
            </h3>
            <p className="mt-1 text-sm text-secondary">
              {data.is_trial
                ? `Ends ${trialEnd} — then Free automatically`
                : data.plan_started_at
                  ? `${
                      plan.id === "free" ? "Free since " : "Active since "
                    }${formatDate(data.plan_started_at)}`
                  : plan.id === "free"
                    ? "Free forever — no expiry"
                    : "Active now"}
            </p>
          </div>
          <div className="text-right">
            <p className="text-2xs font-medium uppercase tracking-wide text-tertiary">
              Chat allowance resets
            </p>
            <p className="mt-1 text-sm font-medium text-primary">{resetDate}</p>
          </div>
        </div>

        <div className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <UsageMeter
            label="Chat messages"
            used={usage.chat_messages.used}
            limit={usage.chat_messages.limit}
            percent={usage.chat_messages.percent}
            hint={`Resets ${resetDate} (UTC)`}
          />
          <UsageMeter
            label="AI agents"
            used={usage.agents.used}
            limit={usage.agents.limit}
            percent={usage.agents.percent}
            hint={meterHint(
              usage.agents,
              "Limit reached — delete an agent or upgrade.",
            )}
          />
          <UsageMeter
            label="Documents"
            used={usage.documents.used}
            limit={usage.documents.limit}
            percent={usage.documents.percent}
            hint={meterHint(
              usage.documents,
              "Limit reached — delete a document or upgrade.",
            )}
          />
          <UsageMeter
            label="Website sources"
            used={usage.website_sources.used}
            limit={usage.website_sources.limit}
            percent={usage.website_sources.percent}
            hint={meterHint(
              usage.website_sources,
              "Limit reached — remove a source or upgrade.",
            )}
          />
          <UsageMeter
            label="Indexed pages"
            used={usage.pages_indexed.used}
            limit={usage.pages_indexed.limit}
            percent={usage.pages_indexed.percent}
            hint={meterHint(
              usage.pages_indexed,
              "Limit reached — remove a page or upgrade.",
            )}
          />
          <UsageMeter
            label="Developer API keys"
            used={usage.api_keys.used}
            limit={usage.api_keys.limit}
            percent={usage.api_keys.percent}
            hint={meterHint(
              usage.api_keys,
              "Limit reached — revoke a key or upgrade.",
            )}
          />
          <UsageMeter
            label="Embed tokens"
            used={usage.embed_tokens.used}
            limit={usage.embed_tokens.limit}
            percent={usage.embed_tokens.percent}
            hint={meterHint(
              usage.embed_tokens,
              "Limit reached — deactivate a token or upgrade.",
            )}
          />
          <UsageMeter
            label="Knowledge storage"
            used={usage.storage.used_bytes}
            limit={usage.storage.limit_bytes}
            percent={usage.storage.percent}
            format="bytes"
            hint={
              storageAtLimit
                ? "Full — delete a document or upgrade."
                : `${formatBytes(
                    usage.storage.limit_bytes - usage.storage.used_bytes,
                  )} available`
            }
          />
        </div>

        <p className="mt-5 border-t border-subtle pt-4 text-2xs text-tertiary">
          Team seats: {usage.members.used} of {usage.members.limit}
          {plan.id === "free"
            ? " (just you)"
            : " · member invites are coming soon"}
          {" · "}Chat messages are counted per account, per calendar month,
          before the answer is generated.
        </p>
      </section>

      <section id="plans" aria-labelledby="plans-heading" className="scroll-mt-8">
        <div className="mb-4">
          <h3 id="plans-heading" className="text-lg font-medium text-primary">
            Plans
          </h3>
          <p className="mt-1 max-w-2xl text-sm leading-5 text-secondary">
            Standard adds more capacity. Pro removes the agent, document,
            page, website, API-key, chat and embed-token limits. Each paid plan
            keeps everything in the tiers below it.
          </p>
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          {data.plans.map((candidate) => {
            const isCurrent = candidate.id === plan.id;
            return (
              <PlanCard
                key={candidate.id}
                plan={candidate}
                current={isCurrent}
                blurb={PLAN_BLURB[candidate.id]}
                highlights={planHighlights(candidate)}
                action={
                  isCurrent ? (
                    <Button fullWidth variant="secondary" disabled>
                      Current plan
                    </Button>
                  ) : (
                    <Button
                      fullWidth
                      variant={candidate.recommended ? "primary" : "secondary"}
                      onClick={() => setUpgradeOpen(true)}
                    >
                      {candidate.price_tzs === 0
                        ? "Switch to Free"
                        : PLAN_CTA[candidate.id]}
                    </Button>
                  )
                }
              />
            );
          })}
        </div>
      </section>

      <AlertBanner tone="info" title="No surprise charges">
        At a limit, the affected action pauses. Nothing is charged
        automatically and your workspace stays accessible — the chat allowance
        resets on {resetDate}. Prefer to move sooner?{" "}
        <Link href="/pricing" className="text-accent-300 hover:underline">
          Compare all three plans
        </Link>
        .
      </AlertBanner>

      <PaymentsComingSoonDialog
        open={upgradeOpen}
        onClose={() => setUpgradeOpen(false)}
      />
    </div>
  );
}
