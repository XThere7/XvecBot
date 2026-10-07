import { LoginForm } from "./login-form";
import { AuthShell } from "@/components/layout/auth-shell";
import { normaliseRedirectTarget } from "@/lib/routes";
import { APP_NAME } from "@/lib/constants";

export const metadata = {
  title: "Sign in",
};

/**
 * A server component so the form is server-rendered: the `redirect` target
 * arrives as a prop instead of through `useSearchParams`, which would suspend
 * the page during prerendering.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const query = await searchParams;
  const redirectTo = normaliseRedirectTarget(
    typeof query.redirect === "string" ? query.redirect : null,
  );

  return (
    <AuthShell
      title="Sign in"
      subtitle={`Sign in to manage your ${APP_NAME} knowledge base, agents and widgets.`}
    >
      <LoginForm redirectTo={redirectTo} />
    </AuthShell>
  );
}