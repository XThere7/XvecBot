import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/cn";

/** `sources: []` is not an error — retrieval simply found nothing. */
export function GroundingWarning({
  className,
  compact = false,
}: {
  className?: string;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        compact
          ? "flex items-center gap-1.5 text-2xs text-warning-400"
          : "flex items-start gap-1.5 rounded-sm bg-warning-500/10 px-2 py-1.5 text-2xs leading-4 text-warning-400",
        className,
      )}
    >
      <AlertTriangle aria-hidden className="mt-px h-3 w-3 shrink-0" />
      <span>
        No sources found — this answer was not grounded in your documents.
      </span>
    </div>
  );
}