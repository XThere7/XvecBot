"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ApiRequestError } from "@/lib/api-client";
import { normaliseError } from "@/lib/api-error";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { FieldControl } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { Toggle } from "@/components/ui/toggle";
import { useAgents } from "@/hooks/use-agents";
import { useCreateApiKey, useUpdateApiKey } from "@/hooks/use-api-keys";
import {
  API_KEY_FORM_DEFAULTS,
  apiKeyFormSchema,
  expiryToIso,
  type ApiKeyFormValues,
} from "@/schemas/api-key";
import type { DeveloperApiKey, DeveloperApiKeyCreated } from "@/types/api";

export function ApiKeyFormModal({
  open,
  onClose,
  wsId,
  editing,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  wsId: string;
  editing: DeveloperApiKey | null;
  onCreated: (created: DeveloperApiKeyCreated) => void;
}) {
  const agentsQuery = useAgents(wsId);
  const createKey = useCreateApiKey(wsId);
  const updateKey = useUpdateApiKey(wsId);
  const [serverError, setServerError] = React.useState<string | null>(null);

  const form = useForm<ApiKeyFormValues>({
    resolver: zodResolver(apiKeyFormSchema),
    defaultValues: API_KEY_FORM_DEFAULTS,
  });

  const restrictAgents = form.watch("restrict_agents");
  const selectedAgents = form.watch("allowed_agents");
  const agents = agentsQuery.data ?? [];
  const pending = createKey.isPending || updateKey.isPending;

  React.useEffect(() => {
    if (!open) return;
    form.reset(
      editing
        ? {
            name: editing.name,
            expires_at: "",
            restrict_agents: editing.allowed_agents !== null,
            allowed_agents: editing.allowed_agents ?? [],
          }
        : API_KEY_FORM_DEFAULTS,
    );
    setServerError(null);
  }, [open, editing, form]);

  const toggleAgent = (agentId: string, checked: boolean) => {
    const next = checked
      ? [...selectedAgents, agentId]
      : selectedAgents.filter((id) => id !== agentId);
    form.setValue("allowed_agents", next, { shouldValidate: true, shouldDirty: true });
  };

  const onSubmit = form.handleSubmit(async (values) => {
    setServerError(null);
    try {
      if (editing) {
        await updateKey.mutateAsync({
          keyId: editing.id,
          name: values.name,
          allowed_agents: values.restrict_agents ? values.allowed_agents : null,
        });
      } else {
        const created = await createKey.mutateAsync({
          name: values.name,
          allowed_agents: values.restrict_agents ? values.allowed_agents : null,
          expires_at: expiryToIso(values.expires_at),
        });
        // The mutation cache must not retain the plaintext key. The one-time
        // modal receives it as component state only.
        createKey.reset();
        onCreated(created);
      }
      onClose();
    } catch (error) {
      if (error instanceof ApiRequestError) {
        setServerError(normaliseError(error.body, error.status).message);
      } else {
        setServerError("Could not save the API key. Please try again.");
      }
    }
  });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editing ? "Edit API key" : "Create API key"}
      description={
        editing
          ? "Update the name or which agents this key may call."
          : "Keys are for server-to-server use. Never put one in browser code."
      }
      size="md"
      dismissible={!pending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button
            type="submit"
            form="api-key-form"
            variant="primary"
            loading={pending}
            disabled={pending}
          >
            {editing ? "Save changes" : "Create key"}
          </Button>
        </>
      }
    >
      <form id="api-key-form" onSubmit={onSubmit} className="flex flex-col gap-5">
        {serverError && (
          <AlertBanner tone="danger" title="Could not save the key">
            {serverError}
          </AlertBanner>
        )}

        <FieldControl
          label="Key name"
          hint="A label for your own reference, e.g. “Production website”."
          error={form.formState.errors.name?.message}
          required
        >
          <Input
            {...form.register("name")}
            placeholder="Production integration"
            autoComplete="off"
            autoFocus
          />
        </FieldControl>

        {!editing && (
          <FieldControl
            label="Expiry (optional)"
            hint="Leave blank for a key that does not expire. The date is the last usable day."
            error={form.formState.errors.expires_at?.message}
          >
            <Input type="date" {...form.register("expires_at")} />
          </FieldControl>
        )}

        <div className="rounded-md border border-subtle bg-surface px-4 py-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-primary">
                Restrict to specific agents
              </p>
              <p className="mt-0.5 text-xs leading-5 text-tertiary">
                Without a restriction, this key can call every active agent in
                this workspace.
              </p>
            </div>
            <Toggle
              checked={restrictAgents}
              label="Restrict this key to specific agents"
              onCheckedChange={(checked) => {
                form.setValue("restrict_agents", checked, {
                  shouldValidate: true,
                  shouldDirty: true,
                });
              }}
            />
          </div>

          {restrictAgents && (
            <div className="mt-3 border-t border-subtle pt-3">
              {agentsQuery.isLoading ? (
                <Skeleton variant="text" rows={3} />
              ) : agents.length === 0 ? (
                <p className="text-xs text-tertiary">
                  No agents exist in this workspace yet. Create one before
                  restricting this key.
                </p>
              ) : (
                <fieldset className="flex max-h-44 flex-col gap-2 overflow-y-auto pr-1">
                  <legend className="sr-only">Allowed agents</legend>
                  {agents.map((agent) => {
                    const checked = selectedAgents.includes(agent.id);
                    return (
                      <label
                        key={agent.id}
                        className="flex cursor-pointer items-center gap-2 rounded-sm px-1 py-1 text-sm text-secondary hover:bg-surface-hover"
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(event) =>
                            toggleAgent(agent.id, event.target.checked)
                          }
                          className="h-4 w-4 accent-accent-500"
                        />
                        <span className="min-w-0 flex-1 truncate">{agent.name}</span>
                        {!Boolean(agent.is_active) && (
                          <span className="text-2xs text-tertiary">Inactive</span>
                        )}
                      </label>
                    );
                  })}
                </fieldset>
              )}
              {form.formState.errors.allowed_agents?.message && (
                <p className="mt-2 text-xs text-danger-400">
                  {form.formState.errors.allowed_agents.message}
                </p>
              )}
            </div>
          )}
        </div>

        {editing && (
          <p className="text-xs leading-5 text-tertiary">
            Expiry and the masked prefix cannot be changed. Revoke this key and
            create a new one if you need a different expiry.
          </p>
        )}
      </form>
    </Modal>
  );
}
