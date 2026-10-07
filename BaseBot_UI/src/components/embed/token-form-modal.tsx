"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ApiRequestError } from "@/lib/api-client";
import { normaliseError } from "@/lib/api-error";
import { MAX_LABEL_LENGTH } from "@/lib/constants";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { FieldControl } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { OriginChipInput } from "@/components/ui/origin-chip-input";
import {
  ORIGIN_HELPER,
  TOKEN_FORM_DEFAULTS,
  tokenFormSchema,
  type TokenFormValues,
} from "@/schemas/token";
import { useCreateToken, useUpdateToken } from "@/hooks/use-embed-tokens";
import type { EmbedToken } from "@/types/api";

export function TokenFormModal({
  open,
  onClose,
  wsId,
  agentId,
  editing,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  wsId: string;
  agentId: string;
  /** Present in edit mode. */
  editing?: EmbedToken | null;
  /** Called with the full-token 201 response so the one-time modal can open. */
  onCreated: (token: EmbedToken) => void;
}) {
  const createToken = useCreateToken(wsId, agentId);
  const updateToken = useUpdateToken(wsId, agentId);
  const [formError, setFormError] = React.useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    watch,
    setValue,
    formState: { errors },
  } = useForm<TokenFormValues>({
    resolver: zodResolver(tokenFormSchema),
    defaultValues: TOKEN_FORM_DEFAULTS,
    mode: "onBlur",
  });

  React.useEffect(() => {
    if (!open) return;
    reset(
      editing
        ? {
            label: editing.label,
            allowed_origins: editing.allowed_origins ?? [],
          }
        : TOKEN_FORM_DEFAULTS,
    );
    setFormError(null);
  }, [open, editing, reset]);

  const label = watch("label") ?? "";
  const origins = watch("allowed_origins") ?? [];

  const submit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      if (editing) {
        // Sending [] clears the restriction — the backend stores null.
        await updateToken.mutateAsync({
          tokenId: editing.id,
          label: values.label,
          allowed_origins: values.allowed_origins,
        });
        onClose();
        return;
      }

      const created = await createToken.mutateAsync({
        label: values.label,
        allowed_origins: values.allowed_origins,
      });
      onClose();
      onCreated(created);
    } catch (error) {
      if (error instanceof ApiRequestError) {
        const normalised = normaliseError(error.body, error.status);
        if (normalised.fieldErrors.length > 0) {
          setFormError(normalised.fieldErrors[0]?.message ?? null);
          return;
        }
        setFormError(normalised.message);
        return;
      }
      setFormError("Cannot reach the server.");
    }
  });

  const pending = editing ? updateToken.isPending : createToken.isPending;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editing ? "Edit embed token" : "Create embed token"}
      description={
        editing
          ? "Only the fields you change are sent — the update endpoint ignores empty values."
          : "A token is the key that lets one website talk to this agent."
      }
      size="md"
      initialFocusSelector='[data-autofocus="true"]'
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => void submit()}
            loading={pending}
            disabled={pending}
          >
            {editing ? "Save changes" : "Create token"}
          </Button>
        </>
      }
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-5">
        {formError && <AlertBanner tone="danger">{formError}</AlertBanner>}

        <FieldControl
          label="Label"
          required
          counter={`${label.length}/${MAX_LABEL_LENGTH}`}
          error={errors.label?.message}
          hint="A reminder of where this token is used, e.g. acmestore.co.tz."
        >
          <Input
            data-autofocus="true"
            placeholder="acmestore.co.tz"
            autoComplete="off"
            invalid={Boolean(errors.label)}
            {...register("label")}
          />
        </FieldControl>

        <FieldControl
          label="Allowed origins"
          error={undefined}
          hint={ORIGIN_HELPER}
        >
          <OriginChipInput
            value={origins}
            onChange={(next) =>
              setValue("allowed_origins", next, { shouldValidate: true })
            }
          />
        </FieldControl>

        {editing && (
          <AlertBanner tone="info">
            To allow any origin again, remove every chip and save — an empty list
            is stored as &ldquo;any origin&rdquo;.
          </AlertBanner>
        )}

        <p className="text-2xs leading-4 text-tertiary">
          Widget position and colour are decided server-side and already appear
          in the snippet (<code className="font-mono">data-position</code>,{" "}
          <code className="font-mono">data-color</code>). They are not editable
          from the dashboard.
        </p>
      </form>
    </Modal>
  );
}