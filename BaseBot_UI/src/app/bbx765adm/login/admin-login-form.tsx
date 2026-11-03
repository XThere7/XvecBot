"use client";

import * as React from "react";
import Link from "next/link";
import { Eye, EyeOff, KeyRound, ShieldCheck } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { FieldControl } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { APP_NAME } from "@/lib/constants";
import { useAdminLogin } from "@/lib/admin";
import { z } from "zod";

const loginSchema = z.object({
  email: z.string().min(1, "Enter your email address.").email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});

type LoginValues = z.infer<typeof loginSchema>;

/**
 * Admin sign-in form. Deliberately not the customer form: no forgot-password
 * link (admins are reset by the master admin) and no registration link.
 */
export function AdminLoginForm() {
  const { pending, formError, totpToken, login, completeTotp } = useAdminLogin();
  const [showPassword, setShowPassword] = React.useState(false);
  const [code, setCode] = React.useState("");

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
    mode: "onBlur",
  });

  const submit = handleSubmit(async (values) => {
    await login(values.email, values.password);
  });

  return (
    <div className="rounded-lg border border-subtle bg-surface p-8 shadow-[0_18px_44px_rgb(0_0_0/0.12)]">
      <div className="flex flex-col items-center text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-accent-tint">
          <ShieldCheck aria-hidden className="h-6 w-6 text-accent-300" />
        </span>
        <h1 className="mt-4 text-xl text-primary">Admin sign in</h1>
        <p className="mt-1 text-sm leading-5 text-secondary">
          Restricted area for {APP_NAME} administrators. Customer accounts
          cannot enter here.
        </p>
      </div>

      <div className="mt-6">
        {formError && (
          <div className="mb-4">
            <AlertBanner tone="danger">{formError}</AlertBanner>
          </div>
        )}

        {totpToken ? (
          <form
            method="post"
            noValidate
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              void completeTotp(code);
            }}
          >
            <p className="text-sm text-secondary">
              Two-factor authentication is enabled for this account. Enter the
              6-digit code from your authenticator (or a recovery code).
            </p>
            <FieldControl label="Verification code" required>
              <Input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="••••••"
                value={code}
                disabled={pending}
                onChange={(event) => setCode(event.target.value)}
              />
            </FieldControl>
            <Button type="submit" variant="primary" size="lg" fullWidth loading={pending}>
              Verify and sign in
            </Button>
          </form>
        ) : (
          <form method="post" onSubmit={submit} noValidate className="flex flex-col gap-4">
            <FieldControl label="Admin email" required error={errors.email?.message}>
              <Input
                type="email"
                autoComplete="email"
                placeholder="admin@company.com"
                disabled={pending}
                invalid={Boolean(errors.email)}
                {...register("email")}
              />
            </FieldControl>

            <FieldControl label="Password" required error={errors.password?.message}>
              <Input
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                placeholder="••••••••"
                disabled={pending}
                invalid={Boolean(errors.password)}
                endAdornment={
                  <button
                    type="button"
                    onClick={() => setShowPassword((value) => !value)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    className="rounded-sm p-1 text-tertiary transition-colors hover:text-primary"
                  >
                    {showPassword ? (
                      <EyeOff aria-hidden className="h-4 w-4" />
                    ) : (
                      <Eye aria-hidden className="h-4 w-4" />
                    )}
                  </button>
                }
                {...register("password")}
              />
            </FieldControl>

            <Button type="submit" variant="primary" size="lg" fullWidth loading={pending}>
              Sign in to admin
            </Button>
          </form>
        )}

        <p className="mt-5 flex items-center justify-center gap-1.5 text-xs text-tertiary">
          <KeyRound aria-hidden className="h-3 w-3" />
          <Link href="/" className="text-accent-300 hover:underline">
            Back to {APP_NAME}
          </Link>
        </p>
      </div>
    </div>
  );
}
