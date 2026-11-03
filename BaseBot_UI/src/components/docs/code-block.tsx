"use client";

import * as React from "react";
import { Check, Copy } from "lucide-react";

function languageLabel(language?: string) {
  if (!language) return "text";
  const labels: Record<string, string> = {
    bash: "bash",
    sh: "shell",
    shell: "shell",
    curl: "cURL",
    js: "JavaScript",
    javascript: "JavaScript",
    ts: "TypeScript",
    typescript: "TypeScript",
    py: "Python",
    python: "Python",
    json: "JSON",
    html: "HTML",
    css: "CSS",
    text: "text",
  };
  return labels[language.toLowerCase()] ?? language;
}

export function CodeBlock({
  code,
  language,
  label,
}: {
  code: string;
  language?: string;
  label?: string;
}) {
  const [copied, setCopied] = React.useState(false);
  const cleanCode = code.replace(/^\n+|\n+$/g, "");

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(cleanCode);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = cleanCode;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    }
  };

  return (
    <div className="docs-code-shell">
      <div className="docs-code-head">
        <span className="docs-code-label">{label ?? languageLabel(language)}</span>
        <button type="button" className="docs-code-copy" onClick={copy}>
          {copied ? (
            <Check aria-hidden className="h-3.5 w-3.5" />
          ) : (
            <Copy aria-hidden className="h-3.5 w-3.5" />
          )}
          <span aria-live="polite">{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>
      <pre className="docs-code-pre">
        <code>{cleanCode}</code>
      </pre>
    </div>
  );
}

export type CodeTab = {
  label: string;
  language: string;
  code: string;
};

export function CodeTabs({ tabs }: { tabs: CodeTab[] }) {
  const [active, setActive] = React.useState(0);
  const safeActive = Math.min(active, tabs.length - 1);

  if (!tabs.length) return null;

  return (
    <div className="docs-tabs">
      <div className="docs-tab-list" role="tablist" aria-label="Code examples">
        {tabs.map((tab, index) => (
          <button
            key={`${tab.label}-${index}`}
            type="button"
            role="tab"
            id={`docs-tab-${index}`}
            aria-selected={index === safeActive}
            aria-controls={`docs-tab-panel-${index}`}
            tabIndex={index === safeActive ? 0 : -1}
            className="docs-tab"
            onClick={() => setActive(index)}
            onKeyDown={(event) => {
              if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
              event.preventDefault();
              const next =
                event.key === "ArrowRight"
                  ? (index + 1) % tabs.length
                  : (index - 1 + tabs.length) % tabs.length;
              setActive(next);
              document.getElementById(`docs-tab-${next}`)?.focus();
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id={`docs-tab-panel-${safeActive}`}
        aria-labelledby={`docs-tab-${safeActive}`}
      >
        <CodeBlock
          code={tabs[safeActive].code}
          language={tabs[safeActive].language}
          label={tabs[safeActive].label}
        />
      </div>
    </div>
  );
}
