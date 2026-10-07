"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowRight, Menu, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { LANDING_NAV, PRODUCT_NAME } from "./landing-nav";

/**
 * Phase 1 — the sticky global header. Minimal three-item primary nav that
 * mirrors the in-app sidebar, plus Sign in / Get started actions. Gains a
 * border + blur as soon as the page scrolls.
 */
export function LandingHeader() {
  const pathname = usePathname();
  const [scrolled, setScrolled] = React.useState(false);
  const [open, setOpen] = React.useState(false);

  React.useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  React.useEffect(() => {
    setOpen(false);
  }, [pathname]);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 transition-colors duration-200",
        scrolled || open
          ? "border-b border-subtle bg-canvas/90 backdrop-blur-md"
          : "border-b border-transparent bg-transparent",
      )}
    >
      <div className="mx-auto flex h-16 w-full max-w-[1200px] items-center justify-between gap-4 px-4 sm:px-6">
        <Link href="/" className="flex shrink-0 items-center gap-2.5" aria-label="BotBase home">
          <span
            aria-hidden
            className="flex h-8 w-8 items-center justify-center rounded-md bg-accent-500 text-base font-semibold text-inverse"
          >
            B
          </span>
          <span className="text-lg font-semibold tracking-tight text-primary">
            {PRODUCT_NAME}
          </span>
        </Link>

        {/* Desktop primary nav — the same three destinations as the app sidebar. */}
        <nav aria-label="Primary" className="hidden items-center gap-1 md:flex">
          {LANDING_NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-sm px-3 py-2 text-sm text-secondary transition-colors hover:bg-surface-hover hover:text-primary"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="hidden items-center gap-1 md:flex">
          <ThemeToggle />
          <Button asChild variant="ghost">
            <Link href="/login">Sign in</Link>
          </Button>
          <Button asChild variant="primary" iconRight={<ArrowRight aria-hidden className="h-4 w-4" />}>
            <Link href="/register">Get started</Link>
          </Button>
        </div>

        <div className="flex items-center gap-1 md:hidden">
          <ThemeToggle />
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            aria-label={open ? "Close menu" : "Open menu"}
            className="inline-flex h-11 w-11 items-center justify-center rounded-sm text-secondary transition-colors hover:bg-surface-hover hover:text-primary"
          >
            {open ? <X aria-hidden className="h-5 w-5" /> : <Menu aria-hidden className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {open && (
        <nav aria-label="Mobile" className="border-t border-subtle bg-canvas px-4 pb-6 pt-2 md:hidden">
          <ul className="flex flex-col">
            {LANDING_NAV.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className="block rounded-sm px-2 py-3 text-base text-primary transition-colors hover:bg-surface-hover"
                >
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex flex-col gap-2">
            <Button asChild variant="primary" size="lg" fullWidth>
              <Link href="/register">Get started</Link>
            </Button>
            <Button asChild variant="secondary" size="lg" fullWidth>
              <Link href="/login">Sign in</Link>
            </Button>
          </div>
        </nav>
      )}
    </header>
  );
}
