"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { FileText, Search } from "lucide-react";

type SearchDoc = {
  title: string;
  description: string;
  href: string;
  group: string;
  headings: string[];
  text: string;
};

type SearchResult = SearchDoc & { score: number; snippet: string };

function scoreDoc(doc: SearchDoc, query: string): number {
  const phrase = query.toLowerCase().trim();
  const tokens = phrase.split(/\s+/).filter(Boolean);
  if (!tokens.length) return 1;

  const title = doc.title.toLowerCase();
  const description = doc.description.toLowerCase();
  const headings = doc.headings.join(" ").toLowerCase();
  const text = doc.text.toLowerCase();

  let score = 0;
  if (title.includes(phrase)) score += 40;
  for (const token of tokens) {
    if (!title.includes(token) && !description.includes(token) && !headings.includes(token) && !text.includes(token)) {
      return 0;
    }
    if (title.includes(token)) score += 14;
    if (headings.includes(token)) score += 6;
    if (description.includes(token)) score += 4;
    if (text.includes(token)) score += 1;
  }
  if (doc.title.toLowerCase().startsWith(phrase)) score += 12;
  return score;
}

function makeSnippet(doc: SearchDoc, query: string): string {
  const tokens = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  const source = doc.text || doc.description;
  const lower = source.toLowerCase();
  const hit = tokens
    .map((token) => lower.indexOf(token))
    .filter((index) => index >= 0)
    .sort((a, b) => a - b)[0];
  if (hit === undefined) return doc.description;
  const start = Math.max(0, hit - 55);
  const end = Math.min(source.length, hit + 145);
  return `${start > 0 ? "…" : ""}${source.slice(start, end).trim()}${
    end < source.length ? "…" : ""
  }`;
}

export function DocsSearch({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [query, setQuery] = React.useState("");
  const [docs, setDocs] = React.useState<SearchDoc[] | null>(null);
  const [error, setError] = React.useState(false);
  const [active, setActive] = React.useState(0);

  React.useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() => inputRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [open]);

  React.useEffect(() => {
    if (!open || docs !== null) return;
    let cancelled = false;
    fetch("/docs/search-index.json")
      .then((response) => {
        if (!response.ok) throw new Error("Search index unavailable");
        return response.json() as Promise<SearchDoc[]>;
      })
      .then((payload) => {
        if (!cancelled) setDocs(payload);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [open, docs]);

  React.useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  const results = React.useMemo<SearchResult[]>(() => {
    if (!docs) return [];
    const trimmed = query.trim();
    if (!trimmed) {
      return docs.slice(0, 8).map((doc) => ({
        ...doc,
        score: 1,
        snippet: doc.description,
      }));
    }
    return docs
      .map((doc) => ({
        ...doc,
        score: scoreDoc(doc, trimmed),
        snippet: makeSnippet(doc, trimmed),
      }))
      .filter((doc) => doc.score > 0)
      .sort((a, b) => b.score - a.score || a.title.localeCompare(b.title))
      .slice(0, 10);
  }, [docs, query]);

  React.useEffect(() => {
    setActive(0);
  }, [query, open]);

  if (!open) return null;

  const go = (result: SearchResult | undefined) => {
    if (!result) return;
    onClose();
    router.push(result.href);
  };

  return (
    <div
      className="docs-search-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search documentation"
        className="docs-search-dialog"
      >
        <div className="docs-search-field">
          <Search aria-hidden className="h-4 w-4 shrink-0 text-[var(--docs-text-tertiary)]" />
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActive((index) =>
                  results.length ? (index + 1) % results.length : 0,
                );
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setActive((index) =>
                  results.length
                    ? (index - 1 + results.length) % results.length
                    : 0,
                );
              } else if (event.key === "Enter") {
                event.preventDefault();
                go(results[active]);
              }
            }}
            className="docs-search-input"
            placeholder="Search guides, API reference, troubleshooting…"
            aria-label="Search documentation"
            aria-controls="docs-search-results"
            aria-activedescendant={
              results[active] ? `docs-search-result-${active}` : undefined
            }
          />
          <button
            type="button"
            onClick={onClose}
            className="docs-search-close"
            aria-label="Close search"
          >
            ESC
          </button>
        </div>

        <div
          className="docs-search-results"
          id="docs-search-results"
          role="listbox"
          aria-label="Search results"
        >
          {error ? (
            <p className="docs-search-empty">
              Search is unavailable right now. Reload the page to try again.
            </p>
          ) : docs === null ? (
            <p className="docs-search-empty">Loading search…</p>
          ) : results.length === 0 ? (
            <p className="docs-search-empty">
              No results for “{query}”. Try a shorter phrase such as “widget”,
              “trial” or “API key”.
            </p>
          ) : (
            results.map((result, index) => (
              <a
                key={result.href}
                id={`docs-search-result-${index}`}
                role="option"
                aria-selected={index === active}
                href={result.href}
                className={`docs-search-result${index === active ? " is-active" : ""}`}
                onMouseEnter={() => setActive(index)}
                onClick={(event) => {
                  event.preventDefault();
                  go(result);
                }}
              >
                <span className="docs-search-result-title">
                  <FileText
                    aria-hidden
                    className="h-3.5 w-3.5 shrink-0 text-[var(--docs-text-tertiary)]"
                  />
                  {result.title}
                  <span className="docs-search-result-group">{result.group}</span>
                </span>
                <span className="docs-search-result-snippet">
                  {result.snippet}
                </span>
              </a>
            ))
          )}
        </div>

        <div className="docs-search-help" aria-hidden>
          <span>
            <kbd>↑</kbd> <kbd>↓</kbd> navigate
          </span>
          <span>
            <kbd>Enter</kbd> open
          </span>
          <span>
            <kbd>Esc</kbd> close
          </span>
          <span className="ml-auto">Search runs on this site only</span>
        </div>
      </div>
    </div>
  );
}
