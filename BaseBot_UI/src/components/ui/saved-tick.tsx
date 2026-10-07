import * as React from "react";
import { cn } from "@/lib/cn";

/** Inline "Saved" tick. Replaces a toast for optimistic, non-critical saves. */
export function SavedTick({
  show,
  className,
  label = "Saved",
}: {
  show: boolean;
  className?: string;
  label?: string;
}) {
  return (
    <span
      aria-live="polite"
      className={cn(
        "inline-flex items-center gap-1 text-xs text-success-400 transition-opacity duration-150",
        show ? "opacity-100" : "opacity-0",
        className,
      )}
    >
      <svg aria-hidden viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none">
        <path
          d="M3.5 8.5l3 3 6-6.5"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {label}
    </span>
  );
}