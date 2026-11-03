"use client";

import * as React from "react";
import Link from "next/link";
import { MailCheck } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { FieldControl } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { MAX_EMAIL_LENGTH } from "@/lib/constants";
import { useForgotPassword } from "@/hooks/use-password-reset";
import { z } from "zod";

const forgotSchema = z.object({
  email: z
    .string()
    .min(1, "Enter your email address.")
    .max(MAX_EMAIL_LENGTH, "That email address is too long.")
    .email("Enter a valid email address."),
});

type ForgotValues = z.infer<typeof forgotSchema>;

/**
 * The confirmation text must be identical for known and unknown addresses —
 * the server does not reveal whether an account exists, and neither may this
 * page.
 */
const CONFIRMATION =
  "If an account exists with this email address, you'll receive instructions to reset your password.";

export function ForgotPasswordForm() {
  const { submit, pending, sent, rateLimited, formError } = useForgotPassword();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ForgotValues>({
    resolver: zodResolver(forgotSchema),
    defaultValues: { email: "" },
    mode: "onBlur",
  });

  const onSubmit = handleSubmit(async (values) => {
    await submit(values.email);
  });

  if (sent) {
    return (
      <div role="status" className="flex flex-col gap-4">
        <div className="flex items-start gap-3 rounded-sm border border-subtle bg-surface p-4">
          <MailCheck aria-hidden className="mt-0.5 h-5 w-5 shrink-0 text-accent-300" />
          <p className="text-sm leading-5 text-secondary">{CONFIRMATION}</p>
        </div>
        {rateLimited && (
          <p className="text-xs text-tertiary">
            Please wait a while before requesting another link.
          </p>
        )}
        <p className="text-sm text-secondary">
          <Link href="/login" className="text-accent-300 hover:underline">
            Back to sign in
          </Link>
        </p>
      </div>
    );
  }

  return (
    <form method="post" onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {formError && <AlertBanner tone="danger">{formError}</AlertBanner>}

      <FieldControl
        label="Email address"
        required
        error={errors.email?.message}
        hint="We'll send the reset link to this address."
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

      <Button type="submit" variant="primary" size="lg" fullWidth loading={pending}>
        Send reset link
      </Button>

      <p className="text-sm text-secondary">
        Remembered it?{" "}
        <Link href="/login" className="text-accent-300 hover:underline">
          Sign in
        </Link>
      </p>

      <p className="text-xs text-tertiary">
        Need help?{" "}
        <Link href="/docs/help/faq" className="text-accent-300 hover:underline">
          Read the password reset guide
        </Link>
      </p>
    </form>
  );
}
