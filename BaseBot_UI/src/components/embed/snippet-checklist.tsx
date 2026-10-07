"use client";

import * as React from "react";
import { Check, ExternalLink } from "lucide-react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/button";
import { SITE_URL } from "@/lib/constants";

const STEPS = [
  "Snippet copied",
  "Pasted before </body>",
  "Widget visible on the live site",
];

export function SnippetChecklist({
  /** Optional reset so the modal can restore an unchecked list. */
  resetKey,
}: {
  resetKey?: string | number;
}) {
  const [done, setDone] = React.useState<boolean[]>(() =>
    STEPS.map(() => false),
  );

  React.useEffect(() => {
    setDone(STEPS.map(() => false));
  }, [resetKey]);

  const toggle = (index: number) =>
    setDone((current) =>
      current.map((value, i) => (i === index ? !value : value)),
    );

  return (
    <div className="flex flex-col gap-3">
      <ol className="flex flex-col gap-2">
        {STEPS.map((step, index) => (
          <li key={step}>
            <button
              type="button"
              onClick={() => toggle(index)}
              aria-pressed={done[index]}
              className={cn(
                "flex w-full items-center gap-3 rounded-sm border px-3 py-2 text-left text-sm transition-colors",
                done[index]
                  ? "border-success-500/30 bg-success-500/5 text-secondary"
                  : "border-subtle bg-surface-raised text-primary hover:bg-surface-hover",
              )}
            >
              <span
                aria-hidden
                className={cn(
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border",
                  done[index]
                    ? "border-success-500 bg-success-500/20 text-success-400"
                    : "border-strong text-transparent",
                )}
              >
                <Check className="h-3 w-3" />
              </span>
              <span className="flex-1">{step}</span>
              <span className="sr-only">{done[index] ? "Done" : "Not done"}</span>
            </button>
          </li>
        ))}
      </ol>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-2xs text-tertiary">
          Works on any website — no build step, no framework.
        </p>
        <Button
          asChild
          variant="secondary"
          size="sm"
          iconRight={<ExternalLink aria-hidden className="h-3.5 w-3.5" />}
        >
          <a href={SITE_URL || "/"} target="_blank" rel="noopener noreferrer">
            Test it
          </a>
        </Button>
      </div>
    </div>
  );
}