"use client";

import * as React from "react";
import { Moon, Sun } from "lucide-react";

const STORAGE_KEY = "botbase-docs-theme";

type Theme = "light" | "dark";

function storedTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

/**
 * Docs intentionally use a separate theme key from the dashboard. A first-time
 * visitor gets their operating-system preference; an explicit choice is kept
 * only for the docs surface.
 */
export function DocsThemeToggle() {
  const [theme, setTheme] = React.useState<Theme>("dark");

  React.useEffect(() => {
    const stored = storedTheme();
    if (stored) {
      document.documentElement.dataset.docsTheme = stored;
      setTheme(stored);
      return;
    }

    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = () => setTheme(media.matches ? "dark" : "light");
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.docsTheme = next;
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // A private-mode storage denial should not block the visual toggle.
    }
  };

  const isDark = theme === "dark";

  return (
    <button
      type="button"
      className="docs-icon-button"
      onClick={toggle}
      aria-label={isDark ? "Switch docs to light mode" : "Switch docs to dark mode"}
      aria-pressed={isDark}
      data-docs-theme-toggle
    >
      {isDark ? (
        <Sun aria-hidden className="h-4 w-4" />
      ) : (
        <Moon aria-hidden className="h-4 w-4" />
      )}
    </button>
  );
}
