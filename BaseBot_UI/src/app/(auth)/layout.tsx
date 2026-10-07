/**
 * Auth routes render their own AuthShell (split layout, brand panel on the
 * right) and never get the sidebar or top bar.
 */
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}