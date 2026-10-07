"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
import { SidebarNav } from "./sidebar-nav";
import { TopBar } from "./top-bar";
import { useAuthGuard, useUnauthorizedHandler } from "@/hooks/use-auth";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const reduceMotion = useReducedMotion();
  const { authenticated } = useAuthGuard();
  useUnauthorizedHandler();

  const [collapsed, setCollapsed] = React.useState(false);
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [isDesktop, setIsDesktop] = React.useState(true);

  React.useEffect(() => {
    // Desktop ≥1280 keeps the full sidebar; tablet collapses to a 64px rail.
    // Below 768px the sidebar is a drawer and is always full width.
    const desktop = window.matchMedia("(min-width: 1280px)");
    const mobile = window.matchMedia("(max-width: 767px)");
    const sync = () => {
      setIsDesktop(!mobile.matches);
      setCollapsed(!desktop.matches);
    };
    sync();
    const onChange = () => sync();
    desktop.addEventListener("change", onChange);
    mobile.addEventListener("change", onChange);
    return () => {
      desktop.removeEventListener("change", onChange);
      mobile.removeEventListener("change", onChange);
    };
  }, []);

  React.useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  // Render nothing until the in-memory auth check resolves — no flash of a
  // protected page, and no flash of the login page either.
  if (!authenticated) {
    return (
      <div
        role="status"
        aria-label="Checking your session"
        className="flex min-h-dvh items-center justify-center text-sm text-tertiary"
      >
        Checking your session…
      </div>
    );
  }

  return (
    <div className="flex min-h-dvh bg-canvas">
      <SidebarNav
        collapsed={isDesktop && collapsed}
        onToggleCollapse={() => setCollapsed((value) => !value)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onOpenMobileNav={() => setMobileOpen(true)} />
        <motion.main
          key={pathname}
          initial={reduceMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.12, ease: "easeOut" }}
          className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-6 sm:py-8"
        >
          {children}
        </motion.main>
      </div>
    </div>
  );
}