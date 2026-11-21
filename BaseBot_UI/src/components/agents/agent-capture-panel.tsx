"use client";

import * as React from "react";
import Link from "next/link";
import {
  ClipboardList,
  Copy,
  Download,
  ExternalLink,
  FileText,
  Plus,
  Trash2,
} from "lucide-react";
import { FieldListEditor } from "@/components/actions/field-list-editor";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { FieldControl } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Toggle } from "@/components/ui/toggle";
import { formatAbsoluteTime } from "@/lib/format";
import { toast } from "@/lib/toast";
import {
  downloadCsv,
  useCollectionSubmissions,
  useCollections,
  useCreateCollection,
  useCreateCustomForm,
  useCustomForms,
  useDeleteCollection,
  useDeleteCustomForm,
  useFormSubmissions,
  useUpdateCollection,
  useUpdateCustomForm,
} from "@/hooks/use-engagement";
import type {
  ActionField,
  CustomForm,
  DataCollection,
  DataSubmission,
  FormSubmission,
} from "@/types/api";

type SubmissionRow = DataSubmission | FormSubmission;

function SubmissionsModal({
  open,
  onClose,
  wsId,
  agentId,
  target,
}: {
  open: boolean;
  onClose: () => void;
  wsId: string;
  agentId: string;
  target: { kind: "collection" | "form"; id: string; name: string } | null;
}) {
  const collectionSubmissions = useCollectionSubmissions(
    wsId,
    agentId,
    target?.kind === "collection" ? target.id : null,
  );
  const formSubmissions = useFormSubmissions(
    wsId,
    agentId,
    target?.kind === "form" ? target.id : null,
  );

  const data = target?.kind === "collection" ? collectionSubmissions : formSubmissions;
  const rows: SubmissionRow[] = React.useMemo(
    () => data.data?.items ?? [],
    [data.data?.items],
  );
  const keys = React.useMemo(() => {
    const found: string[] = [];
    for (const row of rows) {
      for (const key of Object.keys(row.data)) {
        if (!found.includes(key)) found.push(key);
      }
    }
    return found;
  }, [rows]);

  const exportCsv = async () => {
    if (!target) return;
    const path =
      target.kind === "collection"
        ? `/workspaces/${wsId}/agents/${agentId}/collections/${target.id}/export`
        : `/workspaces/${wsId}/agents/${agentId}/forms/${target.id}/export`;
    try {
      await downloadCsv(path, `${target.name.toLowerCase().replace(/\s+/g, "-")}.csv`);
      toast.success({ title: "Submissions exported" });
    } catch {
      toast.error({ title: "Could not export submissions" });
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={target ? `Submissions — ${target.name}` : "Submissions"}
      size="xl"
      footer={
        <div className="flex justify-between gap-3">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void exportCsv()}
            iconLeft={<Download aria-hidden className="h-4 w-4" />}
          >
            Export CSV
          </Button>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      }
    >
      {data.isLoading ? (
        <Skeleton height={160} className="rounded-md" />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          size="sm"
          title="No submissions yet"
          description="Submissions arrive when a visitor completes this form or answers the agent in chat."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-subtle text-2xs uppercase tracking-wide text-tertiary">
                <th className="py-2 pr-3 font-medium">Received</th>
                {keys.map((key) => (
                  <th key={key} className="py-2 pr-3 font-medium">
                    {key.replace(/_/g, " ")}
                  </th>
                ))}
                <th className="py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-subtle/60 align-top">
                  <td className="whitespace-nowrap py-2 pr-3 text-xs text-tertiary">
                    {formatAbsoluteTime(row.created_at)}
                  </td>
                  {keys.map((key) => (
                    <td key={key} className="max-w-[220px] py-2 pr-3 text-xs text-secondary">
                      {String(row.data[key] ?? "—")}
                    </td>
                  ))}
                  <td className="py-2">
                    <Badge tone={row.status === "complete" ? "success" : "warning"}>
                      {row.status}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}

export function AgentCapturePanel({
  wsId,
  agentId,
}: {
  wsId: string;
  agentId: string;
}) {
  const collections = useCollections(wsId, agentId);
  const forms = useCustomForms(wsId, agentId);
  const createCollection = useCreateCollection(wsId, agentId);
  const updateCollection = useUpdateCollection(wsId, agentId);
  const deleteCollection = useDeleteCollection(wsId, agentId);
  const createForm = useCreateCustomForm(wsId, agentId);
  const updateForm = useUpdateCustomForm(wsId, agentId);
  const deleteForm = useDeleteCustomForm(wsId, agentId);

  const [section, setSection] = React.useState<"collections" | "forms">("collections");
  const [collectionModal, setCollectionModal] = React.useState<
    DataCollection | "new" | null
  >(null);
  const [formModal, setFormModal] = React.useState<CustomForm | "new" | null>(null);
  const [submissionsTarget, setSubmissionsTarget] = React.useState<{
    kind: "collection" | "form";
    id: string;
    name: string;
  } | null>(null);
  const [pendingDelete, setPendingDelete] = React.useState<
    { kind: "collection" | "form"; id: string; name: string } | null
  >(null);

  // Collection form state
  const [collectionName, setCollectionName] = React.useState("");
  const [collectionDescription, setCollectionDescription] = React.useState("");
  const [collectionFields, setCollectionFields] = React.useState<ActionField[]>([]);
  const [collectionPartial, setCollectionPartial] = React.useState(false);
  const [collectionConsent, setCollectionConsent] = React.useState(false);

  // Form state
  const [formTitle, setFormTitle] = React.useState("");
  const [formDescription, setFormDescription] = React.useState("");
  const [formSubmitLabel, setFormSubmitLabel] = React.useState("Submit");
  const [formFields, setFormFields] = React.useState<ActionField[]>([]);
  const [formConsent, setFormConsent] = React.useState(true);
  const [formActive, setFormActive] = React.useState(true);

  React.useEffect(() => {
    if (collectionModal === "new" || collectionModal === null) {
      if (collectionModal === "new") {
        setCollectionName("");
        setCollectionDescription("");
        setCollectionFields([]);
        setCollectionPartial(false);
        setCollectionConsent(false);
      }
      return;
    }
    setCollectionName(collectionModal.name);
    setCollectionDescription(collectionModal.description ?? "");
    setCollectionFields(collectionModal.fields);
    setCollectionPartial(Boolean(collectionModal.allow_partial));
    setCollectionConsent(Boolean(collectionModal.require_consent));
  }, [collectionModal]);

  React.useEffect(() => {
    if (formModal === "new") {
      setFormTitle("");
      setFormDescription("");
      setFormSubmitLabel("Submit");
      setFormFields([]);
      setFormConsent(true);
      setFormActive(true);
      return;
    }
    if (!formModal) return;
    setFormTitle(formModal.title);
    setFormDescription(formModal.description ?? "");
    setFormSubmitLabel(formModal.submit_label);
    setFormFields(formModal.fields);
    setFormConsent(Boolean(formModal.require_consent));
    setFormActive(Boolean(formModal.is_active));
  }, [formModal]);

  const saveCollection = async () => {
    const body = {
      name: collectionName.trim(),
      description: collectionDescription.trim() || null,
      fields: collectionFields,
      allow_partial: collectionPartial,
      require_consent: collectionConsent,
    };
    try {
      if (collectionModal === "new") {
        await createCollection.mutateAsync(body);
        toast.success({ title: "Collection created" });
      } else if (collectionModal) {
        await updateCollection.mutateAsync({ id: collectionModal.id, body });
        toast.success({ title: "Collection updated" });
      }
      setCollectionModal(null);
    } catch (error) {
      const detail = (error as { body?: { detail?: string } })?.body?.detail;
      toast.error({ title: typeof detail === "string" ? detail : "Could not save the collection" });
    }
  };

  const saveForm = async () => {
    const body = {
      title: formTitle.trim(),
      description: formDescription.trim() || null,
      fields: formFields,
      submit_label: formSubmitLabel.trim() || "Submit",
      require_consent: formConsent,
      is_active: formActive,
    };
    try {
      if (formModal === "new") {
        await createForm.mutateAsync(body);
        toast.success({ title: "Form created" });
      } else if (formModal) {
        await updateForm.mutateAsync({ id: formModal.id, body });
        toast.success({ title: "Form updated" });
      }
      setFormModal(null);
    } catch (error) {
      const detail = (error as { body?: { detail?: string } })?.body?.detail;
      toast.error({ title: typeof detail === "string" ? detail : "Could not save the form" });
    }
  };

  const remove = async () => {
    if (!pendingDelete) return;
    try {
      if (pendingDelete.kind === "collection") {
        await deleteCollection.mutateAsync(pendingDelete.id);
      } else {
        await deleteForm.mutateAsync(pendingDelete.id);
      }
      toast.success({ title: "Deleted" });
      setPendingDelete(null);
    } catch {
      toast.error({ title: "Could not delete this item" });
    }
  };

  const copyPublicLink = async (form: CustomForm) => {
    const url = `${window.location.origin}/forms/${form.public_token}`;
    try {
      await navigator.clipboard.writeText(url);
      toast.success({ title: "Public form link copied" });
    } catch {
      toast.error({ title: "Could not copy the link", description: url });
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-medium text-primary">Capture</h1>
          <p className="mt-1 max-w-2xl text-sm text-secondary">
            Collect structured answers with reusable data collections, or publish a
            standalone form with its own public link. Both are stored against this
            agent and can be exported as CSV.
          </p>
        </div>
        <Button
          size="sm"
          onClick={() =>
            section === "collections"
              ? setCollectionModal("new")
              : setFormModal("new")
          }
          iconLeft={<Plus aria-hidden className="h-4 w-4" />}
        >
          {section === "collections" ? "New collection" : "New form"}
        </Button>
      </div>

      <div
        role="tablist"
        aria-label="Capture sections"
        className="flex flex-wrap gap-1 border-b border-subtle"
      >
        {[
          { id: "collections" as const, label: "Data collections" },
          { id: "forms" as const, label: "Custom forms" },
        ].map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={section === item.id}
            onClick={() => setSection(item.id)}
            className={
              section === item.id
                ? "border-b-2 border-accent-500 px-3 py-2 text-sm font-medium text-primary"
                : "border-b-2 border-transparent px-3 py-2 text-sm text-tertiary hover:text-primary"
            }
          >
            {item.label}
          </button>
        ))}
      </div>

      {section === "collections" && (
        <>
          {collections.isError ? (
            <AlertBanner tone="danger" title="Collections could not be loaded">
              {collections.error instanceof Error ? collections.error.message : "Please try again."}
            </AlertBanner>
          ) : collections.isLoading ? (
            <Skeleton height={140} className="rounded-md" />
          ) : (collections.data?.length ?? 0) === 0 ? (
            <EmptyState
              icon={ClipboardList}
              title="No data collections"
              description="Create a collection to define the questions the agent asks and the answers it stores."
              actionLabel="Create a collection"
              onAction={() => setCollectionModal("new")}
            />
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {collections.data?.map((collection) => (
                <section
                  key={collection.id}
                  className="flex flex-col gap-3 rounded-md border border-subtle bg-surface p-5 shadow-elevation-1"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h2 className="text-base font-medium text-primary">{collection.name}</h2>
                      <p className="mt-1 text-sm text-secondary">
                        {collection.description || "No description"}
                      </p>
                    </div>
                    <Badge tone={collection.is_active ? "success" : "neutral"}>
                      {collection.is_active ? "Active" : "Disabled"}
                    </Badge>
                  </div>
                  <div className="flex flex-wrap gap-2 text-2xs text-tertiary">
                    <Badge tone="neutral">{collection.fields.length} fields</Badge>
                    <Badge tone="neutral">{collection.submission_count} submissions</Badge>
                    {Boolean(collection.require_consent) && (
                      <Badge tone="info">Consent required</Badge>
                    )}
                  </div>
                  <div className="mt-auto flex flex-wrap gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() =>
                        setSubmissionsTarget({
                          kind: "collection",
                          id: collection.id,
                          name: collection.name,
                        })
                      }
                    >
                      View submissions
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setCollectionModal(collection)}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="dangerGhost"
                      size="sm"
                      onClick={() =>
                        setPendingDelete({
                          kind: "collection",
                          id: collection.id,
                          name: collection.name,
                        })
                      }
                      iconLeft={<Trash2 aria-hidden className="h-4 w-4" />}
                    >
                      Delete
                    </Button>
                  </div>
                </section>
              ))}
            </div>
          )}
        </>
      )}

      {section === "forms" && (
        <>
          {forms.isError ? (
            <AlertBanner tone="danger" title="Forms could not be loaded">
              {forms.error instanceof Error ? forms.error.message : "Please try again."}
            </AlertBanner>
          ) : forms.isLoading ? (
            <Skeleton height={140} className="rounded-md" />
          ) : (forms.data?.length ?? 0) === 0 ? (
            <EmptyState
              icon={FileText}
              title="No custom forms"
              description="Publish a form with its own shareable link. Submissions land in your dashboard and can be exported."
              actionLabel="Create a form"
              onAction={() => setFormModal("new")}
            />
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {forms.data?.map((form) => (
                <section
                  key={form.id}
                  className="flex flex-col gap-3 rounded-md border border-subtle bg-surface p-5 shadow-elevation-1"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h2 className="text-base font-medium text-primary">{form.title}</h2>
                      <p className="mt-1 text-sm text-secondary">
                        {form.description || "No description"}
                      </p>
                    </div>
                    <Badge tone={form.is_active ? "success" : "neutral"}>
                      {form.is_active ? "Published" : "Draft"}
                    </Badge>
                  </div>
                  <div className="flex flex-wrap gap-2 text-2xs">
                    <Badge tone="neutral">{form.fields.length} fields</Badge>
                    <Badge tone="neutral">{form.submission_count} responses</Badge>
                    {Boolean(form.require_consent) && (
                      <Badge tone="info">Consent required</Badge>
                    )}
                  </div>
                  <div className="mt-auto flex flex-wrap gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() =>
                        setSubmissionsTarget({
                          kind: "form",
                          id: form.id,
                          name: form.title,
                        })
                      }
                    >
                      View responses
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void copyPublicLink(form)}
                      iconLeft={<Copy aria-hidden className="h-4 w-4" />}
                    >
                      Copy link
                    </Button>
                    <Button asChild variant="ghost" size="sm">
                      <Link
                        href={`/forms/${form.public_token}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <ExternalLink aria-hidden className="h-4 w-4" />
                        Preview
                      </Link>
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setFormModal(form)}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="dangerGhost"
                      size="sm"
                      onClick={() =>
                        setPendingDelete({
                          kind: "form",
                          id: form.id,
                          name: form.title,
                        })
                      }
                      iconLeft={<Trash2 aria-hidden className="h-4 w-4" />}
                    >
                      Delete
                    </Button>
                  </div>
                </section>
              ))}
            </div>
          )}
        </>
      )}

      {/* Collection editor */}
      <Modal
        open={collectionModal !== null}
        onClose={() => setCollectionModal(null)}
        title={collectionModal === "new" ? "New data collection" : "Edit data collection"}
        size="lg"
        footer={
          <div className="flex justify-end gap-3">
            <Button variant="secondary" size="sm" onClick={() => setCollectionModal(null)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => void saveCollection()}
              loading={createCollection.isPending || updateCollection.isPending}
            >
              Save collection
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          <FieldControl label="Name" required>
            <Input
              value={collectionName}
              onChange={(event) => setCollectionName(event.target.value)}
              maxLength={120}
            />
          </FieldControl>
          <FieldControl label="Description">
            <Textarea
              value={collectionDescription}
              onChange={(event) => setCollectionDescription(event.target.value)}
              rows={2}
              maxLength={1000}
            />
          </FieldControl>
          <div className="flex flex-wrap gap-5">
            <label className="flex items-center gap-2 text-xs text-secondary">
              <input
                type="checkbox"
                checked={collectionPartial}
                onChange={(event) => setCollectionPartial(event.target.checked)}
                className="h-4 w-4 accent-accent-500"
              />
              Allow partial submissions
            </label>
            <label className="flex items-center gap-2 text-xs text-secondary">
              <input
                type="checkbox"
                checked={collectionConsent}
                onChange={(event) => setCollectionConsent(event.target.checked)}
                className="h-4 w-4 accent-accent-500"
              />
              Require consent
            </label>
          </div>
          <FieldListEditor fields={collectionFields} onChange={setCollectionFields} />
        </div>
      </Modal>

      {/* Form editor */}
      <Modal
        open={formModal !== null}
        onClose={() => setFormModal(null)}
        title={formModal === "new" ? "New custom form" : "Edit custom form"}
        size="lg"
        footer={
          <div className="flex justify-end gap-3">
            <Button variant="secondary" size="sm" onClick={() => setFormModal(null)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => void saveForm()}
              loading={createForm.isPending || updateForm.isPending}
            >
              Save form
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          <FieldControl label="Title" required>
            <Input
              value={formTitle}
              onChange={(event) => setFormTitle(event.target.value)}
              maxLength={160}
            />
          </FieldControl>
          <FieldControl label="Description">
            <Textarea
              value={formDescription}
              onChange={(event) => setFormDescription(event.target.value)}
              rows={2}
              maxLength={2000}
            />
          </FieldControl>
          <div className="grid gap-4 sm:grid-cols-2">
            <FieldControl label="Submit button label">
              <Input
                value={formSubmitLabel}
                onChange={(event) => setFormSubmitLabel(event.target.value)}
                maxLength={60}
              />
            </FieldControl>
            <div className="flex items-end gap-6 pb-2">
              <label className="flex items-center gap-2 text-xs text-secondary">
                <input
                  type="checkbox"
                  checked={formConsent}
                  onChange={(event) => setFormConsent(event.target.checked)}
                  className="h-4 w-4 accent-accent-500"
                />
                Require consent
              </label>
              <div className="flex items-center gap-2">
                <Toggle
                  checked={formActive}
                  onCheckedChange={setFormActive}
                  label="Published"
                  size="sm"
                />
                <span className="text-xs text-secondary">Published</span>
              </div>
            </div>
          </div>
          <FieldListEditor fields={formFields} onChange={setFormFields} />
        </div>
      </Modal>

      <SubmissionsModal
        open={submissionsTarget !== null}
        onClose={() => setSubmissionsTarget(null)}
        wsId={wsId}
        agentId={agentId}
        target={submissionsTarget}
      />

      <ConfirmationDialog
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title={`Delete ${pendingDelete?.kind === "collection" ? "collection" : "form"}?`}
        body={
          <>
            <strong className="font-medium text-primary">{pendingDelete?.name}</strong>{" "}
            and all of its submissions will be permanently deleted. This cannot be
            undone.
          </>
        }
        confirmLabel="Delete"
        confirmLoading={deleteCollection.isPending || deleteForm.isPending}
        onConfirm={() => void remove()}
      />
    </div>
  );
}
