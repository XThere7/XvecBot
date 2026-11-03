import * as React from "react";
import { Check, Clock } from "lucide-react";
import { cn } from "@/lib/cn";
import type { PlanHighlight } from "@/lib/plan-copy";
import type { Plan } from "@/types/api";
import { PlanBadge } from "./plan-badge";

export type PlanCardProps = {
  plan: Plan;
  highlights: PlanHighlight[];
  blurb: string;
  current?: boolean;
  /** Primary action — a link on the pricing page, a dialog trigger in-app. */
  action: React.ReactNode;
  className?: string;
};

/**
 * One tier. Prices and limits are rendered from the API plan object; only the
 * narrative copy and the action are supplied by the page.
 */
export function PlanCard({
  plan,
  highlights,
  blurb,
  current = false,
  action,
  className,
}: PlanCardProps) {
  return (
    <article
      className={cn(
        "relative flex h-full flex-col rounded-lg border bg-surface p-6 shadow-elevation-1",
        plan.recommended
          ? "border-accent-500/50"
          : "border-subtle",
        current && "ring-1 ring-accent-500/60",
        className,
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-semibold text-primary">{plan.name}</h3>
          {current && <PlanBadge plan={plan.id} />}
        </div>
        {plan.recommended && (
          <span className="rounded-full border border-accent-500/40 bg-accent-tint px-2.5 py-0.5 text-2xs font-medium uppercase tracking-wide text-accent-300">
            Recommended
          </span>
        )}
      </div>

      <p className="mt-2 min-h-[40px] text-sm leading-5 text-secondary">
        {blurb}
      </p>

      <div className="mt-4 flex items-baseline gap-1.5">
        <span className="text-3xl font-semibold tracking-tight text-primary">
          {plan.price_label}
        </span>
        <span className="text-sm text-tertiary">
          {plan.period === "forever" ? "forever" : "/ month"}
        </span>
      </div>
      <p className="mt-1 text-2xs text-tertiary">
        {plan.period === "forever"
          ? "No card required. No expiry."
          : "Per workspace. Billed monthly when payments go live."}
      </p>

      <div className="mt-5">{action}</div>

      <ul className="mt-5 flex flex-col gap-2.5 border-t border-subtle pt-5">
        {highlights.map((highlight) => (
          <li key={highlight.label} className="flex items-start gap-2 text-sm">
            <Check
              aria-hidden
              className="mt-0.5 h-4 w-4 shrink-0 text-accent-300"
            />
            <span className="min-w-0 flex-1 leading-5 text-secondary">
              {highlight.label}
            </span>
            {highlight.soon && (
              <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-warning-500/30 bg-warning-500/10 px-1.5 py-0.5 text-2xs text-warning-400">
                <Clock aria-hidden className="h-3 w-3" />
                Soon
              </span>
            )}
          </li>
        ))}
      </ul>
    </article>
  );
}
