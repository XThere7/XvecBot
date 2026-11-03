import { AdminLoginForm } from "./admin-login-form";

export const metadata = {
  title: "Admin sign in",
  robots: { index: false, follow: false },
};

/** Dedicated, centered admin sign-in — intentionally different from the
 * customer login (no password recovery, no registration links). */
export default function AdminLoginPage() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-canvas px-4 py-10">
      <div className="w-full max-w-[400px]">
        <AdminLoginForm />
      </div>
    </div>
  );
}
