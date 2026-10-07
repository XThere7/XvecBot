import { cn } from "@/lib/cn";

/**
 * Indeterminate progress. The API never returns a percentage, so this never
 * pretends to know how far along training is.
 */
export function IndeterminateProgress({
  className,
  label = "Training in progress",
}: {
  className?: string;
  label?: string;
}) {
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-busy="true"
      className={cn("h-1 w-full overflow-hidden rounded-full bg-inset", className)}
    >
      <div className="h-full w-1/3 animate-indeterminate rounded-full bg-warning-500/80" />
    </div>
  );
}