"use client";

import * as React from "react";
import { Moon, Sun } from "lucide-react";
import { cn } from "@/lib/cn";

export const THEME_STORAGE_KEY = "xvecbot-theme";
export type Theme = "dark" | "light";

export function getStoredTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  return stored === "light" ? "light" : "dark";
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  window.localStorage.setItem(THEME_STORAGE_KEY, theme);
}

/**
 * Dark is the default; light is opt-in. The choice is a UI preference, not a
 * credential, so localStorage is the right home for it.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = React.useState<Theme>("dark");

  React.useEffect(() => {
    setTheme(getStoredTheme());
  }, []);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    applyTheme(next);
  };

  const isLight = theme === "light";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isLight ? "Switch to dark mode" : "Switch to light mode"}
      aria-pressed={isLight}
      title={isLight ? "Switch to dark mode" : "Switch to light mode"}
      className={cn(
        "inline-flex h-8 w-8 items-center justify-center rounded-sm text-secondary transition-colors",
        "hover:bg-surface-hover hover:text-primary",
        "max-sm:h-11 max-sm:w-11",
        className,
      )}
    >
      {isLight ? (
        <Moon aria-hidden className="h-4 w-4" />
      ) : (
        <Sun aria-hidden className="h-4 w-4" />
      )}
    </button>
  );
}
