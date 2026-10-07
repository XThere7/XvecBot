"use client";

import * as React from "react";
import Link from "next/link";
import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import { usePathname } from "next/navigation";
import { ChevronDown, LogOut, Menu, ShieldCheck, User } from "lucide-react";
import { Breadcrumb, type Crumb } from "./breadcrumb";
import { ThemeToggle } from "./theme-toggle";
import { cn } from "@/lib/cn";
import { useLogout } from "@/hooks/use-auth";
import { useSession } from "@/stores/session";

const SEGMENT_LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  workspaces: "Workspaces",
  new: "New",
  agents: "Agents",
  conversations: "Conversations",
  account: "Account",
  security: "Session & API",
};

/** Breadcrumbs derived from the route when a page does not supply its own. */
function useRouteCrumbs(): Crumb[] {
  const pathname = usePathname();
  return React.useMemo(() => {
    const segments = pathname.split("/").filter(Boolean);
    return segments.map((segment, index) => {
      const isLast = index === segments.length - 1;
      const href = `/${segments.slice(0, index + 1).join("/")}`;
      const label =
        SEGMENT_LABELS[segment] ??
        (SEGMENT_LABELS[segment.toLowerCase()] ?? segment);
      return isLast ? { label } : { label, href };
    });
  }, [pathname]);
}

export function TopBar({
  breadcrumbs,
  actions,
  onOpenMobileNav,
}: {
  breadcrumbs?: Crumb[];
  actions?: React.ReactNode;
  onOpenMobileNav?: () => void;
}) {
  const logout = useLogout();
  const routeCrumbs = useRouteCrumbs();
  const user = useSession((state) => state.user);
  const initials = (user?.email ?? "?").slice(0, 1).toUpperCase();
  const crumbs = breadcrumbs ?? routeCrumbs;

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-subtle bg-canvas/95 px-4 backdrop-blur sm:px-6">
      <button
        type="button"
        onClick={onOpenMobileNav}
        aria-label="Open navigation"
        className="rounded-sm p-1.5 text-secondary transition-colors hover:bg-surface-hover hover:text-primary md:hidden"
      >
        <Menu aria-hidden className="h-5 w-5" />
      </button>

      {crumbs.length > 0 && <Breadcrumb items={crumbs} className="flex-1" />}

      <div className="flex shrink-0 items-center gap-1">
        <ThemeToggle />
        {actions}

        <DropdownMenuPrimitive.Root>
          <DropdownMenuPrimitive.Trigger
            aria-label="Account menu"
            className="flex items-center gap-2 rounded-sm px-1.5 py-1 transition-colors hover:bg-surface-hover"
          >
            <span
              aria-hidden
              className="flex h-7 w-7 items-center justify-center rounded-full bg-surface-raised text-xs font-medium text-secondary"
            >
              {initials}
            </span>
            <ChevronDown aria-hidden className="h-3.5 w-3.5 text-tertiary" />
          </DropdownMenuPrimitive.Trigger>
          <DropdownMenuPrimitive.Portal>
            <DropdownMenuPrimitive.Content
              align="end"
              sideOffset={4}
              className="z-50 min-w-[220px] rounded-md border border-subtle bg-surface-raised p-1 shadow-elevation-2"
            >
              <div className="px-2 py-2">
                <p className="truncate text-sm text-primary">{user?.email ?? "—"}</p>
                <p className="mt-0.5 truncate font-mono text-2xs text-tertiary">
                  {user?.userId ?? ""}
                </p>
              </div>
              <DropdownMenuPrimitive.Separator className="my-1 h-px bg-subtle" />
              <DropdownMenuPrimitive.Item
                asChild
                className="flex cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-2 text-sm text-primary outline-none data-[highlighted]:bg-surface-hover"
              >
                <Link href="/account">
                  <User aria-hidden className="h-4 w-4" />
                  Account
                </Link>
              </DropdownMenuPrimitive.Item>
              <DropdownMenuPrimitive.Item
                asChild
                className="flex cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-2 text-sm text-primary outline-none data-[highlighted]:bg-surface-hover"
              >
                <Link href="/account/security">
                  <ShieldCheck aria-hidden className="h-4 w-4" />
                  Session &amp; API
                </Link>
              </DropdownMenuPrimitive.Item>
              <DropdownMenuPrimitive.Separator className="my-1 h-px bg-subtle" />
              <DropdownMenuPrimitive.Item
                onSelect={logout}
                className={cn(
                  "flex cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-2 text-sm",
                  "text-danger-400 outline-none data-[highlighted]:bg-danger-500/10",
                )}
              >
                <LogOut aria-hidden className="h-4 w-4" />
                Log out
              </DropdownMenuPrimitive.Item>
            </DropdownMenuPrimitive.Content>
          </DropdownMenuPrimitive.Portal>
        </DropdownMenuPrimitive.Root>
      </div>
    </header>
  );
}