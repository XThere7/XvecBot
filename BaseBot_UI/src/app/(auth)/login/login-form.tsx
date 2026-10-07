"use client";

import * as React from "react";
import Link from "next/link";
import { Eye, EyeOff } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { FieldControl } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { loginSchema, type LoginValues } from "@/schemas/auth";
import { fieldErrorFor, useLogin } from "@/hooks/use-auth";

const NETWORK_ERROR = "Cannot reach the server.";

export function LoginForm({ redirectTo }: { redirectTo: string | null }) {
  const { login, pending, formError, fieldErrors } = useLogin();
  const [showPassword, setShowPassword] = React.useState(false);
  const lastAttempt = React.useRef<LoginValues | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
    // Validate on submit first, then on blur — never while the user types.
    mode: "onBlur",
  });

  const submit = handleSubmit(async (values) => {
    lastAttempt.current = values;
    await login(values.email, values.password, redirectTo);
  });

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      {formError && (
        <AlertBanner
          tone="danger"
          action={
            formError === NETWORK_ERROR && lastAttempt.current ? (
              <Button
                size="sm"
                variant="secondary"
                loading={pending}
                onClick={() => {
                  const attempt = lastAttempt.current;
                  if (attempt) void login(attempt.email, attempt.password, redirectTo);
                }}
              >
                Retry
              </Button>
            ) : undefined
          }
        >
          {formError}
        </AlertBanner>
      )}

      <FieldControl
        label="Email address"
        required
        error={errors.email?.message ?? fieldErrorFor(fieldErrors, "email")}
      >
        <Input
          type="email"
          autoComplete="email"
          placeholder="you@company.co.tz"
          disabled={pending}
          invalid={Boolean(errors.email)}
          {...register("email")}
        />
      </FieldControl>

      <FieldControl
        label="Password"
        required
        error={errors.password?.message ?? fieldErrorFor(fieldErrors, "password")}
      >
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
        Sign in
      </Button>

      {/* No backend endpoint exists for password recovery — deliberately not a form. */}
      <p className="text-xs text-tertiary">
        Forgot your password?{" "}
        <span className="text-secondary">Password recovery is coming soon.</span>
      </p>

      <p className="text-sm text-secondary">
        No account yet?{" "}
        <Link href="/register" className="text-accent-300 hover:underline">
          Create one
        </Link>
      </p>
    </form>
  );
}
