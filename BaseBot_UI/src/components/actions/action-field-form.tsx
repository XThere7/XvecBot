"use client";

import * as React from "react";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { FieldControl } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Toggle } from "@/components/ui/toggle";
import type { ActionField } from "@/types/api";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const PHONE_RE = /^\+?[0-9][0-9\s().-]{5,24}$/;

function validateField(field: ActionField, value: unknown): string | null {
  const text = value === undefined || value === null ? "" : String(value).trim();
  if (!text) {
    if (field.required && field.type !== "boolean") {
      return `${field.label} is required.`;
    }
    return null;
  }
  if (field.type === "email" && !EMAIL_RE.test(text)) {
    return "Enter a valid email address.";
  }
  if (field.type === "phone") {
    const digits = text.replace(/\D/g, "");
    if (!PHONE_RE.test(text) || digits.length < 7 || digits.length > 15) {
      return "Enter a valid phone number.";
    }
  }
  if (field.type === "number" && Number.isNaN(Number(text))) {
    return "Enter a number.";
  }
  if (field.type === "select" && field.options?.length && !field.options.includes(text)) {
    return "Choose one of the listed options.";
  }
  const max = field.max_length ?? 10000;
  if (text.length > max) {
    return `${field.label} must be at most ${max} characters.`;
  }
  return null;
}

export function ActionFieldForm({
  fields,
  submitLabel = "Submit",
  requireConsent = false,
  consentText,
  disabled = false,
  loading = false,
  compact = false,
  error,
  onSubmit,
}: {
  fields: ActionField[];
  submitLabel?: string;
  requireConsent?: boolean;
  consentText?: string | null;
  disabled?: boolean;
  loading?: boolean;
  compact?: boolean;
  error?: string | null;
  onSubmit: (values: Record<string, unknown>) => void | Promise<void>;
}) {
  const [values, setValues] = React.useState<Record<string, unknown>>({});
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [consent, setConsent] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);

  const setValue = (key: string, value: unknown) => {
    setValues((current) => ({ ...current, [key]: value }));
    setErrors((current) => {
      if (!current[key]) return current;
      const next = { ...current };
      delete next[key];
      return next;
    });
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const nextErrors: Record<string, string> = {};
    for (const field of fields) {
      const message = validateField(field, values[field.key]);
      if (message) nextErrors[field.key] = message;
    }
    if (requireConsent && !consent) {
      setFormError("Tick the consent box before submitting.");
    } else {
      setFormError(null);
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0 || (requireConsent && !consent)) return;

    const payload: Record<string, unknown> = {};
    for (const field of fields) {
      const value = values[field.key];
      if (value === undefined || value === null || value === "") continue;
      payload[field.key] = value;
    }
    if (requireConsent) payload._consent = true;
    await onSubmit(payload);
  };

  return (
    <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-4">
      {error && <AlertBanner tone="danger">{error}</AlertBanner>}
      {formError && <AlertBanner tone="danger">{formError}</AlertBanner>}
      {fields.map((field) => {
        const value = values[field.key];
        const fieldError = errors[field.key];
        if (field.type === "boolean") {
          return (
            <div
              key={field.key}
              className="flex items-center justify-between gap-4 rounded-sm border border-subtle bg-surface-raised px-3 py-2.5"
            >
              <div>
                <p className="text-sm text-primary">{field.label}</p>
                {field.help_text && (
                  <p className="text-xs text-tertiary">{field.help_text}</p>
                )}
              </div>
              <Toggle
                checked={Boolean(value)}
                onCheckedChange={(next) => setValue(field.key, next)}
                disabled={disabled}
                label={field.label}
                size="sm"
              />
            </div>
          );
        }
        return (
          <FieldControl
            key={field.key}
            label={field.label}
            required={field.required}
            error={fieldError}
            hint={field.help_text || field.placeholder}
          >
            {field.type === "long_text" ? (
              <Textarea
                value={String(value ?? "")}
                onChange={(event) => setValue(field.key, event.target.value)}
                rows={compact ? 3 : 4}
                disabled={disabled}
                invalid={Boolean(fieldError)}
              />
            ) : field.type === "select" ? (
              <Select
                options={(field.options ?? []).map((option) => ({
                  value: option,
                  label: option,
                }))}
                value={String(value ?? "")}
                onValueChange={(next) => setValue(field.key, next)}
                placeholder={`Choose ${field.label.toLowerCase()}`}
                disabled={disabled}
                invalid={Boolean(fieldError)}
              />
            ) : (
              <Input
                type={
                  field.type === "email"
                    ? "email"
                    : field.type === "number"
                      ? "number"
                      : field.type === "date"
                        ? "date"
                        : field.type === "phone"
                          ? "tel"
                          : "text"
                }
                value={String(value ?? "")}
                onChange={(event) => setValue(field.key, event.target.value)}
                disabled={disabled}
                invalid={Boolean(fieldError)}
                placeholder={field.placeholder}
              />
            )}
          </FieldControl>
        );
      })}

      {requireConsent && (
        <label className="flex items-start gap-3 rounded-sm border border-subtle bg-surface-raised p-3 text-xs leading-5 text-secondary">
          <input
            type="checkbox"
            checked={consent}
            onChange={(event) => {
              setConsent(event.target.checked);
              if (event.target.checked) setFormError(null);
            }}
            disabled={disabled}
            className="mt-0.5 h-4 w-4 accent-accent-500"
          />
          <span>
            {consentText ||
              "I agree to be contacted about this enquiry and understand my details will be stored by this business."}
          </span>
        </label>
      )}

      <Button type="submit" loading={loading} disabled={disabled}>
        {submitLabel}
      </Button>
    </form>
  );
}
