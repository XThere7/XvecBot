"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
import {
  LayoutDashboard,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  User,
  X,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { APP_NAME } from "@/lib/constants";
import { Tooltip } from "@/components/ui/tooltip";
import { WorkspaceSwitcher } from "./workspace-switcher";
import { useLogout } from "@/hooks/use-auth";
import { useSession } from "@/stores/session";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/workspaces", label: "Workspaces", icon: Settings },
  { href: "/account", label: "Account", icon: User },
];

export type SidebarNavProps = {
  collapsed: boolean;
  onToggleCollapse: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
};

export function SidebarNav({
  collapsed,
  onToggleCollapse,
  mobileOpen,
  onCloseMobile,
}: SidebarNavProps) {
  const pathname = usePathname();
  const reduceMotion = useReducedMotion();
  const logout = useLogout();
  const email = useSession((state) => state.user?.email);

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);

  const items = NAV_ITEMS.map((item) => {
    const active = isActive(item.href);
    const Icon = item.icon;
    const link = (
      <Link
        key={item.href}
        href={item.href}
        onClick={onCloseMobile}
        aria-current={active ? "page" : undefined}
        className={cn(
          "group relative flex h-9 items-center gap-2.5 rounded-sm px-2.5 text-sm transition-colors duration-150",
          active
            ? "bg-accent-tint text-primary"
            : "text-secondary hover:bg-surface-hover hover:text-primary",
          collapsed && "justify-center px-0",
        )}
      >
        {active && (
          <span
            aria-hidden
            className="absolute left-0 h-4 w-0.5 rounded-full bg-accent-500"
          />
        )}
        <Icon aria-hidden className="h-4 w-4 shrink-0" />
        {!collapsed && <span className="truncate">{item.label}</span>}
      </Link>
    );

    return collapsed ? (
      <Tooltip key={item.href} content={item.label} side="right">
        {link}
      </Tooltip>
    ) : (
      link
    );
  });

  return (
    <>
      {mobileOpen && (
        <div
          role="presentation"
          onClick={onCloseMobile}
          className="fixed inset-0 z-40 bg-black/60 md:hidden"
        />
      )}

      <motion.aside
        initial={false}
        animate={{ width: collapsed ? 64 : 256 }}
        transition={
          reduceMotion
            ? { duration: 0 }
            : { type: "spring", stiffness: 300, damping: 30 }
        }
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex shrink-0 flex-col border-r border-subtle bg-surface",
          "md:relative md:z-0 md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          "w-[256px] max-md:w-[80vw]",
        )}
        aria-label="Primary"
      >
        <div className="flex items-center justify-between gap-2 px-3 py-3">
          <Link href="/dashboard" className="flex min-w-0 items-center gap-2.5">
            <span
              aria-hidden
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-sm bg-accent-500 text-sm font-semibold text-inverse"
            >
              X
            </span>
            {!collapsed && (
              <span className="truncate text-base font-semibold text-primary">
                {APP_NAME}
              </span>
            )}
          </Link>
          <button
            type="button"
            onClick={onCloseMobile}
            aria-label="Close navigation"
            className="rounded-sm p-1.5 text-tertiary transition-colors hover:bg-surface-hover hover:text-primary md:hidden"
          >
            <X aria-hidden className="h-4 w-4" />
          </button>
        </div>

        <div className={cn("px-3 pb-3", collapsed && "px-2")}>
          <WorkspaceSwitcher collapsed={collapsed} />
        </div>

        <nav className="flex flex-1 flex-col gap-0.5 px-3">
          {collapsed && <span className="sr-only">Navigation</span>}
          {items}
        </nav>

        <div className="border-t border-subtle p-3">
          {!collapsed && (
            <div className="mb-2 min-w-0 px-1">
              <p className="truncate text-xs text-tertiary">{email ?? "Signed in"}</p>
            </div>
          )}
          <div className={cn("flex flex-col gap-0.5", collapsed && "items-center")}>
            <Tooltip content="Log out" side="right">
              <button
                type="button"
                onClick={logout}
                className={cn(
                  "flex h-9 w-full items-center gap-2.5 rounded-sm px-2.5 text-sm text-secondary transition-colors hover:bg-surface-hover hover:text-primary",
                  collapsed && "w-9 justify-center px-0",
                )}
              >
                <LogOut aria-hidden className="h-4 w-4 shrink-0" />
                {!collapsed && "Log out"}
              </button>
            </Tooltip>
            <button
              type="button"
              onClick={onToggleCollapse}
              aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
              className={cn(
                "hidden h-9 w-full items-center gap-2.5 rounded-sm px-2.5 text-sm text-tertiary transition-colors hover:bg-surface-hover hover:text-primary md:flex",
                collapsed && "w-9 justify-center px-0",
              )}
            >
              {collapsed ? (
                <PanelLeftOpen aria-hidden className="h-4 w-4 shrink-0" />
              ) : (
                <>
                  <PanelLeftClose aria-hidden className="h-4 w-4 shrink-0" />
                  Collapse
                </>
              )}
            </button>
          </div>
        </div>
      </motion.aside>
    </>
  );
}