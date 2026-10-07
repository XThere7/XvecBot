import { AppShell } from "@/components/layout/app-shell";

/** Every authenticated route: sidebar + top bar + the in-memory auth guard. */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
