/**
 * App.tsx
 * Root component — two-panel layout: sidebar (docs) + main (chat).
 */
import React, { useState } from "react";
import { ChatInput } from "./components/ChatInput";
import { ChatWindow } from "./components/ChatWindow";
import { DocumentList } from "./components/DocumentList";
import { FileUploader } from "./components/FileUploader";
import { useChat } from "./hooks/useChat";
import { useDocuments } from "./hooks/useDocuments";
import "./styles.css";

export default function App() {
  const [selectedDocId, setSelectedDocId] = useState<string | undefined>();
  const { documents, isLoading: docsLoading, isUploading, upload, remove } = useDocuments();
  const { messages, isLoading: chatLoading, error, sendMessage, cancelStream, clearChat } =
    useChat({ documentId: selectedDocId });

  const handleDocSelect = (id: string | undefined) => {
    setSelectedDocId(id);
    clearChat();
  };

  return (
    <div className="app-layout">
      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <header className="sidebar-header">
          <h1 className="app-title">
            <span className="app-title-icon">🔍</span>
            RAG Citations
          </h1>
          <p className="app-subtitle">Ask questions. Get cited answers.</p>
        </header>

        <section className="sidebar-section">
          <h2 className="section-title">Upload Document</h2>
          <FileUploader onUpload={upload} isUploading={isUploading} />
        </section>

        <section className="sidebar-section sidebar-docs">
          <div className="section-header-row">
            <h2 className="section-title">Documents</h2>
            {docsLoading && <span className="spinner-sm" />}
          </div>
          <DocumentList
            documents={documents}
            onDelete={remove}
            selectedId={selectedDocId}
            onSelect={handleDocSelect}
          />
        </section>

        {selectedDocId && (
          <div className="sidebar-selected-hint">
            ✓ Querying selected document only
          </div>
        )}
      </aside>

      {/* ── Main Chat Area ── */}
      <main className="chat-main">
        <div className="chat-toolbar">
          <span className="chat-toolbar-title">
            {selectedDocId
              ? `📄 ${documents.find((d) => d.id === selectedDocId)?.filename ?? "Selected document"}`
              : "All documents"}
          </span>
          {messages.length > 0 && (
            <button className="btn btn-ghost" onClick={clearChat}>
              Clear chat
            </button>
          )}
        </div>

        {error && (
          <div className="alert alert-error" role="alert">
            ⚠ {error}
          </div>
        )}

        <ChatWindow messages={messages} isLoading={chatLoading} />

        <ChatInput
          onSend={sendMessage}
          onCancel={cancelStream}
          isLoading={chatLoading}
          disabled={documents.filter((d) => d.status === "ready").length === 0}
        />
      </main>
    </div>
  );
}
