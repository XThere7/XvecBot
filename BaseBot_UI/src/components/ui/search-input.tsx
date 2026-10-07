"use client";

import * as React from "react";
import { Search, X } from "lucide-react";
import { cn } from "@/lib/cn";

export function SearchInput({
  value,
  onChange,
  placeholder = "Search…",
  className,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  label: string;
}) {
  const id = React.useId();
  return (
    <div className={cn("relative w-full max-w-xs", className)}>
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <Search
        aria-hidden
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tertiary"
      />
      <input
        id={id}
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="h-9 w-full rounded-sm border border-strong bg-inset pl-9 pr-8 text-base text-primary placeholder:text-tertiary transition-colors hover:border-tertiary focus:border-accent-500 focus:outline-2 focus:outline-offset-0 focus:outline-accent-500"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Clear search"
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-sm p-1 text-tertiary transition-colors hover:bg-surface-hover hover:text-primary"
        >
          <X aria-hidden className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}