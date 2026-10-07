"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { Check, Lock, Sparkles } from "lucide-react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/button";

/** PREMIUM MOMENT 1 — lazily loaded, only on the dashboard. */
const BackgroundBeams = dynamic(
  () => import("@/components/premium/background-beams").then((m) => m.BackgroundBeams),
  { ssr: false },
);

export type OnboardingStep = {
  id: string;
  title: string;
  description: string;
  complete: boolean;
  href?: string;
  cta?: string;
  /** Disabled steps always explain why, next to the control. */
  lockedReason?: string;
};

export function OnboardingChecklist({ steps }: { steps: OnboardingStep[] }) {
  const reduceMotion = useReducedMotion();
  const complete = steps.filter((step) => step.complete).length;

  return (
    <section className="relative overflow-hidden rounded-lg border border-subtle bg-surface">
      <BackgroundBeams />
      <div className="relative px-6 py-8 sm:px-8 sm:py-10">
        <div className="max-w-xl">
          <span className="inline-flex items-center gap-1.5 rounded-chip border border-accent-500/30 bg-accent-tint px-2 py-0.5 text-2xs text-accent-300">
            <Sparkles aria-hidden className="h-3 w-3" />
            Getting started
          </span>
          <h2 className="mt-4 text-2xl text-primary">Welcome to XvecBot</h2>
          <p className="mt-2 text-sm leading-5 text-secondary">
            Three steps to your first live chat widget. Progress comes from your
            real data — nothing here is stored in the browser.
          </p>
        </div>

        <ol className="mt-8 grid gap-4 lg:grid-cols-3">
          {steps.map((step, index) => (
            <motion.li
              key={step.id}
              initial={
                reduceMotion
                  ? false
                  : { opacity: 0, y: 16, filter: "blur(4px)" }
              }
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              transition={{ duration: 0.3, delay: reduceMotion ? 0 : index * 0.08 }}
              className={cn(
                "flex flex-col rounded-md border bg-surface-raised/80 p-5 backdrop-blur-sm",
                step.complete ? "border-success-500/30" : "border-subtle",
              )}
            >
              <div className="flex items-center justify-between gap-3">
                <span
                  aria-hidden
                  className={cn(
                    "flex h-7 w-7 items-center justify-center rounded-full border text-xs font-medium",
                    step.complete
                      ? "border-success-500/40 bg-success-500/10 text-success-400"
                      : "border-subtle bg-surface text-tertiary",
                  )}
                >
                  {step.complete ? <Check className="h-3.5 w-3.5" /> : index + 1}
                </span>
                {step.complete && (
                  <span className="text-2xs text-success-400">Done</span>
                )}
              </div>

              <p className="mt-4 text-base font-medium text-primary">{step.title}</p>
              <p className="mt-1.5 text-sm leading-5 text-secondary">
                {step.description}
              </p>

              <div className="mt-5">
                {step.complete ? (
                  step.href ? (
                    <Button asChild variant="ghost" size="sm">
                      <Link href={step.href}>View</Link>
                    </Button>
                  ) : null
                ) : step.lockedReason ? (
                  <div>
                    <Button variant="secondary" size="sm" disabled iconLeft={<Lock aria-hidden className="h-3.5 w-3.5" />}>
                      {step.cta}
                    </Button>
                    <p className="mt-2 text-2xs leading-4 text-tertiary">
                      {step.lockedReason}
                    </p>
                  </div>
                ) : (
                  <Button asChild variant="primary" size="sm">
                    <Link href={step.href ?? "#"}>{step.cta}</Link>
                  </Button>
                )}
              </div>
            </motion.li>
          ))}
        </ol>

        <p className="mt-6 text-xs text-tertiary">
          {complete} of {steps.length} complete
        </p>
      </div>
    </section>
  );
}
