"use client";

import { Select } from "@/components/ui/select";
import { FieldControl } from "@/components/ui/field";
import { LANGUAGES } from "@/lib/reference-data";

export function LanguageSelect({
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
  return (
    <FieldControl
      label="Language"
      required
      error={error}
      hint="The widget answers in this language. Anything else is coerced to English by the API."
    >
      <Select
        value={value}
        onValueChange={onChange}
        disabled={disabled}
        invalid={Boolean(error)}
        options={LANGUAGES.map((language) => ({ value: language, label: language }))}
      />
    </FieldControl>
  );
}