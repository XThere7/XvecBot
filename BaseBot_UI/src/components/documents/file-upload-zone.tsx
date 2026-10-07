"use client";

import * as React from "react";
import { FileUp, UploadCloud, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { ALLOWED_FILE_EXTENSIONS, MAX_FILE_SIZE_MB } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export type FileUploadZoneProps = {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
  uploadingCount?: number;
  /** Per-file pre-flight rejections, shown under the zone. */
  rejections?: { name: string; message: string }[];
  onDismissRejection?: (index: number) => void;
  /** Exposed so empty states and headers can trigger the native picker. */
  inputRef?: React.RefObject<HTMLInputElement | null>;
  className?: string;
};

/**
 * Drag-and-drop upload with client-side pre-flight checks. Files upload
 * sequentially, one at a time.
 */
export function FileUploadZone({
  onFiles,
  disabled,
  uploadingCount = 0,
  rejections = [],
  onDismissRejection,
  inputRef,
  className,
}: FileUploadZoneProps) {
  const [dragOver, setDragOver] = React.useState(false);
  const localRef = React.useRef<HTMLInputElement | null>(null);
  const fileInputRef = inputRef ?? localRef;

  const handleFiles = (list: FileList | null) => {
    if (!list || list.length === 0) return;
    onFiles(Array.from(list));
  };

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragOver(false);
          if (disabled) return;
          handleFiles(event.dataTransfer.files);
        }}
        className={cn(
          "rounded-md border-2 border-dashed px-5 py-7 text-center transition-colors duration-150",
          dragOver
            ? "border-accent-500 bg-accent-tint"
            : "border-strong bg-surface hover:border-tertiary",
          disabled && "pointer-events-none opacity-60",
        )}
      >
        <UploadCloud
          aria-hidden
          className={cn(
            "mx-auto h-6 w-6",
            dragOver ? "text-accent-400" : "text-tertiary",
          )}
        />
        <p className="mt-3 text-base text-primary">
          {uploadingCount > 0
            ? `Uploading ${uploadingCount} file${uploadingCount === 1 ? "" : "s"}…`
            : "Drop files here, or choose from your device"}
        </p>
        <p className="mt-1 text-xs text-tertiary">
          {ALLOWED_FILE_EXTENSIONS.join(", ")} · recommended under{" "}
          {MAX_FILE_SIZE_MB} MB
        </p>

        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ALLOWED_FILE_EXTENSIONS.join(",")}
          className="sr-only"
          onChange={(event) => {
            handleFiles(event.target.files);
            event.target.value = "";
          }}
        />

        <Button
          type="button"
          variant="secondary"
          className="mt-4"
          disabled={disabled}
          iconLeft={<FileUp aria-hidden className="h-4 w-4" />}
          onClick={() => fileInputRef.current?.click()}
        >
          Choose file
        </Button>
      </div>

      {rejections.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {rejections.map((rejection, index) => (
            <li
              key={`${rejection.name}-${index}`}
              className="flex items-start justify-between gap-3 rounded-sm border border-danger-500/30 bg-danger-500/5 px-3 py-2 text-xs text-danger-400"
            >
              <span>
                <strong className="font-medium">{rejection.name}</strong> —{" "}
                {rejection.message}
              </span>
              {onDismissRejection && (
                <button
                  type="button"
                  onClick={() => onDismissRejection(index)}
                  aria-label={`Dismiss ${rejection.name}`}
                  className="rounded-sm p-0.5 text-tertiary transition-colors hover:text-primary"
                >
                  <X aria-hidden className="h-3.5 w-3.5" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function UploadZoneSkeleton() {
  return <Skeleton height={172} className="rounded-md" />;
}