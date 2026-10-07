"use client";

import * as React from "react";
import { ApiRequestError } from "@/lib/api-client";
import { normaliseError } from "@/lib/api-error";
import { MAX_FILE_SIZE_MB } from "@/lib/constants";
import { toast } from "@/lib/toast";
import { validateFile } from "@/schemas/document";
import { AlertBanner } from "@/components/ui/alert-banner";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { ErrorPanel } from "@/components/common/error-panel";
import { FileUploadZone } from "./file-upload-zone";
import {
  DocumentTable,
  DocumentsEmptyState,
  type PendingUpload,
} from "./document-table";
import {
  useDeleteDocument,
  useDocuments,
  usePatchDocumentStatus,
  useTrainDocument,
  useUploadDocument,
} from "@/hooks/use-documents";
import { useTrainingPoll } from "@/hooks/use-training-poll";
import type { WorkspaceDocument } from "@/types/api";

export function DocumentsPanel({ wsId }: { wsId: string }) {
  const query = useDocuments(wsId);
  const upload = useUploadDocument(wsId);
  const train = useTrainDocument(wsId);
  const remove = useDeleteDocument(wsId);
  const patchStatus = usePatchDocumentStatus(wsId);

  const [pending, setPending] = React.useState<PendingUpload[]>([]);
  const [rejections, setRejections] = React.useState<
    { name: string; message: string }[]
  >([]);
  const [pendingDelete, setPendingDelete] = React.useState<WorkspaceDocument | null>(
    null,
  );
  const [bulkBusy, setBulkBusy] = React.useState(false);

  const documents = query.data;

  // One poller for every non-terminal document. Terminal transitions emit a
  // single toast each, emitted here rather than by the poll loop.
  const { timedOutIds } = useTrainingPoll({
    wsId,
    documents,
    onUpdate: (docId, status, chunkCount) => {
      patchStatus(docId, { status, chunk_count: chunkCount });
    },
    onComplete: (docId, chunkCount) => {
      patchStatus(docId, { status: "ready" });
      toast.success({
        title: "Training complete",
        description: `${chunkCount} chunks indexed.`,
        id: `training-${docId}`,
      });
      void query.refetch();
    },
    onFailed: () => {
      toast.error({
        title: "Training failed. Check the file and retry.",
        id: "training-failed",
      });
      void query.refetch();
    },
    onRemoved: () => {
      toast.warning({ title: "A document was removed elsewhere" });
      void query.refetch();
    },
    onTimeout: () => {
      toast.warning({
        title: "Taking longer than expected",
        description: "Check back shortly — we stopped watching for you.",
        id: "training-slow",
      });
    },
  });

  const documents_ = documents ?? [];
  const trainingCount = documents_.filter((d) => d.status === "processing").length;

  const handleFiles = async (files: File[]) => {
    const rejected: { name: string; message: string }[] = [];
    const accepted: File[] = [];

    for (const file of files) {
      const result = validateFile(file, MAX_FILE_SIZE_MB);
      if (result.ok) accepted.push(file);
      else rejected.push({ name: file.name, message: result.message });
    }

    if (rejected.length > 0) setRejections(rejected);
    if (accepted.length === 0) return;

    setBulkBusy(true);
    try {
      // Sequential by design: one upload at a time keeps progress legible.
      for (const file of accepted) {
        const localId = `${file.name}-${file.size}-${Date.now()}`;
        setPending((rows) => [
          ...rows,
          { localId, filename: file.name, sizeBytes: file.size, state: "uploading" },
        ]);

        try {
          await upload.mutateAsync(file);
          setPending((rows) => rows.filter((row) => row.localId !== localId));
        } catch (error) {
          if (error instanceof ApiRequestError && error.status === 404) {
            setPending((rows) => rows.filter((row) => row.localId !== localId));
            toast.error({ title: "Workspace not found." });
            return;
          }
          const message =
            error instanceof ApiRequestError
              ? normaliseError(error.body, error.status).message
              : "Cannot reach the server.";
          setPending((rows) =>
            rows.map((row) =>
              row.localId === localId ? { ...row, state: "failed", error: message } : row,
            ),
          );
        }
      }
      void query.refetch();
    } finally {
      setBulkBusy(false);
    }
  };

  const handleTrain = async (document: WorkspaceDocument) => {
    try {
      await train.mutateAsync(document.id);
      void query.refetch();
    } catch {
      toast.error({
        title: "Could not start training",
        description: "Try again in a moment.",
      });
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    try {
      await remove.mutateAsync(pendingDelete.id);
      toast.success({ title: "Document deleted" });
      setPendingDelete(null);
    } catch {
      toast.error({ title: "Could not delete the document" });
    }
  };

  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  const openPicker = () => fileInputRef.current?.click();

  if (query.isError) {
    return (
      <ErrorPanel
        title="We could not load your documents"
        statusCode={(query.error as { status?: number })?.status}
        onRetry={() => void query.refetch()}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {trainingCount > 0 && (
        <AlertBanner tone="info">
          {trainingCount} document{trainingCount === 1 ? "" : "s"} training…
          You can leave this page — training continues on the server.
        </AlertBanner>
      )}

      <div>
        <FileUploadZone
          inputRef={fileInputRef}
          onFiles={(files) => void handleFiles(files)}
          uploadingCount={pending.filter((row) => row.state === "uploading").length}
          rejections={rejections}
          onDismissRejection={(index) =>
            setRejections((rows) => rows.filter((_, i) => i !== index))
          }
        />
      </div>

      <DocumentTable
        documents={documents_}
        pending={pending}
        onCancelPending={(localId) =>
          setPending((rows) => rows.filter((row) => row.localId !== localId))
        }
        onDelete={(document) => setPendingDelete(document)}
        onTrain={(document) => void handleTrain(document)}
        retryingIds={
          train.isPending && train.variables ? [train.variables] : []
        }
        slowIds={timedOutIds}
        loading={query.isLoading}
        emptyState={<DocumentsEmptyState onUpload={openPicker} />}
      />

      <ConfirmationDialog
        open={Boolean(pendingDelete)}
        onClose={() => setPendingDelete(null)}
        title="Delete document?"
        body={
          pendingDelete ? (
            <p>
              This removes{" "}
              <strong className="font-medium text-primary">
                {pendingDelete.filename}
              </strong>{" "}
              and everything extracted from it. The agent will no longer be able
              to answer questions using this document. This cannot be undone.
            </p>
          ) : null
        }
        confirmLabel="Delete document"
        confirmLoading={remove.isPending}
        onConfirm={() => void confirmDelete()}
      />

      {bulkBusy && <span className="sr-only">Uploading files</span>}
    </div>
  );
}