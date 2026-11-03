"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ArrowUpRight,
  ChevronRight,
  Menu,
  Search,
  X,
} from "lucide-react";
import { BotBaseMark } from "@/components/brand/botbase-mark";
import { DocsSearch } from "./docs-search";
import { DocsThemeToggle } from "./docs-theme-toggle";
import { cn } from "@/lib/cn";

export type DocsNavItem = { href: string; title: string };
export type DocsNavGroup = { name: string; pages: DocsNavItem[] };

function DocsNav({
  groups,
  onNavigate,
}: {
  groups: DocsNavGroup[];
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const [closed, setClosed] = React.useState<Record<string, boolean>>({});

  return (
    <nav aria-label="Documentation" className="docs-sidebar-inner">
      {groups.map((group) => {
        const isClosed = Boolean(closed[group.name]);
        return (
          <div className="docs-nav-group" key={group.name}>
            <button
              type="button"
              className="docs-nav-group-title"
              aria-expanded={!isClosed}
              onClick={() =>
                setClosed((current) => ({
                  ...current,
                  [group.name]: !current[group.name],
                }))
              }
            >
              <ChevronRight
                aria-hidden
                className={cn(
                  "h-3 w-3 transition-transform",
                  !isClosed && "rotate-90",
                )}
              />
              {group.name}
            </button>
            {!isClosed && (
              <ul className="docs-nav-list">
                {group.pages.map((page) => (
                  <li key={page.href}>
                    <Link
                      href={page.href}
                      onClick={onNavigate}
                      aria-current={pathname === page.href ? "page" : undefined}
                      className="docs-nav-link"
                    >
                      {page.title}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </nav>
  );
}

export function DocsShell({
  groups,
  children,
}: {
  groups: DocsNavGroup[];
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [searchOpen, setSearchOpen] = React.useState(false);

  React.useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  React.useEffect(() => {
    if (!drawerOpen && !searchOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [drawerOpen, searchOpen]);

  return (
    <div className="docs-root">
      <a href="#docs-content" className="docs-skip">
        Skip to content
      </a>

      <header className="docs-topbar">
        <div className="docs-topbar-inner">
          <button
            type="button"
            className="docs-icon-button lg:hidden"
            aria-label="Open documentation navigation"
            aria-expanded={drawerOpen}
            onClick={() => setDrawerOpen(true)}
          >
            <Menu aria-hidden className="h-5 w-5" />
          </button>

          <Link href="/docs" className="docs-brand" aria-label="BotBase documentation home">
            <BotBaseMark className="h-7 w-7" />
            <span>BotBase</span>
            <span className="docs-brand-badge">Docs</span>
          </Link>

          <div className="docs-top-actions">
            <button
              type="button"
              className="docs-search-trigger"
              aria-label="Search documentation"
              onClick={() => setSearchOpen(true)}
            >
              <Search aria-hidden className="h-4 w-4" />
              <span>Search docs</span>
              <kbd>Ctrl K</kbd>
            </button>

            <Link href="/pricing" className="docs-top-link">
              Pricing
            </Link>
            <Link href="/dashboard" className="docs-top-link">
              Dashboard
            </Link>
            <Link href="/register" className="docs-top-cta">
              Start free
              <ArrowUpRight aria-hidden className="h-3.5 w-3.5" />
            </Link>
            <DocsThemeToggle />
          </div>
        </div>
      </header>

      <div className="docs-shell">
        <aside className="docs-sidebar" aria-label="Documentation sidebar">
          <DocsNav groups={groups} />
        </aside>

        <main id="docs-content" className="docs-main-wrap">
          {children}
        </main>
      </div>

      {drawerOpen && (
        <>
          <div
            className="docs-sidebar-drawer-backdrop"
            role="presentation"
            onClick={() => setDrawerOpen(false)}
          />
          <aside className="docs-sidebar-drawer" aria-label="Documentation navigation">
            <div className="docs-drawer-head">
              <Link
                href="/docs"
                className="docs-brand"
                onClick={() => setDrawerOpen(false)}
              >
                <BotBaseMark className="h-7 w-7" />
                <span>BotBase Docs</span>
              </Link>
              <button
                type="button"
                className="docs-icon-button"
                aria-label="Close documentation navigation"
                onClick={() => setDrawerOpen(false)}
              >
                <X aria-hidden className="h-5 w-5" />
              </button>
            </div>
            <DocsNav groups={groups} onNavigate={() => setDrawerOpen(false)} />
          </aside>
        </>
      )}

      <DocsSearch open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}
