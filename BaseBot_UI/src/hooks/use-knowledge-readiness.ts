"use client";

import * as React from "react";
import { useDocuments } from "./use-documents";
import { useWebsiteSources } from "./use-websites";

/**
 * An agent can be created once either an uploaded document or an indexed
 * website page is available. The two APIs are separate, so readiness lives in
 * one hook rather than being re-derived (and forgotten) per page.
 */
export function useKnowledgeReadiness(wsId: string | undefined) {
  const documents = useDocuments(wsId);
  const websites = useWebsiteSources(wsId);

  const readyDocumentCount = (documents.data ?? []).filter(
    (document) => document.status === "ready",
  ).length;
  const indexedWebsitePages = (websites.data ?? []).reduce(
    (total, source) => total + source.pages_indexed,
    0,
  );

  const hasReadyKnowledge = readyDocumentCount > 0 || indexedWebsitePages > 0;
  const isLoading = documents.isLoading || websites.isLoading;

  return React.useMemo(
    () => ({
      documents,
      websites,
      readyDocumentCount,
      indexedWebsitePages,
      hasReadyKnowledge,
      isLoading,
    }),
    [
      documents,
      websites,
      readyDocumentCount,
      indexedWebsitePages,
      hasReadyKnowledge,
      isLoading,
    ],
  );
}
