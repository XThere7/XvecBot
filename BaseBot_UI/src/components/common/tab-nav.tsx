"use client";

import * as React from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/cn";

export type TabItem = { id: string; label: string; href: string; count?: number };

/**
 * Tab navigation. The active tab lives in the URL (`?tab=`) so links are
 * shareable and browser Back works — this is mandatory, not optional.
 */
export function TabNav({
  tabs,
  active,
  layoutId = "tab-underline",
  className,
  ariaLabel = "Sections",
}: {
  tabs: TabItem[];
  active: string;
  layoutId?: string;
  className?: string;
  ariaLabel?: string;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <nav aria-label={ariaLabel} className={cn("max-w-full overflow-x-auto", className)}>
      <div className="flex min-w-max items-center gap-1 border-b border-subtle">
        {tabs.map((tab) => {
          const isActive = tab.id === active;
          return (
            <Link
              key={tab.id}
              href={tab.href}
              aria-current={isActive ? "page" : undefined}
              className={cn(
                "relative whitespace-nowrap px-3 py-2.5 text-sm font-medium transition-colors duration-150",
                isActive ? "text-primary" : "text-secondary hover:text-primary",
              )}
            >
              <span className="inline-flex items-center gap-2">
                {tab.label}
                {typeof tab.count === "number" && (
                  <span
                    className={cn(
                      "rounded-chip px-1.5 py-0.5 text-2xs",
                      isActive
                        ? "bg-accent-tint text-accent-300"
                        : "bg-surface-raised text-tertiary",
                    )}
                  >
                    {tab.count}
                  </span>
                )}
              </span>
              {isActive && (
                <motion.span
                  layoutId={layoutId}
                  transition={
                    reduceMotion
                      ? { duration: 0 }
                      : { type: "spring", stiffness: 380, damping: 32 }
                  }
                  className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-accent-500"
                />
              )}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

/** Direction-aware slide + fade for tab content swaps (180 ms). */
export function TabContent({
  tabKey,
  children,
  className,
  offset = false,
}: {
  tabKey: string;
  children: React.ReactNode;
  className?: string;
  offset?: boolean;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      key={tabKey}
      initial={reduceMotion ? false : { opacity: 0, x: 8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      className={cn(offset && "mt-6", className)}
    >
      {children}
    </motion.div>
  );
}