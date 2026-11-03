import * as React from "react";
import { ExternalLink, FileText, Globe2 } from "lucide-react";
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
      {sources.map((source, index) => {
        const isWebsite = Boolean(source.source_url);
        const title =
          typeof source.chunk_index === "number"
            ? `${source.filename} · chunk ${source.chunk_index}`
            : source.filename;

        const content = (
          <>
            {isWebsite ? (
              <Globe2 aria-hidden className="h-3 w-3 shrink-0 text-accent-400" />
            ) : (
              <FileText aria-hidden className="h-3 w-3 shrink-0 text-tertiary" />
            )}
            <span
              className={cn(
                "max-w-[220px] truncate",
                isWebsite && "group-hover:underline",
              )}
            >
              {source.filename}
            </span>
            {typeof source.chunk_index === "number" && (
              <span className="font-mono text-tertiary">#{source.chunk_index}</span>
            )}
            {isWebsite && (
              <ExternalLink
                aria-hidden
                className="h-2.5 w-2.5 shrink-0 text-tertiary"
              />
            )}
          </>
        );

        return (
          <li
            key={`${source.filename}-${source.chunk_index}-${index}`}
            title={isWebsite ? `${title} · ${source.source_url}` : title}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-chip border border-subtle bg-surface-raised px-2 py-0.5 text-2xs text-secondary",
              isWebsite && "hover:border-strong hover:text-primary",
            )}
          >
            {source.source_url ? (
              <a
                href={source.source_url}
                target="_blank"
                rel="noreferrer"
                className="group inline-flex items-center gap-1.5 rounded-chip focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500"
                aria-label={`${title} (opens website)`}
              >
                {content}
              </a>
            ) : (
              content
            )}
          </li>
        );
      })}
    </ul>
  );
}