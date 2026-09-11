/**
 * components/DocumentList.tsx
 * Shows ingested documents with status badges and delete buttons.
 */
import React from "react";
import type { Document } from "../types";

interface DocumentListProps {
  documents: Document[];
  onDelete: (id: string) => void;
  selectedId?: string;
  onSelect: (id: string | undefined) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function StatusBadge({ status }: { status: Document["status"] }) {
  const map = {
    ready:      { label: "Ready",      cls: "badge-ready"      },
    processing: { label: "Processing", cls: "badge-processing" },
    error:      { label: "Error",      cls: "badge-error"      },
  };
  const { label, cls } = map[status];
  return <span className={`badge ${cls}`}>{label}</span>;
}

export function DocumentList({ documents, onDelete, selectedId, onSelect }: DocumentListProps) {
  if (documents.length === 0) {
    return <p className="empty-state">No documents yet. Upload a PDF above.</p>;
  }

  return (
    <ul className="doc-list" role="listbox" aria-label="Documents">
      {documents.map((doc) => (
        <li
          key={doc.id}
          className={`doc-item ${doc.id === selectedId ? "selected" : ""}`}
          onClick={() => onSelect(doc.id === selectedId ? undefined : doc.id)}
          role="option"
          aria-selected={doc.id === selectedId}
          tabIndex={0}
          onKeyDown={(e) => e.key === "Enter" && onSelect(doc.id === selectedId ? undefined : doc.id)}
        >
          <div className="doc-info">
            <span className="doc-name" title={doc.filename}>{doc.filename}</span>
            <div className="doc-meta">
              <StatusBadge status={doc.status} />
              <span className="doc-stat">{doc.total_pages} pages</span>
              <span className="doc-stat">{formatBytes(doc.file_size)}</span>
            </div>
          </div>
          <button
            className="btn-icon btn-delete"
            onClick={(e) => { e.stopPropagation(); onDelete(doc.id); }}
            aria-label={`Delete ${doc.filename}`}
            title="Delete document"
          >
            ✕
          </button>
        </li>
      ))}
    </ul>
  );
}
