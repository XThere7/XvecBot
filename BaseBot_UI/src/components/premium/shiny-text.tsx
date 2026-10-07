"use client";

import { cn } from "@/lib/cn";

/**
 * PREMIUM MOMENT 4 — Magic UI "Animated Shiny Text", used on the embed copy
 * button's label. Lazy-loaded with next/dynamic.
 */
export function ShinyText({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "bg-clip-text text-transparent",
        "bg-[linear-gradient(110deg,var(--color-primary)_35%,var(--color-accent-300)_50%,var(--color-primary)_65%)]",
        "bg-[length:200%_100%] animate-shiny",
        className,
      )}
    >
      {children}
    </span>
  );
}

export default ShinyText;