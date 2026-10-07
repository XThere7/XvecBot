"use client";

import { cn } from "@/lib/cn";

/**
 * PREMIUM MOMENT 1 — Aceternity "Background Beams", used once behind the
 * dashboard hero / onboarding empty state. Lazy-loaded with next/dynamic.
 */
export function BackgroundBeams({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)}
    >
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(99,102,241,0.18),transparent_58%)]" />
      <div className="absolute left-1/2 top-[-60%] h-[120%] w-[70%] -translate-x-1/2 opacity-40 blur-3xl">
        <div className="absolute left-[18%] top-0 h-full w-16 rotate-[18deg] bg-gradient-to-b from-accent-500/40 via-accent-500/10 to-transparent" />
        <div className="absolute left-[46%] top-0 h-full w-24 rotate-[10deg] bg-gradient-to-b from-accent-400/30 via-accent-400/8 to-transparent" />
        <div className="absolute left-[74%] top-0 h-full w-10 rotate-[24deg] bg-gradient-to-b from-accent-600/40 via-accent-600/10 to-transparent" />
      </div>
      <div
        className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-canvas to-transparent"
      />
    </div>
  );
}

export default BackgroundBeams;