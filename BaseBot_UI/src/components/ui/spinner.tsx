"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

export function Spinner({ className }: { className?: string }) {
  return (
    <Loader2
      aria-hidden
      className={cn("h-4 w-4 animate-spin text-tertiary", className)}
    />
  );
}

/** Page-level fallback. Never a spinner over the whole page for lists. */
export function LoadingBlock({ label = "Loading" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-label={label}
      className="flex items-center justify-center gap-2 py-16 text-sm text-tertiary"
    >
      <Spinner />
      <span>{label}…</span>
    </div>
  );
}