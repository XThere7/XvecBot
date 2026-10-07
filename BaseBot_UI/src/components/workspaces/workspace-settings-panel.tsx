"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Save } from "lucide-react";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { FieldControl } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { SavedTick } from "@/components/ui/saved-tick";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { MAX_NAME_LENGTH } from "@/lib/constants";
import { toast } from "@/lib/toast";
import {
  WORKSPACE_FORM_DEFAULTS,
  workspaceSchema,
  type WorkspaceValues,
} from "@/schemas/workspace";
import { useDeleteWorkspace, useUpdateWorkspace, useWorkspace } from "@/hooks/use-workspaces";
import { ApiRequestError } from "@/lib/api-client";
import { normaliseError } from "@/lib/api-error";

export function WorkspaceSettingsPanel({ wsId }: { wsId: string }) {
  const router = useRouter();
  const workspace = useWorkspace(wsId);
  const updateWorkspace = useUpdateWorkspace(wsId);
  const deleteWorkspace = useDeleteWorkspace();

  const [showSaved, setShowSaved] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = React.useState(false);

  const {
    register,
    handleSubmit,
    reset,
    watch,
    setError,
    formState: { errors, isDirty },
  } = useForm<WorkspaceValues>({
    resolver: zodResolver(workspaceSchema),
    defaultValues: WORKSPACE_FORM_DEFAULTS,
    mode: "onBlur",
  });

  // Populate once the workspace arrives.
  const loaded = workspace.data;
  const initialised = React.useRef(false);
  React.useEffect(() => {
    if (loaded && !initialised.current) {
      initialised.current = true;
      reset({
        name: loaded.name,
        description: loaded.description ?? "",
        system_prompt: loaded.system_prompt,
      });
    }
  }, [loaded, reset]);

  const name = watch("name") ?? "";

  const submit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await updateWorkspace.mutateAsync({
        name: values.name,
        description: values.description ?? "",
        system_prompt: values.system_prompt ?? "",
      });
      setShowSaved(true);
      setTimeout(() => setShowSaved(false), 2000);
    } catch (error) {
      if (error instanceof ApiRequestError) {
        const normalised = normaliseError(error.body, error.status);
        const fieldIssue = normalised.fieldErrors[0];
        if (fieldIssue) {
          setError(fieldIssue.field as "name", { message: fieldIssue.message });
          return;
        }
        setFormError(normalised.message);
        return;
      }
      setFormError("Cannot reach the server.");
    }
  });

  const confirmDelete = async () => {
    try {
      await deleteWorkspace.mutateAsync(wsId);
      toast.success({ title: "Workspace deleted" });
      router.replace("/workspaces");
    } catch {
      toast.error({
        title: "Could not delete the workspace",
        description: "Check your connection and try again.",
      });
    }
  };

  if (workspace.isLoading) {
    return (
      <div className="flex max-w-2xl flex-col gap-6">
        <Skeleton variant="card" height={220} />
        <Skeleton variant="card" height={140} />
      </div>
    );
  }

  return (
    <div className="flex max-w-2xl flex-col gap-8">
      <form onSubmit={submit} noValidate className="flex flex-col gap-6">
        <div className="flex flex-col gap-6 rounded-md border border-subtle bg-surface p-6">
          <div>
            <h2 className="text-xl text-primary">Workspace details</h2>
            {/* Workspace has no updated_at — nothing to show here. */}
            <p className="mt-1 text-sm text-secondary">
              These details identify the knowledge base for your team.
            </p>
          </div>

          {formError && <AlertBanner tone="danger">{formError}</AlertBanner>}

          <FieldControl
            label="Name"
            required
            counter={`${name.length}/${MAX_NAME_LENGTH}`}
            error={errors.name?.message}
          >
            <Input invalid={Boolean(errors.name)} {...register("name")} />
          </FieldControl>

          <FieldControl
            label="Description"
            error={errors.description?.message}
            hint="Optional."
          >
            <Textarea rows={2} invalid={Boolean(errors.description)} {...register("description")} />
          </FieldControl>

          <FieldControl
            label="Default system prompt"
            error={errors.system_prompt?.message}
            hint="This is the baseline instruction for workspace-level chat. Each agent can override it."
          >
            <Textarea
              rows={4}
              invalid={Boolean(errors.system_prompt)}
              {...register("system_prompt")}
            />
          </FieldControl>

          <div className="flex items-center justify-end gap-3 border-t border-subtle pt-4">
            <SavedTick show={showSaved} />
            <Button type="submit" variant="primary" loading={updateWorkspace.isPending} disabled={!isDirty} iconLeft={<Save aria-hidden className="h-4 w-4" />}>
              Save changes
            </Button>
          </div>
        </div>
      </form>

      <section className="flex flex-col gap-4 rounded-md border border-danger-500/30 bg-danger-500/5 p-6">
        <div>
          <h2 className="text-xl text-primary">Danger zone</h2>
          <p className="mt-1 text-sm text-secondary">
            Deleting a workspace destroys every document, chunk, embedding,
            agent, conversation and embed token inside it. There is no undo.
            Copy your embed snippets somewhere safe first.
          </p>
        </div>
        <div className="flex justify-end">
          <Button variant="danger" onClick={() => setConfirmOpen(true)}>
            Delete workspace
          </Button>
        </div>
      </section>

      <ConfirmationDialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Delete workspace?"
        body={
          <p>
            This permanently deletes{" "}
            <strong className="font-medium text-primary">
              {workspace.data?.name}
            </strong>{" "}
            — every document, chunk and embedding, all agents, all conversations
            and all embed tokens. This cannot be undone.
          </p>
        }
        confirmLabel="Delete workspace"
        confirmLoading={deleteWorkspace.isPending}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}