"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { RotateCcw } from "lucide-react";
import { LanguageSelect } from "./language-select";
import { ModelSelect } from "./model-select";
import { TemperatureSlider } from "./temperature-slider";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { FieldControl } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiRequestError } from "@/lib/api-client";
import { normaliseError } from "@/lib/api-error";
import { MAX_DESCRIPTION_LENGTH, MAX_NAME_LENGTH } from "@/lib/constants";
import { agentHref } from "@/lib/routes";
import { toast } from "@/lib/toast";
import {
  AGENT_FORM_DEFAULTS,
  AGENT_SYSTEM_PROMPT_PLACEHOLDER,
  agentSchema,
  clampTemperature,
  type AgentValues,
} from "@/schemas/agent";
import { useCreateAgent, useUpdateAgent } from "@/hooks/use-agents";
import type { Agent } from "@/types/api";

export type AgentFormProps = {
  wsId: string;
  /** Present in edit mode. */
  agentId?: string;
  initialValues?: AgentValues;
  submitLabel?: string;
  onSaved?: (agent: Agent) => void;
};

export function AgentForm({
  wsId,
  agentId,
  initialValues,
  submitLabel = "Create agent",
  onSaved,
}: AgentFormProps) {
  const router = useRouter();
  const createAgent = useCreateAgent(wsId);
  const updateAgent = useUpdateAgent(wsId, agentId ?? "");
  const [formError, setFormError] = React.useState<string | null>(null);

  const isEdit = Boolean(agentId);

  const {
    register,
    handleSubmit,
    reset,
    watch,
    setValue,
    setError,
    formState: { errors, dirtyFields },
  } = useForm<AgentValues>({
    resolver: zodResolver(agentSchema),
    defaultValues: initialValues ?? AGENT_FORM_DEFAULTS,
    mode: "onBlur",
  });

  const welcome = watch("welcome_message") ?? "";
  const model = watch("model");
  const language = watch("language");
  const temperature = watch("temperature");

  const submit = handleSubmit(async (values) => {
    setFormError(null);

    // Clamp locally: the backend soft-clamps, so the UI must agree with it.
    const temperature_ = clampTemperature(Number(values.temperature));

    try {
      if (isEdit && agentId) {
        const updates: {
          name?: string;
          description?: string;
          system_prompt?: string;
          welcome_message?: string;
          model?: string;
          temperature?: number;
          language?: string;
        } = {
          name: values.name,
          system_prompt: values.system_prompt,
          temperature: temperature_,
          model: values.model,
          language: values.language,
        };

        // The backend drops nulls on update. Clear `description` with an
        // explicit empty string and reset `welcome_message` with a single
        // space, which the public API maps back to the default greeting.
        if (dirtyFields.description) updates.description = values.description ?? "";
        if (dirtyFields.welcome_message) {
          updates.welcome_message =
            values.welcome_message && values.welcome_message.trim() !== ""
              ? values.welcome_message
              : " ";
        }

        const agent = await updateAgent.mutateAsync(updates);
        toast.success({ title: "Agent saved" });
        onSaved?.(agent);
        return;
      }

      const agent = await createAgent.mutateAsync({
        name: values.name,
        description: values.description || null,
        system_prompt: values.system_prompt,
        welcome_message: values.welcome_message || null,
        model: values.model,
        temperature: temperature_,
        language: values.language,
      });
      toast.success({ title: "Agent created" });
      router.push(agentHref(wsId, agent.id, "overview"));
    } catch (error) {
      if (error instanceof ApiRequestError) {
        const normalised = normaliseError(error.body, error.status);
        if (normalised.fieldErrors.length > 0) {
          for (const issue of normalised.fieldErrors) {
            setError(issue.field as keyof AgentValues, {
              message: issue.message,
            });
          }
          return;
        }
        setFormError(normalised.message);
        return;
      }
      setFormError("Cannot reach the server.");
    }
  });

  const pending = isEdit ? updateAgent.isPending : createAgent.isPending;

  return (
    <form onSubmit={submit} noValidate className="flex max-w-2xl flex-col gap-6">
      <div className="flex flex-col gap-6 rounded-md border border-subtle bg-surface p-6">
        {formError && <AlertBanner tone="danger">{formError}</AlertBanner>}

        <FieldControl
          label="Name"
          required
          counter={`${(watch("name") ?? "").length}/${MAX_NAME_LENGTH}`}
          error={errors.name?.message}
          hint="Shown in the widget header, so it is customer-facing."
        >
          <Input
            placeholder="Acme Store Support"
            autoComplete="off"
            invalid={Boolean(errors.name)}
            {...register("name")}
          />
        </FieldControl>

        <FieldControl
          label="Description"
          counter={`${(watch("description") ?? "").length}/${MAX_DESCRIPTION_LENGTH}`}
          error={errors.description?.message}
          hint={
            isEdit
              ? "Optional. Shown in the agent list in this dashboard. Clear the field and save to reset it to the platform default."
              : "Optional. Shown in the agent list in this dashboard."
          }
        >
          <Textarea
            rows={2}
            invalid={Boolean(errors.description)}
            {...register("description")}
          />
        </FieldControl>

        <FieldControl
          label="System prompt"
          required
          error={errors.system_prompt?.message}
          hint="The persona and the rules of the agent. This is the most important field."
        >
          <Textarea
            rows={6}
            placeholder={AGENT_SYSTEM_PROMPT_PLACEHOLDER}
            invalid={Boolean(errors.system_prompt)}
            {...register("system_prompt")}
          />
        </FieldControl>

        <FieldControl
          label="Welcome message"
          counter={`${welcome.length}/500`}
          error={errors.welcome_message?.message}
          hint={
            isEdit
              ? "The first thing visitors see when they open the chat. This is the only message shown before the visitor sends anything. Clear the field and save to reset it to the platform default."
              : "The first thing visitors see when they open the chat. Leave empty for the default greeting. This is the only message shown before the visitor sends anything."
          }
        >
          <Textarea
            rows={3}
            placeholder="Hi! Ask me about our products, prices or delivery."
            invalid={Boolean(errors.welcome_message)}
            {...register("welcome_message")}
          />
        </FieldControl>

        <div className="h-px bg-subtle" />

        <ModelSelect
          value={model}
          onChange={(value) => setValue("model", value, { shouldValidate: true })}
          error={errors.model?.message}
          disabled={pending}
        />

        <TemperatureSlider
          value={Number(temperature)}
          onChange={(value) =>
            setValue("temperature", value, { shouldValidate: false })
          }
          error={errors.temperature?.message}
          disabled={pending}
        />

        <LanguageSelect
          value={language}
          onChange={(value) => setValue("language", value, { shouldValidate: true })}
          error={errors.language?.message}
          disabled={pending}
        />
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          iconLeft={<RotateCcw aria-hidden className="h-4 w-4" />}
          onClick={() => reset(initialValues ?? AGENT_FORM_DEFAULTS)}
          disabled={pending}
        >
          Reset to defaults
        </Button>
        <Button asChild variant="secondary" disabled={pending}>
          <Link
            href={isEdit && agentId ? agentHref(wsId, agentId, "overview") : `/workspaces/${wsId}?tab=agents`}
          >
            Cancel
          </Link>
        </Button>
        <Button type="submit" variant="primary" loading={pending} disabled={pending}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}