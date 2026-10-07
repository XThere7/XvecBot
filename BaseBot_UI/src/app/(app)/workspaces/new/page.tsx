"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { FieldControl } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { MAX_NAME_LENGTH } from "@/lib/constants";
import { workspaceHref } from "@/lib/routes";
import {
  WORKSPACE_FORM_DEFAULTS,
  workspaceSchema,
  type WorkspaceValues,
} from "@/schemas/workspace";
import { useCreateWorkspace } from "@/hooks/use-workspaces";
import { ApiRequestError } from "@/lib/api-client";
import { normaliseError } from "@/lib/api-error";

export default function NewWorkspacePage() {
  const router = useRouter();
  const createWorkspace = useCreateWorkspace();
  const [serverErrors, setServerErrors] = React.useState<Record<string, string>>({});

  const {
    register,
    handleSubmit,
    watch,
    setError,
    formState: { errors },
  } = useForm<WorkspaceValues>({
    resolver: zodResolver(workspaceSchema),
    defaultValues: WORKSPACE_FORM_DEFAULTS,
    mode: "onBlur",
  });

  const name = watch("name") ?? "";

  const submit = handleSubmit(async (values) => {
    setServerErrors({});
    try {
      const workspace = await createWorkspace.mutateAsync({
        name: values.name,
        description: values.description || null,
        system_prompt: values.system_prompt || null,
      });
      router.push(workspaceHref(workspace.id, "documents"));
    } catch (error) {
      if (error instanceof ApiRequestError) {
        const normalised = normaliseError(error.body, error.status);
        if (normalised.fieldErrors.length > 0) {
          const next: Record<string, string> = {};
          for (const issue of normalised.fieldErrors) next[issue.field] = issue.message;
          setServerErrors(next);
          if (next.name) setError("name", { message: next.name });
          return;
        }
      }
      setServerErrors({ form: "Could not create the workspace. Please try again." });
    }
  });

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="New workspace"
        description="A workspace groups the documents your agents answer from."
        actions={
          <Button asChild variant="ghost" iconLeft={<ArrowLeft aria-hidden className="h-4 w-4" />}>
            <Link href="/workspaces">Cancel</Link>
          </Button>
        }
      />

      <form onSubmit={submit} noValidate className="max-w-2xl">
        <div className="flex flex-col gap-6 rounded-md border border-subtle bg-surface p-6">
          {serverErrors.form && <AlertBanner tone="danger">{serverErrors.form}</AlertBanner>}

          <FieldControl
            label="Name"
            required
            counter={`${name.length}/${MAX_NAME_LENGTH}`}
            error={errors.name?.message ?? serverErrors.name}
            hint="Shown in the workspace switcher and the sidebar."
          >
            <Input
              placeholder="Acme Store"
              autoComplete="off"
              invalid={Boolean(errors.name ?? serverErrors.name)}
              {...register("name")}
            />
          </FieldControl>

          <FieldControl
            label="Description"
            error={errors.description?.message ?? serverErrors.description}
            hint="Optional. A one-line reminder of what this workspace knows."
          >
            <Textarea
              rows={2}
              placeholder="Product catalogue and delivery policy for acmestore.co.tz"
              invalid={Boolean(errors.description ?? serverErrors.description)}
              {...register("description")}
            />
          </FieldControl>

          <FieldControl
            label="Default system prompt"
            error={errors.system_prompt?.message ?? serverErrors.system_prompt}
            hint="This is the baseline instruction for workspace-level chat. Each agent can override it."
          >
            <Textarea
              rows={4}
              invalid={Boolean(errors.system_prompt ?? serverErrors.system_prompt)}
              {...register("system_prompt")}
            />
          </FieldControl>

          <div className="flex items-center justify-end gap-2 border-t border-subtle pt-4">
            <Button asChild variant="secondary">
              <Link href="/workspaces">Cancel</Link>
            </Button>
            <Button type="submit" variant="primary" loading={createWorkspace.isPending}>
              Create workspace
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}