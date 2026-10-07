import Link from "next/link";
import { LANDING_NAV } from "./landing-nav";

/**
 * Phase 1 — minimal footer. Product links reuse the same three destinations
 * as the header so the information architecture stays one idea deep.
 */
export function LandingFooter() {
  return (
    <footer className="border-t border-subtle">
      <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-8 px-4 py-12 sm:px-6 md:flex-row md:items-start md:justify-between">
        <div className="max-w-xs">
          <div className="flex items-center gap-2.5">
            <span
              aria-hidden
              className="flex h-8 w-8 items-center justify-center rounded-md bg-accent-500 text-base font-semibold text-inverse"
            >
              B
            </span>
            <span className="text-lg font-semibold tracking-tight text-primary">
              BotBase
            </span>
          </div>
          <p className="mt-3 text-sm leading-5 text-secondary">
            Turn your documents into an embeddable AI chat widget. Built for
            businesses that want answers from their own content.
          </p>
        </div>

        <nav aria-label="Footer" className="grid grid-cols-2 gap-8 sm:grid-cols-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-widest text-tertiary">
              Product
            </p>
            <ul className="mt-3 flex flex-col gap-2">
              {LANDING_NAV.map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className="text-sm text-secondary transition-colors hover:text-primary"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-widest text-tertiary">
              Get started
            </p>
            <ul className="mt-3 flex flex-col gap-2">
              <li>
                <Link href="/register" className="text-sm text-secondary transition-colors hover:text-primary">
                  Create account
                </Link>
              </li>
              <li>
                <Link href="/login" className="text-sm text-secondary transition-colors hover:text-primary">
                  Sign in
                </Link>
              </li>
              <li>
                <Link href="/#how-it-works" className="text-sm text-secondary transition-colors hover:text-primary">
                  How it works
                </Link>
              </li>
            </ul>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-widest text-tertiary">
              Company
            </p>
            <ul className="mt-3 flex flex-col gap-2">
              <li>
                <Link href="/account" className="text-sm text-secondary transition-colors hover:text-primary">
                  Contact
                </Link>
              </li>
            </ul>
          </div>
        </nav>
      </div>

      <div className="border-t border-subtle">
        <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-2 px-4 py-5 text-xs text-tertiary sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>© {new Date().getFullYear()} BotBase. All rights reserved.</p>
          <p>Dashboards stay in dark or light — your choice, top-right.</p>
        </div>
      </div>
    </footer>
  );
}
