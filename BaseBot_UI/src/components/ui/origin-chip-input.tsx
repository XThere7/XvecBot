"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";
import { normaliseOrigin } from "@/schemas/token";
import { useFieldProps } from "./field";

export type OriginChipInputProps = {
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  maxChips?: number;
  id?: string;
  "aria-describedby"?: string;
  invalid?: boolean;
};

/**
 * Allowed origins as bare hostnames. Enter or comma commits a chip, Backspace on
 * an empty input removes the last, pasting a comma-separated list splits it, and
 * anything containing a scheme, path or port is normalised before it is stored.
 */
export function OriginChipInput({
  value,
  onChange,
  placeholder = "mystore.co.tz",
  maxChips = 20,
  id,
  ...aria
}: OriginChipInputProps) {
  const field = useFieldProps();
  const [draft, setDraft] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  const commit = (raw: string) => {
    const normalised = normaliseOrigin(raw);
    if (!normalised) {
      setError(`"${raw.trim()}" is not a valid hostname.`);
      return;
    }
    if (value.includes(normalised)) {
      setDraft("");
      setError(null);
      return;
    }
    if (value.length >= maxChips) {
      setError(`Up to ${maxChips} origins.`);
      return;
    }
    onChange([...value, normalised]);
    setDraft("");
    setError(null);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      if (draft.trim()) commit(draft);
      return;
    }
    if (event.key === "Backspace" && !draft && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  const handlePaste = (event: React.ClipboardEvent<HTMLInputElement>) => {
    const text = event.clipboardData.getData("text");
    if (!text.includes(",") && !text.includes(" ")) return;
    event.preventDefault();
    for (const part of text.split(/[,\s]+/)) {
      if (part.trim()) commit(part);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div
        onClick={() => document.getElementById(id ?? field.id ?? "")?.focus()}
        className={cn(
          "flex min-h-[38px] flex-wrap items-center gap-1.5 rounded-sm border bg-inset px-2 py-1.5 transition-colors",
          "focus-within:outline-2 focus-within:outline-offset-0 focus-within:outline-accent-500",
          error
            ? "border-danger-500"
            : "border-strong hover:border-tertiary focus-within:border-accent-500",
        )}
      >
        {value.map((origin) => (
          <span
            key={origin}
            className="inline-flex items-center gap-1 rounded-chip border border-subtle bg-surface-raised py-0.5 pl-2 pr-1 text-xs text-primary"
          >
            {origin}
            <button
              type="button"
              onClick={() => onChange(value.filter((o) => o !== origin))}
              aria-label={`Remove ${origin}`}
              className="rounded-full p-0.5 text-tertiary transition-colors hover:bg-surface-hover hover:text-primary"
            >
              <X aria-hidden className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          id={id ?? field.id}
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value);
            setError(null);
          }}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          onBlur={() => draft.trim() && commit(draft)}
          placeholder={value.length === 0 ? placeholder : ""}
          aria-invalid={error ? true : undefined}
          aria-describedby={aria["aria-describedby"] ?? field["aria-describedby"]}
          className="h-6 min-w-[120px] flex-1 bg-transparent text-sm text-primary placeholder:text-tertiary focus:outline-none"
        />
      </div>
      {error && <p className="text-xs text-danger-400">{error}</p>}
    </div>
  );
}