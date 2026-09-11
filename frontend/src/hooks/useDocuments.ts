/**
 * hooks/useDocuments.ts
 * Document list state — fetch, upload, delete.
 */
import { useCallback, useEffect, useState } from "react";
import { deleteDocument, listDocuments, uploadDocument } from "../api/client";
import type { Document, UploadResponse } from "../types";

export function useDocuments() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDocuments = useCallback(async () => {
    setIsLoading(true);
    try {
      const docs = await listDocuments();
      setDocuments(docs);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const upload = useCallback(
    async (file: File): Promise<UploadResponse> => {
      setIsUploading(true);
      setError(null);
      try {
        const result = await uploadDocument(file);
        await fetchDocuments(); // Refresh list
        return result;
      } catch (err) {
        setError((err as Error).message);
        throw err;
      } finally {
        setIsUploading(false);
      }
    },
    [fetchDocuments]
  );

  const remove = useCallback(
    async (id: string) => {
      try {
        await deleteDocument(id);
        setDocuments((prev) => prev.filter((d) => d.id !== id));
      } catch (err) {
        setError((err as Error).message);
      }
    },
    []
  );

  return {
    documents,
    isLoading,
    isUploading,
    error,
    upload,
    remove,
    refresh: fetchDocuments,
  };
}
