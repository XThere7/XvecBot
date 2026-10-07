"use client";

import * as React from "react";
import { Pencil } from "lucide-react";
import { AgentForm } from "@/components/agents/agent-form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DefinitionList } from "@/components/ui/definition-list";
import { RelativeTime } from "@/components/ui/relative-time";
import { Skeleton } from "@/components/ui/skeleton";
import { ActiveBadge } from "@/components/ui/toggle";
import { modelLabel } from "@/lib/reference-data";
import { useAgent } from "@/hooks/use-agents";
import type { AgentValues } from "@/schemas/agent";

export function AgentOverview({ wsId, agentId }: { wsId: string; agentId: string }) {
  const agentQuery = useAgent(wsId, agentId);
  const [editing, setEditing] = React.useState(false);
  const agent = agentQuery.data;

  if (agentQuery.isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <div className="rounded-md border border-subtle bg-surface p-6">
          <Skeleton rows={4} height={18} />
        </div>
      </div>
    );
  }

  if (!agent) return null;

  if (editing) {
    const initial: AgentValues = {
      name: agent.name,
      description: agent.description ?? "",
      system_prompt: agent.system_prompt,
      welcome_message: agent.welcome_message ?? "",
      model: agent.model,
      temperature: agent.temperature,
      language: agent.language,
    };

    return (
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-xl text-primary">Edit configuration</h2>
          <Button variant="secondary" size="sm" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </div>
        <AgentForm
          wsId={wsId}
          agentId={agentId}
          initialValues={initial}
          submitLabel="Save agent"
          onSaved={() => setEditing(false)}
        />
      </div>
    );
  }

  const isActive = Boolean(agent.is_active);

  return (
    <div className="flex flex-col gap-6">
      <section className="rounded-md border border-subtle bg-surface p-6 shadow-elevation-1">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-xl text-primary">Configuration</h2>
            <p className="mt-1 text-sm text-secondary">
              Every field here is sent to the model on each message.
            </p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setEditing(true)}
            iconLeft={<Pencil aria-hidden className="h-4 w-4" />}
          >
            Edit
          </Button>
        </div>

        <DefinitionList
          className="mt-6"
          items={[
            {
              label: "Name",
              value: agent.name,
              note: "Shown in the widget header — customer-facing.",
            },
            { label: "Status", value: <ActiveBadge active={isActive} /> },
            { label: "Language", value: agent.language },
            {
              label: "Model",
              value: (
                <span className="flex items-center gap-2">
                  <Badge tone="neutral">{modelLabel(agent.model)}</Badge>
                  <span className="font-mono text-2xs text-tertiary">{agent.model}</span>
                </span>
              ),
            },
            { label: "Temperature", value: agent.temperature.toFixed(1) },
            {
              label: "Description",
              value: agent.description ?? "Not set",
              note: "Shown in the agent list in this dashboard only.",
            },
            {
              label: "System prompt",
              value: (
                <span className="whitespace-pre-wrap">{agent.system_prompt}</span>
              ),
            },
            {
              label: "Welcome message",
              value: agent.welcome_message ?? "Platform default greeting",
              note: "The only message visitors see before sending anything.",
            },
            {
              label: "Agent ID",
              value: agent.id,
              mono: true,
              copyable: agent.id,
            },
            { label: "Created", value: <RelativeTime date={agent.created_at} /> },
            { label: "Updated", value: <RelativeTime date={agent.updated_at} /> },
          ]}
        />
      </section>
    </div>
  );
}