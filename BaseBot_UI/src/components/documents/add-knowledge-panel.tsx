"use client";

import * as React from "react";
import { FileText, Globe2 } from "lucide-react";
import { cn } from "@/lib/cn";

export type AddKnowledgeMode = "upload" | "website";

const OPTIONS: {
  mode: AddKnowledgeMode;
  icon: React.ElementType;
  title: string;
  description: string;
}[] = [
  {
    mode: "upload",
    icon: FileText,
    title: "Upload documents",
    description: "PDF, TXT or DOCX files from your device.",
  },
  {
    mode: "website",
    icon: Globe2,
    title: "Connect a website",
    description: "Index up to 50 public pages from a URL.",
  },
];

/**
 * The two ways to add knowledge sit side by side. Only the selected form is
 * mounted, but both options stay visible so a website-only workspace is never
 * pushed towards uploading a document.
 */
export function AddKnowledgePanel({
  mode,
  onModeChange,
  uploadZone,
  websiteForm,
}: {
  mode: AddKnowledgeMode;
  onModeChange: (mode: AddKnowledgeMode) => void;
  uploadZone: React.ReactNode;
  websiteForm: React.ReactNode;
}) {
  return (
    <section
      aria-labelledby="add-knowledge-heading"
      className="rounded-md border border-subtle bg-surface p-4 sm:p-5"
    >
      <div>
        <h2 id="add-knowledge-heading" className="text-base font-semibold text-primary">
          Add knowledge
        </h2>
        <p className="mt-1 text-sm text-secondary">
          Agents answer from uploaded documents and indexed website pages. Pick
          either one to get started.
        </p>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {OPTIONS.map((option) => {
          const Icon = option.icon;
          const selected = mode === option.mode;
          return (
            <button
              key={option.mode}
              type="button"
              aria-pressed={selected}
              onClick={() => onModeChange(option.mode)}
              className={cn(
                "flex min-h-[64px] items-start gap-3 rounded-sm border px-3.5 py-3 text-left transition-colors duration-150",
                "focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-500",
                selected
                  ? "border-accent-500/60 bg-accent-tint"
                  : "border-subtle bg-surface-raised hover:border-strong hover:bg-surface-hover",
              )}
            >
              <span
                aria-hidden
                className={cn(
                  "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border",
                  selected
                    ? "border-accent-500/30 bg-surface text-accent-400"
                    : "border-subtle bg-surface text-tertiary",
                )}
              >
                <Icon className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <span
                  className={cn(
                    "block text-sm font-medium",
                    selected ? "text-primary" : "text-secondary",
                  )}
                >
                  {option.title}
                </span>
                <span className="mt-0.5 block text-xs text-tertiary">
                  {option.description}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-4">
        {mode === "upload" ? uploadZone : websiteForm}
      </div>
    </section>
  );
}
