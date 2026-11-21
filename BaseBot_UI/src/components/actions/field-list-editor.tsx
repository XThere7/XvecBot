"use client";

import * as React from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { FieldControl } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { ActionField, ActionFieldType } from "@/types/api";

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

export function FieldListEditor({
  fields,
  onChange,
  disabled = false,
}: {
  fields: ActionField[];
  onChange: (fields: ActionField[]) => void;
  disabled?: boolean;
}) {
  const update = (index: number, patch: Partial<ActionField>) => {
    onChange(fields.map((field, i) => (i === index ? { ...field, ...patch } : field)));
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-primary">Fields</p>
          <p className="text-xs text-tertiary">
            Keys must start with a letter and use lowercase letters, numbers and
            underscores.
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={disabled}
          onClick={() => onChange([...fields, newField(fields.length + 1)])}
          iconLeft={<Plus aria-hidden className="h-4 w-4" />}
        >
          Add field
        </Button>
      </div>

      {fields.length === 0 && (
        <p className="rounded-sm border border-subtle bg-surface-raised p-3 text-xs text-tertiary">
          Add at least one field.
        </p>
      )}

      {fields.map((field, index) => (
        <div
          key={`${field.key}-${index}`}
          className="rounded-sm border border-subtle bg-surface-raised p-3"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <FieldControl label="Label">
              <Input
                value={field.label}
                disabled={disabled}
                onChange={(event) => update(index, { label: event.target.value })}
                maxLength={120}
              />
            </FieldControl>
            <FieldControl label="Key">
              <Input
                value={field.key}
                disabled={disabled}
                onChange={(event) =>
                  update(index, {
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
                  update(index, { type: next as ActionFieldType })
                }
                disabled={disabled}
              />
            </FieldControl>
            <div className="flex items-end justify-between gap-3">
              <label className="flex items-center gap-2 text-xs text-secondary">
                <input
                  type="checkbox"
                  checked={field.required}
                  disabled={disabled}
                  onChange={(event) => update(index, { required: event.target.checked })}
                  className="h-4 w-4 accent-accent-500"
                />
                Required
              </label>
              <Button
                type="button"
                variant="dangerGhost"
                size="sm"
                disabled={disabled}
                onClick={() => onChange(fields.filter((_, i) => i !== index))}
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
                  disabled={disabled}
                  onChange={(event) =>
                    update(index, {
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
  );
}
