import { ForgotPasswordForm } from "./forgot-password-form";
import { AuthShell } from "@/components/layout/auth-shell";
import { APP_NAME } from "@/lib/constants";

export const metadata = {
  title: "Forgot password",
};

export default function ForgotPasswordPage() {
  return (
    <AuthShell
      title="Forgot password"
      subtitle={`We'll email you a secure link to reset your ${APP_NAME} password.`}
    >
      <ForgotPasswordForm />
    </AuthShell>
  );
}
