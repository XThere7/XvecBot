"use client";

import * as React from "react";
import { Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { FieldControl } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Toggle } from "@/components/ui/toggle";
import { toast } from "@/lib/toast";
import { workspaceHref } from "@/lib/routes";
import {
  useCollections,
  useCreateCollection,
  useCustomForms,
  useUpsertAction,
} from "@/hooks/use-engagement";
import type { ActionCatalogEntry, ActionField, ActionFieldType } from "@/types/api";

const FIELD_TYPES: { value: ActionFieldType; label: string }[] = [
  { value: "short_text", label: "Short text" },
  { value: "long_text", label: "Long text" },
  { value: "email", label: "Email" },
  { value: "phone", label: "Phone" },
  { value: "number", label: "Number" },
  { value: "select", label: "Dropdown" },
  { value: "boolean", label: "Yes / no" },
  { value: "date", label: "Date" },
];

function newField(index: number): ActionField {
  return {
    key: `field_${index}`,
    label: "New field",
    type: "short_text",
    required: false,
  };
}

export function ActionConfigModal({
  open,
  onClose,
  wsId,
  agentId,
  entry,
}: {
  open: boolean;
  onClose: () => void;
  wsId: string;
  agentId: string;
  entry: ActionCatalogEntry | null;
}) {
  const upsert = useUpsertAction(wsId, agentId);
  const collections = useCollections(wsId, agentId);
  const forms = useCustomForms(wsId, agentId);
  const createCollection = useCreateCollection(wsId, agentId);

  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [instructions, setInstructions] = React.useState("");
  const [active, setActive] = React.useState(true);
  const [requireConsent, setRequireConsent] = React.useState(false);
  const [consentText, setConsentText] = React.useState("");
  const [notifyEmail, setNotifyEmail] = React.useState("");
  const [reasonTemplate, setReasonTemplate] = React.useState("");
  const [collectionId, setCollectionId] = React.useState("");
  const [formId, setFormId] = React.useState("");
  const [fields, setFields] = React.useState<ActionField[]>([]);

  React.useEffect(() => {
    if (!open || !entry) return;
    const action = entry.action;
    const config = action?.config ?? entry.default_config;
    setName(action?.name ?? entry.name);
    setDescription(action?.description ?? entry.description);
    setInstructions(action?.instructions ?? "");
    setActive(action ? Boolean(action.is_active) : true);
    setRequireConsent(Boolean(config.require_consent));
    setConsentText(String(config.consent_text ?? ""));
    setNotifyEmail(String(config.notify_email ?? ""));
    setReasonTemplate(String(config.reason_template ?? ""));
    setCollectionId(String(config.collection_id ?? ""));
    setFormId(String(config.form_id ?? ""));
    setFields(Array.isArray(config.fields) ? config.fields : []);
  }, [open, entry]);

  if (!entry) return null;

  const supportsFields =
    entry.action_type === "lead_capture" || entry.action_type === "data_collection";

  const updateField = (index: number, patch: Partial<ActionField>) => {
    setFields((current) =>
      current.map((field, i) => (i === index ? { ...field, ...patch } : field)),
    );
  };

  const save = async () => {
    const config: Record<string, unknown> = {};
    if (entry.action_type === "lead_capture") {
      config.fields = fields;
      config.require_consent = requireConsent;
      config.consent_text = consentText.trim() || null;
      config.notify_email = notifyEmail.trim() || null;
    } else if (entry.action_type === "data_collection") {
      config.collection_id = collectionId || null;
      config.require_consent = requireConsent;
    } else if (entry.action_type === "custom_forms") {
      config.form_id = formId || null;
    } else if (entry.action_type === "knowledge_support") {
      config.notify_email = notifyEmail.trim() || null;
      config.reason_template = reasonTemplate.trim() || null;
    }

    try {
      await upsert.mutateAsync({
        actionType: entry.action_type,
        body: {
          name: name.trim() || entry.name,
          description: description.trim() || entry.description,
          instructions: instructions.trim() || null,
          is_active: active,
          config,
        },
      });
      toast.success({ title: active ? "Action saved" : "Action disabled" });
      onClose();
    } catch (error) {
      const detail = (error as { body?: { detail?: unknown } })?.body?.detail;
      toast.error({
        title:
          typeof detail === "string"
            ? detail
            : "Could not save this action. Check the field definitions.",
      });
    }
  };

  const ensureCollection = async () => {
    try {
      const collection = await createCollection.mutateAsync({
        name: `${entry.name} questions`,
        description: "Collected by this agent during conversations.",
        fields:
          fields.length > 0
            ? fields
            : [{ key: "email", label: "Email", type: "email", required: true }],
        allow_partial: false,
        require_consent: requireConsent,
      });
      setCollectionId(collection.id);
      toast.success({ title: "Collection created" });
    } catch {
      toast.error({ title: "Could not create the collection" });
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Configure ${entry.name}`}
      description={entry.description}
      size="lg"
      footer={
        <div className="flex justify-end gap-3">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" onClick={() => void save()} loading={upsert.isPending}>
            Save action
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-5">
        {!entry.plan_available && (
          <AlertBanner
            tone="warning"
            title="Standard plan required"
            action={
              <Button asChild variant="secondary" size="sm">
                <Link href={workspaceHref(wsId, "billing")}>View plans</Link>
              </Button>
            }
          >
            {entry.locked_reason}
          </AlertBanner>
        )}

        <div className="flex items-center justify-between gap-4 rounded-sm border border-subtle bg-surface-raised px-3 py-2.5">
          <div>
            <p className="text-sm text-primary">Action enabled</p>
            <p className="text-xs text-tertiary">
              Disabled actions are hidden from the agent and cannot be submitted.
            </p>
          </div>
          <Toggle checked={active} onCheckedChange={setActive} label="Action enabled" />
        </div>

        <FieldControl label="Name">
          <Input value={name} onChange={(event) => setName(event.target.value)} maxLength={120} />
        </FieldControl>
        <FieldControl label="Description">
          <Textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={2}
            maxLength={1000}
          />
        </FieldControl>
        <FieldControl
          label="Extra instructions for the agent"
          hint="Optional. Explains when the agent should use this action."
        >
          <Textarea
            value={instructions}
            onChange={(event) => setInstructions(event.target.value)}
            rows={3}
            maxLength={4000}
          />
        </FieldControl>

        {supportsFields && entry.action_type === "lead_capture" && (
          <>
            <div className="flex items-center justify-between gap-4 rounded-sm border border-subtle bg-surface-raised px-3 py-2.5">
              <div>
                <p className="text-sm text-primary">Require consent</p>
                <p className="text-xs text-tertiary">
                  The visitor must tick a consent box before their details are stored.
                </p>
              </div>
              <Toggle
                checked={requireConsent}
                onCheckedChange={setRequireConsent}
                label="Require consent"
              />
            </div>
            {requireConsent && (
              <FieldControl label="Consent text">
                <Textarea
                  value={consentText}
                  onChange={(event) => setConsentText(event.target.value)}
                  rows={2}
                  maxLength={1000}
                  placeholder="I agree to be contacted about my enquiry…"
                />
              </FieldControl>
            )}
          </>
        )}

        {entry.action_type === "data_collection" && (
          <>
            <FieldControl
              label="Collection"
              hint="Submissions are stored against this collection. Leave empty to use the first active collection."
            >
              <Select
                options={[
                  { value: "", label: "First active collection" },
                  ...(collections.data ?? []).map((collection) => ({
                    value: collection.id,
                    label: collection.name,
                  })),
                ]}
                value={collectionId}
                onValueChange={setCollectionId}
              />
            </FieldControl>
            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void ensureCollection()}
                loading={createCollection.isPending}
              >
                Create a collection from these fields
              </Button>
              <p className="text-xs text-tertiary">
                Manage fields and submissions in the Capture tab.
              </p>
            </div>
          </>
        )}

        {entry.action_type === "custom_forms" && (
          <FieldControl
            label="Form"
            hint="Create and publish forms in the Capture tab, then select the one the agent should offer."
          >
            <Select
              options={[
                { value: "", label: "First active form" },
                ...(forms.data ?? []).map((form) => ({
                  value: form.id,
                  label: `${form.title} (${form.submission_count} responses)`,
                })),
              ]}
              value={formId}
              onValueChange={setFormId}
            />
          </FieldControl>
        )}

        {entry.action_type === "knowledge_support" && (
          <>
            <FieldControl
              label="Notification email"
              hint="Recorded for the team; no email is sent automatically."
            >
              <Input
                type="email"
                value={notifyEmail}
                onChange={(event) => setNotifyEmail(event.target.value)}
                placeholder="support@yourbusiness.com"
              />
            </FieldControl>
            <FieldControl label="Default escalation reason">
              <Input
                value={reasonTemplate}
                onChange={(event) => setReasonTemplate(event.target.value)}
                maxLength={500}
              />
            </FieldControl>
          </>
        )}

        {supportsFields && (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-primary">Collected fields</p>
                <p className="text-xs text-tertiary">
                  Only these fields are accepted and stored. Keys must start with a
                  letter and use lowercase letters, numbers and underscores.
                </p>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setFields((current) => [...current, newField(current.length + 1)])}
                iconLeft={<Plus aria-hidden className="h-4 w-4" />}
              >
                Add field
              </Button>
            </div>

            {fields.length === 0 && (
              <p className="rounded-sm border border-subtle bg-surface-raised p-3 text-xs text-tertiary">
                No fields yet. Add at least one.
              </p>
            )}

            <div className="flex flex-col gap-3">
              {fields.map((field, index) => (
                <div
                  key={`${field.key}-${index}`}
                  className="rounded-sm border border-subtle bg-surface-raised p-3"
                >
                  <div className="grid gap-3 sm:grid-cols-2">
                    <FieldControl label="Label">
                      <Input
                        value={field.label}
                        onChange={(event) =>
                          updateField(index, { label: event.target.value })
                        }
                        maxLength={120}
                      />
                    </FieldControl>
                    <FieldControl label="Key">
                      <Input
                        value={field.key}
                        onChange={(event) =>
                          updateField(index, {
                            key: event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"),
                          })
                        }
                        maxLength={50}
                      />
                    </FieldControl>
                    <FieldControl label="Type">
                      <Select
                        options={FIELD_TYPES}
                        value={field.type}
                        onValueChange={(next) =>
                          updateField(index, { type: next as ActionFieldType })
                        }
                      />
                    </FieldControl>
                    <div className="flex items-end justify-between gap-3">
                      <label className="flex items-center gap-2 text-xs text-secondary">
                        <input
                          type="checkbox"
                          checked={field.required}
                          onChange={(event) =>
                            updateField(index, { required: event.target.checked })
                          }
                          className="h-4 w-4 accent-accent-500"
                        />
                        Required
                      </label>
                      <Button
                        variant="dangerGhost"
                        size="sm"
                        onClick={() =>
                          setFields((current) => current.filter((_, i) => i !== index))
                        }
                        iconLeft={<Trash2 aria-hidden className="h-4 w-4" />}
                      >
                        Remove
                      </Button>
                    </div>
                  </div>
                  {field.type === "select" && (
                    <div className="mt-3">
                      <FieldControl label="Options" hint="Comma-separated.">
                        <Input
                          value={(field.options ?? []).join(", ")}
                          onChange={(event) =>
                            updateField(index, {
                              options: event.target.value
                                .split(",")
                                .map((option) => option.trim())
                                .filter(Boolean),
                            })
                          }
                        />
                      </FieldControl>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
