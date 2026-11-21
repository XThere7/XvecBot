"use client";

import * as React from "react";
import { ActionFieldForm } from "@/components/actions/action-field-form";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { usePublicForm, useSubmitPublicForm } from "@/hooks/use-engagement";

export function PublicFormView({ token }: { token: string }) {
  const form = usePublicForm(token);
  const submit = useSubmitPublicForm(token);
  const [success, setSuccess] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const onSubmit = async (values: Record<string, unknown>) => {
    setError(null);
    try {
      const result = await submit.mutateAsync(values);
      setSuccess(result.message || "Thank you — your response has been saved.");
    } catch (err) {
      const detail = (err as { body?: { detail?: unknown } })?.body?.detail as
        | { errors?: string[]; message?: string }
        | string
        | undefined;
      setError(
        typeof detail === "string"
          ? detail
          : detail?.errors?.join(" ") || "Your response could not be saved. Please try again.",
      );
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-4 py-12">
      <div className="w-full max-w-xl rounded-lg border border-subtle bg-surface p-6 shadow-elevation-1 sm:p-8">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <p className="text-2xs uppercase tracking-wide text-tertiary">
              {form.data?.agent_name ? `Form by ${form.data.agent_name}` : "Form"}
            </p>
            <h1 className="mt-1 text-2xl font-medium text-primary">
              {form.data?.title ?? "Loading form…"}
            </h1>
            {form.data?.description && (
              <p className="mt-2 text-sm leading-5 text-secondary">
                {form.data.description}
              </p>
            )}
          </div>
          <Badge tone="neutral">Secure form</Badge>
        </div>

        {form.isLoading ? (
          <div className="flex flex-col gap-4">
            <Skeleton height={40} className="rounded-sm" />
            <Skeleton height={40} className="rounded-sm" />
            <Skeleton height={80} className="rounded-sm" />
            <Skeleton height={40} className="rounded-sm" />
          </div>
        ) : form.isError || !form.data ? (
          <AlertBanner tone="danger" title="This form is unavailable">
            The link may have expired or the form was unpublished by its owner.
          </AlertBanner>
        ) : success ? (
          <div className="flex flex-col gap-4">
            <AlertBanner tone="success" title="Response saved">
              {success}
            </AlertBanner>
            <p className="text-xs text-tertiary">
              You can close this page. The business has received your details.
            </p>
          </div>
        ) : (
          <ActionFieldForm
            fields={form.data.fields}
            submitLabel={form.data.submit_label}
            requireConsent={Boolean(form.data.require_consent)}
            loading={submit.isPending}
            error={error}
            onSubmit={onSubmit}
          />
        )}

        <p className="mt-6 text-center text-2xs text-tertiary">
          Powered by {process.env.NEXT_PUBLIC_APP_NAME || "BotBase"}
        </p>
      </div>
    </main>
  );
}
