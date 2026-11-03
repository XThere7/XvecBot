import { ResetPasswordForm } from "./reset-password-form";
import { AuthShell } from "@/components/layout/auth-shell";
import { APP_NAME } from "@/lib/constants";

export const metadata = {
  title: "Reset password",
  // The reset token rides in the query string: never send it to third parties
  // (analytics embeds, image hosts) via the Referer header.
  referrer: "no-referrer",
};

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const query = await searchParams;
  const token = typeof query.token === "string" ? query.token : null;

  return (
    <AuthShell
      title="Reset password"
      subtitle={`Choose a new password for your ${APP_NAME} account.`}
    >
      <ResetPasswordForm token={token} />
    </AuthShell>
  );
}
