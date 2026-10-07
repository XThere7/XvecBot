"use client";

import * as React from "react";
import { motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/cn";

/**
 * PREMIUM MOMENT 3 — Aceternity "Focus Cards" glow treatment, used once behind
 * the one-time-token modal to mark it as the highest-anxiety screen in the
 * product. Combined with the modal's own scale-in entrance.
 */
export function FocusGlow({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <div className={cn("relative isolate", className)}>
      <motion.div
        aria-hidden
        initial={reduceMotion ? false : { opacity: 0.35 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.2 }}
        className="pointer-events-none absolute -inset-8 -z-10 rounded-[32px] bg-[radial-gradient(circle_at_50%_0%,rgba(99,102,241,0.35),transparent_60%)] blur-2xl"
      />
      <div className="relative">{children}</div>
    </div>
  );
}

export default FocusGlow;