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
import { MIN_PASSWORD_LENGTH } from "@/lib/constants";
import { registerSchema, type RegisterValues } from "@/schemas/auth";
import { fieldErrorFor, useRegister } from "@/hooks/use-auth";

const NETWORK_ERROR = "Cannot reach the server.";

export function RegisterForm() {
  const { register: submitRegister, pending, formError, fieldErrors } = useRegister();
  const [showPassword, setShowPassword] = React.useState(false);
  const lastAttempt = React.useRef<{ email: string; password: string } | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { email: "", password: "", acceptTerms: false as never },
    mode: "onBlur",
  });

  const submit = handleSubmit(async (values) => {
    lastAttempt.current = { email: values.email, password: values.password };
    await submitRegister(values.email, values.password);
  });

  const duplicateEmail =
    fieldErrors.length === 0 && formError?.toLowerCase().includes("already registered");

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      {formError && !duplicateEmail && (
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
                  if (attempt) void submitRegister(attempt.email, attempt.password);
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
        error={
          duplicateEmail
            ? (formError ?? undefined)
            : (errors.email?.message ?? fieldErrorFor(fieldErrors, "email"))
        }
        hint={
          duplicateEmail ? (
            <span>
              Already have an account?{" "}
              <Link href="/login" className="text-accent-300 hover:underline">
                Log in instead?
              </Link>
            </span>
          ) : undefined
        }
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
        hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
      >
        <Input
          type={showPassword ? "text" : "password"}
          autoComplete="new-password"
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

      <div className="flex flex-col gap-2">
        <label className="flex items-start gap-2.5 text-sm text-secondary">
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4 shrink-0 rounded-sm border border-strong bg-inset accent-[var(--color-accent-500)]"
            {...register("acceptTerms")}
          />
          <span>
            I understand this dashboard stores my session in memory only, so a
            browser sign-out ends it.
          </span>
        </label>
        {errors.acceptTerms && (
          <p className="text-xs text-danger-400">{errors.acceptTerms.message}</p>
        )}
      </div>

      <Button type="submit" variant="primary" size="lg" fullWidth loading={pending}>
        Create account
      </Button>

      <p className="text-sm text-secondary">
        Already registered?{" "}
        <Link href="/login" className="text-accent-300 hover:underline">
          Sign in
        </Link>
      </p>
    </form>
  );
}
