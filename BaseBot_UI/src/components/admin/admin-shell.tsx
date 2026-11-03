"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { RefreshCw, Shield } from "lucide-react";
import { cn } from "@/lib/cn";
import {
  ADMIN_LOGIN,
  ADMIN_SECTIONS,
  can,
  isAdmin,
  useAdminMe,
} from "@/lib/admin";
import { auth } from "@/lib/auth";

/** Admin area shell: server-independent client gate + permission sidebar. */
export function AdminShell({ children }: { children: React.ReactNode }) {
  const { me, loading, reload } = useAdminMe();
  const router = useRouter();
  const pathname = usePathname();

  React.useEffect(() => {
    if (!loading && !isAdmin(me)) {
      // No admin session → the dedicated admin sign-in; a signed-in customer
      // → their own dashboard.
      router.replace(me ? "/dashboard" : ADMIN_LOGIN);
    }
  }, [loading, me, router]);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-sm text-secondary">
        Loading admin area…
      </div>
    );
  }
  if (!isAdmin(me)) return null;

  const sections = ADMIN_SECTIONS.filter(
    (section) =>
      can(me, section.permission) &&
      (!section.superadminOnly || me?.role === "superadmin"),
  );

  return (
    <div className="flex min-h-[calc(100vh-56px)]">
      <aside className="hidden w-56 shrink-0 flex-col gap-1 border-r border-subtle p-3 md:flex">
        <div className="flex items-center gap-2 px-2 pb-2 text-xs font-semibold uppercase tracking-wide text-tertiary">
          <Shield aria-hidden className="h-3.5 w-3.5" />
          {me?.role === "superadmin" ? "Master admin" : "Admin"}
        </div>
        {sections.map((section) => {
          const active =
            pathname === section.href || pathname.startsWith(`${section.href}/`);
          return (
            <Link
              key={section.href}
              href={section.href}
              className={cn(
                "rounded-sm px-2.5 py-2 text-sm transition-colors",
                active
                  ? "bg-accent-tint text-primary"
                  : "text-secondary hover:bg-surface-hover hover:text-primary",
              )}
            >
              {section.label}
            </Link>
          );
        })}
      </aside>

      <main className="min-w-0 flex-1 p-4 sm:p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div className="text-xs text-tertiary">
            Signed in as <span className="text-secondary">{me?.email}</span>
          </div>
          <div className="flex flex-wrap items-center gap-2 md:hidden">
            {sections.map((section) => (
              <Link
                key={section.href}
                href={section.href}
                className="rounded-sm border border-subtle px-2 py-1 text-xs text-secondary"
              >
                {section.label}
              </Link>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={reload}
              className="inline-flex items-center gap-1.5 rounded-sm px-2 py-1 text-xs text-tertiary transition-colors hover:text-primary"
            >
              <RefreshCw aria-hidden className="h-3 w-3" />
              Reload session
            </button>
            <button
              type="button"
              onClick={() => {
                auth.clear();
                router.replace(ADMIN_LOGIN);
              }}
              className="inline-flex items-center gap-1.5 rounded-sm px-2 py-1 text-xs text-tertiary transition-colors hover:text-primary"
            >
              Sign out
            </button>
          </div>
        </div>
        {children}
      </main>
    </div>
  );
}
