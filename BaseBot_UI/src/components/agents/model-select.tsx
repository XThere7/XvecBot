"use client";

import { Select } from "@/components/ui/select";
import { FieldControl } from "@/components/ui/field";
import { MODEL_BILLING_CAPTION, MODEL_GROUPS, modelLabel } from "@/lib/reference-data";
import { cn } from "@/lib/cn";

export function ModelSelect({
  value,
  onChange,
  error,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  error?: string;
  disabled?: boolean;
}) {
  const options = MODEL_GROUPS.flatMap((group) => group.options);

  return (
    <FieldControl
      label="Model"
      required
      error={error}
      hint={MODEL_BILLING_CAPTION}
      className="min-w-0"
    >
      <div className={cn(disabled && "opacity-60")}>
        <Select
          value={value}
          onValueChange={onChange}
          groups={MODEL_GROUPS}
          options={options}
          disabled={disabled}
          invalid={Boolean(error)}
        />
      </div>
      <p className="text-2xs text-tertiary">Currently: {modelLabel(value)}</p>
    </FieldControl>
  );
}