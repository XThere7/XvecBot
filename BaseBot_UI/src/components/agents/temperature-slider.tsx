"use client";

import { RangeSlider } from "@/components/ui/range-slider";
import { FieldControl } from "@/components/ui/field";
import { temperatureCaption } from "@/lib/reference-data";

export function TemperatureSlider({
  value,
  onChange,
  error,
  disabled,
}: {
  value: number;
  onChange: (value: number) => void;
  error?: string;
  disabled?: boolean;
}) {
  return (
    <FieldControl
      className="min-w-0"
      error={error}
      hint="Lower is more faithful to your documents. Higher varies its phrasing."
    >
      <RangeSlider
        label="Temperature"
        value={value}
        onValueChange={onChange}
        min={0}
        max={1}
        step={0.1}
        captionFor={temperatureCaption}
        disabled={disabled}
      />
    </FieldControl>
  );
}