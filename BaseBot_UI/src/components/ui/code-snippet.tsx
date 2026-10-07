"use client";

import * as React from "react";
import { cn } from "@/lib/cn";
import { CopyButton } from "./copy-button";

type TokenKind = "comment" | "tag" | "attr" | "value" | "punct" | "text";

const TOKEN_CLASS: Record<TokenKind, string> = {
  comment: "text-tertiary italic",
  tag: "text-accent-300",
  attr: "text-info-400",
  value: "text-success-400",
  punct: "text-secondary",
  text: "text-secondary",
};

/**
 * A minimal tokeniser for the six-line HTML embed snippet. A runtime
 * highlighter would cost 10–100 KB for markup that is never more than a
 * script tag, so the two-token approach is used instead.
 */
const TOKEN_RE = /(<!--[\s\S]*?-->)|(<\/?[a-zA-Z][\w-]*)|([a-zA-Z_:][\w:.-]*)(=)("[^"]*")|(\/?>)/g;

function highlightLine(line: string, keyPrefix: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  TOKEN_RE.lastIndex = 0;

  while ((match = TOKEN_RE.exec(line)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(
        <span key={`${keyPrefix}-t-${lastIndex}`} className={TOKEN_CLASS.text}>
          {line.slice(lastIndex, match.index)}
        </span>,
      );
    }
    const [full, comment, tag, attr, eq, value, punct] = match;
    if (comment) {
      nodes.push(
        <span key={`${keyPrefix}-c-${match.index}`} className={TOKEN_CLASS.comment}>
          {comment}
        </span>,
      );
    } else if (tag) {
      nodes.push(
        <span key={`${keyPrefix}-g-${match.index}`} className={TOKEN_CLASS.tag}>
          {tag}
        </span>,
      );
    } else if (attr) {
      nodes.push(
        <span key={`${keyPrefix}-a-${match.index}`} className={TOKEN_CLASS.attr}>
          {attr}
        </span>,
        <span key={`${keyPrefix}-e-${match.index}`} className={TOKEN_CLASS.punct}>
          {eq}
        </span>,
        <span key={`${keyPrefix}-v-${match.index}`} className={TOKEN_CLASS.value}>
          {value}
        </span>,
      );
    } else if (punct) {
      nodes.push(
        <span key={`${keyPrefix}-p-${match.index}`} className={TOKEN_CLASS.punct}>
          {punct}
        </span>,
      );
    }
    lastIndex = match.index + full.length;
  }

  if (lastIndex < line.length) {
    nodes.push(
      <span key={`${keyPrefix}-tail`} className={TOKEN_CLASS.text}>
        {line.slice(lastIndex)}
      </span>,
    );
  }

  return nodes;
}

export type CodeSnippetProps = {
  code: string;
  filename?: string;
  language?: "html";
  copyLabel?: React.ReactNode;
  onCopy?: () => void;
  wrap?: boolean;
  /** Rendered above the block — e.g. the two lines of paste context. */
  context?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
};

export function CodeSnippet({
  code,
  filename,
  language = "html",
  copyLabel = "Copy snippet",
  onCopy,
  wrap = false,
  context,
  footer,
  className,
}: CodeSnippetProps) {
  const [wrapOn, setWrapOn] = React.useState(wrap);
  const lines = React.useMemo(() => code.split("\n"), [code]);

  return (
    <div className={cn("overflow-hidden rounded-lg border border-subtle bg-inset", className)}>
      <div className="flex items-center justify-between gap-2 border-b border-subtle px-3 py-2">
        <span className="truncate font-mono text-2xs text-tertiary">
          {filename ?? `index.${language}`}
        </span>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setWrapOn((v) => !v)}
            className="rounded-sm px-1.5 py-1 text-2xs text-tertiary transition-colors hover:bg-surface-hover hover:text-secondary"
            aria-pressed={wrapOn}
          >
            {wrapOn ? "No wrap" : "Wrap"}
          </button>
          <CopyButton value={code} label={copyLabel} onCopied={onCopy} variant="ghost" />
        </div>
      </div>

      {context && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-subtle px-3 py-2 text-2xs text-tertiary">
          {context}
        </div>
      )}

      {/* Fixed minimum height: the block must not reflow when the code arrives. */}
      <pre className="min-h-[132px] overflow-x-auto px-3 py-3">
        <code
          className={cn(
            "block font-mono text-xs leading-5",
            // Code must not reflow on desktop, but must wrap on a phone.
            wrapOn ? "whitespace-pre-wrap break-all" : "whitespace-pre max-sm:whitespace-pre-wrap max-sm:break-all",
          )}
        >
          {lines.map((line, index) => (
            <span key={index} className="block">
              {highlightLine(line, `l${index}`)}
              {index < lines.length - 1 ? "\n" : null}
            </span>
          ))}
        </code>
      </pre>

      {footer && (
        <div className="border-t border-subtle px-3 py-2 text-2xs text-tertiary">
          {footer}
        </div>
      )}
    </div>
  );
}