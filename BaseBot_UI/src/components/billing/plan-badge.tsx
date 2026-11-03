import { cn } from "@/lib/cn";
import type { PlanId } from "@/types/api";

const STYLES: Record<PlanId, string> = {
  free: "border-subtle bg-surface-raised text-secondary",
  standard: "border-accent-500/40 bg-accent-tint text-accent-300",
  pro: "border-warning-500/40 bg-warning-500/10 text-warning-400",
};

const LABELS: Record<PlanId, string> = {
  free: "Free",
  standard: "Standard",
  pro: "Pro",
};

/** Compact plan pill used in the workspace header, cards and billing panel. */
export function PlanBadge({
  plan,
  className,
}: {
  plan: PlanId;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-2xs font-medium uppercase tracking-wide",
        STYLES[plan],
        className,
      )}
    >
      {LABELS[plan]}
    </span>
  );
}
