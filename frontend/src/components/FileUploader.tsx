/**
 * components/FileUploader.tsx
 * Drag-and-drop PDF uploader with progress feedback.
 */
import React, { useCallback, useRef, useState } from "react";
import type { UploadResponse } from "../types";

interface FileUploaderProps {
  onUpload: (file: File) => Promise<UploadResponse>;
  isUploading: boolean;
}

export function FileUploader({ onUpload, isUploading }: FileUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [lastResult, setLastResult] = useState<UploadResponse | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        setUploadError("Only PDF files are supported.");
        return;
      }
      setUploadError(null);
      setLastResult(null);
      try {
        const result = await onUpload(file);
        setLastResult(result);
      } catch (err) {
        setUploadError((err as Error).message);
      } finally {
        // Reset input so same file can be selected again after success/failure
        if (inputRef.current) inputRef.current.value = "";
      }
    },
    [onUpload]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const onInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  return (
    <div className="uploader">
      <div
        className={`drop-zone ${isDragging ? "dragging" : ""} ${isUploading ? "uploading" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        aria-label="Upload PDF"
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf"
          onChange={onInputChange}
          style={{ display: "none" }}
        />
        {isUploading ? (
          <div className="upload-status">
            <div className="spinner" />
            <p>Ingesting document…</p>
            <p className="upload-hint">Extracting text, chunking, embedding</p>
          </div>
        ) : (
          <div className="upload-prompt">
            <div className="upload-icon">📄</div>
            <p className="upload-main">Drop a PDF here or click to browse</p>
            <p className="upload-hint">Max 50 MB · PDF only</p>
          </div>
        )}
      </div>

      {uploadError && (
        <div className="alert alert-error" role="alert">
          ⚠ {uploadError}
        </div>
      )}

      {lastResult && (
        <div className="alert alert-success" role="status">
          ✓ <strong>{lastResult.filename}</strong> ingested —{" "}
          {lastResult.total_pages} pages · {lastResult.chunk_count} chunks
        </div>
      )}
    </div>
  );
}
