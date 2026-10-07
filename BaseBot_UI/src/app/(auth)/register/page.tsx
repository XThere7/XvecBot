import { RegisterForm } from "./register-form";
import { AuthShell } from "@/components/layout/auth-shell";

export const metadata = {
  title: "Create your account",
};

export default function RegisterPage() {
  return (
    <AuthShell
      title="Create your account"
      subtitle="Three steps to a live chat widget on your website. No card, no AI expertise."
    >
      <RegisterForm />
    </AuthShell>
  );
}
