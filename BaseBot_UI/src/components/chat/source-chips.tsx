import * as React from "react";
import { FileText } from "lucide-react";
import { cn } from "@/lib/cn";
import { GroundingWarning } from "./grounding-warning";
import type { Source } from "@/types/api";

/**
 * Citation chips under an answer. An empty array renders the grounding
 * warning instead — never an empty container.
 */
export function SourceChips({
  sources,
  variant = "inline",
}: {
  sources: Source[] | null | undefined;
  variant?: "inline" | "block";
}) {
  if (!sources || sources.length === 0) {
    return <GroundingWarning compact={variant === "inline"} />;
  }

  return (
    <ul
      aria-label="Sources"
      className={cn(
        "flex flex-wrap gap-1.5",
        variant === "block" && "mt-2",
      )}
    >
      {sources.map((source, index) => (
        <li
          key={`${source.filename}-${source.chunk_index}-${index}`}
          className="inline-flex items-center gap-1.5 rounded-chip border border-subtle bg-surface-raised px-2 py-0.5 text-2xs text-secondary"
          title={
            typeof source.chunk_index === "number"
              ? `${source.filename} · chunk ${source.chunk_index}`
              : source.filename
          }
        >
          <FileText aria-hidden className="h-3 w-3 shrink-0 text-tertiary" />
          <span className="max-w-[220px] truncate">{source.filename}</span>
          {typeof source.chunk_index === "number" && (
            <span className="font-mono text-tertiary">#{source.chunk_index}</span>
          )}
        </li>
      ))}
    </ul>
  );
}