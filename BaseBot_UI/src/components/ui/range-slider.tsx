"use client";

import * as React from "react";
import { cn } from "@/lib/cn";
import { useFieldProps } from "./field";

export type RangeSliderProps = {
  value: number;
  onValueChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  label: string;
  captionFor?: (value: number) => string;
  valueFormatter?: (value: number) => string;
  disabled?: boolean;
  id?: string;
  "aria-describedby"?: string;
};

export function RangeSlider({
  value,
  onValueChange,
  min = 0,
  max = 1,
  step = 0.1,
  label,
  captionFor,
  valueFormatter = (v) => v.toFixed(1),
  disabled,
  id,
  ...aria
}: RangeSliderProps) {
  const field = useFieldProps();
  const generatedId = React.useId();
  const inputId = id ?? field.id ?? `slider-${generatedId}`;
  const percent = ((value - min) / (max - min)) * 100;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3">
        <label htmlFor={inputId} className="text-xs font-medium text-secondary">
          {label}
        </label>
        <span className="rounded-chip border border-subtle bg-surface-raised px-2 py-0.5 font-mono text-xs text-primary">
          {valueFormatter(value)}
        </span>
      </div>
      <input
        id={inputId}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(event) => onValueChange(Number(event.target.value))}
        aria-describedby={aria["aria-describedby"] ?? field["aria-describedby"]}
        aria-valuetext={captionFor ? captionFor(value) : valueFormatter(value)}
        className={cn(
          "h-1.5 w-full cursor-pointer appearance-none rounded-full outline-none",
          "[&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:appearance-none",
          "[&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-2",
          "[&::-webkit-slider-thumb]:border-accent-500 [&::-webkit-slider-thumb]:bg-white",
          "[&::-moz-range-thumb]:h-3 [&::-moz-range-thumb]:w-3 [&::-moz-range-thumb]:rounded-full",
          "[&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-accent-500 [&::-moz-range-thumb]:bg-white",
          "disabled:cursor-not-allowed disabled:opacity-50",
        )}
        style={{
          background: `linear-gradient(to right, var(--color-accent-500) 0%, var(--color-accent-500) ${percent}%, var(--color-strong) ${percent}%, var(--color-strong) 100%)`,
        }}
      />
      {captionFor && (
        <p className="flex items-center justify-between text-xs text-tertiary">
          <span>Precise</span>
          <span className="text-secondary">{captionFor(value)}</span>
          <span>Creative</span>
        </p>
      )}
    </div>
  );
}