"use client";

import * as React from "react";
import Link from "next/link";
import { CheckCircle2, Eye, EyeOff, ShieldAlert } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { FieldControl } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { MIN_PASSWORD_LENGTH } from "@/lib/constants";
import { fieldErrorFor } from "@/hooks/use-auth";
import { useResetPassword, RESET_LINK_INVALID } from "@/hooks/use-password-reset";
import { z } from "zod";

const resetSchema = z
  .object({
    newPassword: z
      .string()
      .min(MIN_PASSWORD_LENGTH, `Use at least ${MIN_PASSWORD_LENGTH} characters.`),
    confirmPassword: z.string().min(1, "Confirm your new password."),
  })
  .refine((values) => values.newPassword === values.confirmPassword, {
    path: ["confirmPassword"],
    message: "Passwords do not match.",
  });

type ResetValues = z.infer<typeof resetSchema>;

export function ResetPasswordForm({ token }: { token: string | null }) {
  const { status, pending, formError, fieldErrors, submit } = useResetPassword(token);
  const [showNew, setShowNew] = React.useState(false);
  const [showConfirm, setShowConfirm] = React.useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ResetValues>({
    resolver: zodResolver(resetSchema),
    defaultValues: { newPassword: "", confirmPassword: "" },
    mode: "onBlur",
  });

  if (status === "loading") {
    return (
      <p className="text-sm text-secondary" role="status">
        Checking your reset link…
      </p>
    );
  }

  if (status === "invalid") {
    return (
      <div role="alert" className="flex flex-col gap-4">
        <div className="flex items-start gap-3 rounded-sm border border-subtle bg-surface p-4">
          <ShieldAlert aria-hidden className="mt-0.5 h-5 w-5 shrink-0 text-danger-400" />
          <p className="text-sm leading-5 text-secondary">{RESET_LINK_INVALID}</p>
        </div>
        <Button asChild variant="primary" size="lg" fullWidth>
          <Link href="/forgot-password">Request a new link</Link>
        </Button>
        <p className="text-sm text-secondary">
          <Link href="/login" className="text-accent-300 hover:underline">
            Back to sign in
          </Link>
        </p>
      </div>
    );
  }

  if (status === "success") {
    return (
      <div role="status" className="flex flex-col gap-4">
        <div className="flex items-start gap-3 rounded-sm border border-subtle bg-surface p-4">
          <CheckCircle2 aria-hidden className="mt-0.5 h-5 w-5 shrink-0 text-accent-300" />
          <p className="text-sm leading-5 text-secondary">
            Your password has been reset. You can now sign in with your new
            password.
          </p>
        </div>
        <Button asChild variant="primary" size="lg" fullWidth>
          <Link href="/login">Go to sign in</Link>
        </Button>
      </div>
    );
  }

  const submitForm = handleSubmit(async (values) => {
    await submit(values.newPassword, values.confirmPassword);
  });

  return (
    <form method="post" onSubmit={submitForm} noValidate className="flex flex-col gap-4">
      {formError && <AlertBanner tone="danger">{formError}</AlertBanner>}

      <FieldControl
        label="New password"
        required
        error={errors.newPassword?.message ?? fieldErrorFor(fieldErrors, "new_password")}
        hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
      >
        <Input
          type={showNew ? "text" : "password"}
          autoComplete="new-password"
          placeholder="••••••••"
          disabled={pending}
          invalid={Boolean(errors.newPassword)}
          endAdornment={
            <button
              type="button"
              onClick={() => setShowNew((value) => !value)}
              aria-label={showNew ? "Hide new password" : "Show new password"}
              className="rounded-sm p-1 text-tertiary transition-colors hover:text-primary"
            >
              {showNew ? (
                <EyeOff aria-hidden className="h-4 w-4" />
              ) : (
                <Eye aria-hidden className="h-4 w-4" />
              )}
            </button>
          }
          {...register("newPassword")}
        />
      </FieldControl>

      <FieldControl
        label="Confirm new password"
        required
        error={
          errors.confirmPassword?.message ??
          fieldErrorFor(fieldErrors, "confirm_password")
        }
      >
        <Input
          type={showConfirm ? "text" : "password"}
          autoComplete="new-password"
          placeholder="••••••••"
          disabled={pending}
          invalid={Boolean(errors.confirmPassword)}
          endAdornment={
            <button
              type="button"
              onClick={() => setShowConfirm((value) => !value)}
              aria-label={showConfirm ? "Hide confirmed password" : "Show confirmed password"}
              className="rounded-sm p-1 text-tertiary transition-colors hover:text-primary"
            >
              {showConfirm ? (
                <EyeOff aria-hidden className="h-4 w-4" />
              ) : (
                <Eye aria-hidden className="h-4 w-4" />
              )}
            </button>
          }
          {...register("confirmPassword")}
        />
      </FieldControl>

      <Button type="submit" variant="primary" size="lg" fullWidth loading={pending}>
        Reset password
      </Button>
    </form>
  );
}
