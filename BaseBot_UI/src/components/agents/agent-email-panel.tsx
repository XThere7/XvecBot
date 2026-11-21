"use client";

import * as React from "react";
import Link from "next/link";
import {
  Inbox,
  Mail,
  MessageSquare,
  Send,
  Settings2,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { FieldControl } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/ui/stat-card";
import { Textarea } from "@/components/ui/textarea";
import { Toggle } from "@/components/ui/toggle";
import { formatAbsoluteTime } from "@/lib/format";
import { workspaceHref } from "@/lib/routes";
import { toast } from "@/lib/toast";
import { useBilling } from "@/hooks/use-billing";
import {
  useApproveEmailDraft,
  useDeleteEmailIntegration,
  useEmailDrafts,
  useEmailOverview,
  useRejectEmailDraft,
  useSaveEmailIntegration,
  useSimulateEmail,
  useUpdateEmailDraft,
} from "@/hooks/use-engagement";
import type { EmailDraft, EmailProvider } from "@/types/api";

const PROVIDERS: { value: EmailProvider; label: string }[] = [
  { value: "simulated", label: "Simulated mailbox (recommended for evaluation)" },
  { value: "imap", label: "IMAP mailbox" },
  { value: "gmail_oauth", label: "Gmail (OAuth — setup only)" },
  { value: "microsoft_oauth", label: "Microsoft 365 (OAuth — setup only)" },
];

const STATUS_TONE: Record<string, "neutral" | "info" | "success" | "warning" | "danger"> = {
  draft_ready: "info",
  processing: "warning",
  approved: "success",
  sent: "success",
  rejected: "neutral",
  failed: "danger",
  received: "info",
  drafted: "info",
  filtered: "neutral",
};

function statusLabel(status: string): string {
  return status.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function AgentEmailPanel({
  wsId,
  agentId,
}: {
  wsId: string;
  agentId: string;
}) {
  const overview = useEmailOverview(wsId, agentId);
  const billing = useBilling(wsId);
  const saveIntegration = useSaveEmailIntegration(wsId, agentId);
  const deleteIntegration = useDeleteEmailIntegration(wsId, agentId);
  const simulate = useSimulateEmail(wsId, agentId);
  const drafts = useEmailDrafts(wsId, agentId, "");
  const updateDraft = useUpdateEmailDraft(wsId, agentId);
  const approveDraft = useApproveEmailDraft(wsId, agentId);
  const rejectDraft = useRejectEmailDraft(wsId, agentId);

  const integration = overview.data?.integration ?? null;
  const featureEnabled = billing.data?.plan.features.email_integration ?? true;

  const [provider, setProvider] = React.useState<EmailProvider>("simulated");
  const [emailAddress, setEmailAddress] = React.useState("");
  const [displayName, setDisplayName] = React.useState("");
  const [automation, setAutomation] = React.useState(true);
  const [notificationPhone, setNotificationPhone] = React.useState("");
  const [ignoreSenders, setIgnoreSenders] = React.useState("");
  const [subjectKeywords, setSubjectKeywords] = React.useState("");
  const [imapUsername, setImapUsername] = React.useState("");
  const [imapPassword, setImapPassword] = React.useState("");
  const [editing, setEditing] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState(false);

  const [senderName, setSenderName] = React.useState("John Customer");
  const [senderEmail, setSenderEmail] = React.useState("john@example.com");
  const [subject, setSubject] = React.useState("Product inquiry");
  const [bodyText, setBodyText] = React.useState(
    "Hello, I would like to know your pricing and delivery options.",
  );

  const [reviewing, setReviewing] = React.useState<EmailDraft | null>(null);
  const [draftBody, setDraftBody] = React.useState("");
  const [confirmSend, setConfirmSend] = React.useState(false);
  const [rejecting, setRejecting] = React.useState(false);

  React.useEffect(() => {
    if (!integration) return;
    setProvider(integration.provider);
    setEmailAddress(integration.email_address);
    setDisplayName(integration.display_name ?? "");
    setAutomation(Boolean(integration.automation_enabled));
    setNotificationPhone(integration.notification_phone ?? "");
    setIgnoreSenders(
      Array.isArray(integration.filters.ignore_senders)
        ? (integration.filters.ignore_senders as string[]).join(", ")
        : "",
    );
    setSubjectKeywords(
      Array.isArray(integration.filters.subject_keywords)
        ? (integration.filters.subject_keywords as string[]).join(", ")
        : "",
    );
  }, [integration]);

  const openReview = (draft: EmailDraft) => {
    setReviewing(draft);
    setDraftBody(draft.body);
    setConfirmSend(false);
    setRejecting(false);
  };

  const saveConfig = async () => {
    try {
      await saveIntegration.mutateAsync({
        provider,
        email_address: emailAddress,
        display_name: displayName || null,
        automation_enabled: automation,
        notification_phone: notificationPhone || null,
        filters: {
          ignore_senders: ignoreSenders
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
          subject_keywords: subjectKeywords
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
        },
        imap_username: imapUsername || null,
        imap_password: imapPassword || null,
      });
      setEditing(false);
      setImapPassword("");
      toast.success({ title: "Email Agent settings saved" });
    } catch (error) {
      const detail = (error as { body?: { detail?: unknown } })?.body?.detail;
      const message =
        typeof detail === "string"
          ? detail
          : (detail as { message?: string } | undefined)?.message;
      toast.error({ title: message || "Could not save the mailbox settings" });
    }
  };

  const runSimulation = async () => {
    try {
      const result = await simulate.mutateAsync({
        sender_name: senderName,
        sender_email: senderEmail,
        subject,
        body_text: bodyText,
      });
      if (result.duplicate) {
        toast.info({ title: "This email was already processed" });
      } else if (result.draft?.status === "draft_ready") {
        toast.success({
          title: "Incoming email processed",
          description: "An AI draft was created and a simulated SMS alert was stored.",
        });
      } else {
        toast.warning({
          title: "Email received, draft needs attention",
          description: "Open the draft and write the reply manually.",
        });
      }
    } catch (error) {
      const detail = (error as { body?: { detail?: unknown } })?.body?.detail;
      toast.error({
        title:
          typeof detail === "string"
            ? detail
            : "Could not process the simulated email",
      });
    }
  };

  const saveDraft = async () => {
    if (!reviewing) return;
    try {
      const updated = await updateDraft.mutateAsync({
        id: reviewing.id,
        body: draftBody,
      });
      setReviewing(updated);
      toast.success({ title: "Draft saved" });
    } catch {
      toast.error({ title: "Could not save the draft" });
    }
  };

  const approve = async () => {
    if (!reviewing) return;
    try {
      await approveDraft.mutateAsync({
        id: reviewing.id,
        body: draftBody,
        confirmSimulatedSend: confirmSend,
      });
      toast.success({
        title: "Reply approved — send simulated",
        description: "No real email was sent. The record is marked Sent (simulated).",
      });
      setReviewing(null);
    } catch (error) {
      const detail = (error as { body?: { detail?: unknown } })?.body?.detail;
      toast.error({
        title:
          typeof detail === "string" ? detail : "Could not approve this draft",
      });
    }
  };

  const reject = async () => {
    if (!reviewing) return;
    try {
      await rejectDraft.mutateAsync({ id: reviewing.id, reason: "Rejected by owner" });
      toast.success({ title: "Draft rejected" });
      setReviewing(null);
    } catch {
      toast.error({ title: "Could not reject the draft" });
    }
  };

  const removeIntegration = async () => {
    try {
      await deleteIntegration.mutateAsync();
      setConfirmDelete(false);
      toast.success({ title: "Mailbox removed and credentials deleted" });
    } catch {
      toast.error({ title: "Could not remove the mailbox" });
    }
  };

  const stats = overview.data?.stats;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-medium text-primary">Email Agent</h1>
          <p className="mt-1 max-w-2xl text-sm text-secondary">
            Turn incoming email into a reviewed reply. The AI drafts from your
            knowledge base, the owner approves, and the reply is marked as sent
            only in simulation.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone="warning" icon={<Send aria-hidden className="h-3.5 w-3.5" />}>
            Sending simulated
          </Badge>
          <Badge tone="info" icon={<MessageSquare aria-hidden className="h-3.5 w-3.5" />}>
            SMS simulated
          </Badge>
        </div>
      </div>

      {!featureEnabled && (
        <AlertBanner
          tone="warning"
          title="Standard plan required"
          action={
            <Button asChild variant="secondary" size="sm">
              <Link href={workspaceHref(wsId, "billing")}>View plans</Link>
            </Button>
          }
        >
          The Email Agent is included in Standard and Pro. You can review the setup,
          but saving a mailbox will be blocked by the backend until the workspace is
          upgraded.
        </AlertBanner>
      )}

      <AlertBanner tone="info" title="What is real and what is simulated">
        Message ingestion, AI drafting, storage, approvals and the audit trail are
        real. SMS delivery and outbound email are simulated: no message leaves this
        server. Approved replies are labelled <strong>Sent (simulated)</strong>.
      </AlertBanner>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Emails received" value={stats?.incoming_total ?? 0} loading={overview.isLoading} icon={Inbox} />
        <StatCard label="Awaiting review" value={stats?.awaiting_approval ?? 0} loading={overview.isLoading} icon={Mail} />
        <StatCard label="Sent (simulated)" value={stats?.sent_simulated ?? 0} loading={overview.isLoading} />
        <StatCard label="Failed drafts" value={stats?.failed ?? 0} loading={overview.isLoading} />
      </div>

      {/* Configuration */}
      <section className="rounded-md border border-subtle bg-surface p-5 shadow-elevation-1">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-medium text-primary">Mailbox setup</h2>
            <p className="mt-1 text-sm text-secondary">
              {integration
                ? `${integration.email_address} · ${statusLabel(integration.status)}`
                : "Connect a mailbox to receive email. In evaluation, the simulated mailbox is fully functional."}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {integration && (
              <Badge tone={integration.has_credentials ? "success" : "neutral"}>
                {integration.has_credentials ? "Credentials stored encrypted" : "No credentials stored"}
              </Badge>
            )}
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setEditing((value) => !value)}
              iconLeft={<Settings2 aria-hidden className="h-4 w-4" />}
            >
              {editing ? "Close setup" : integration ? "Edit setup" : "Configure"}
            </Button>
            {integration && (
              <Button
                variant="dangerGhost"
                size="sm"
                onClick={() => setConfirmDelete(true)}
                iconLeft={<Trash2 aria-hidden className="h-4 w-4" />}
              >
                Remove
              </Button>
            )}
          </div>
        </div>

        {overview.isLoading ? (
          <Skeleton height={180} className="mt-4 rounded-md" />
        ) : (editing || !integration) && (
          <div className="mt-5 flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <FieldControl label="Provider">
                <Select
                  options={PROVIDERS}
                  value={provider}
                  onValueChange={(next) => setProvider(next as EmailProvider)}
                />
              </FieldControl>
              <FieldControl label="Business email address" required>
                <Input
                  type="email"
                  value={emailAddress}
                  onChange={(event) => setEmailAddress(event.target.value)}
                  placeholder="sales@yourbusiness.com"
                />
              </FieldControl>
              <FieldControl label="Display name">
                <Input
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  placeholder="Acme Sales"
                />
              </FieldControl>
              <FieldControl
                label="Notification phone (simulated SMS)"
                hint="Alerts are stored, never sent by a gateway."
              >
                <Input
                  type="tel"
                  value={notificationPhone}
                  onChange={(event) => setNotificationPhone(event.target.value)}
                  placeholder="+255 712 000 000"
                />
              </FieldControl>
            </div>

            {provider === "imap" && (
              <div className="grid gap-4 rounded-sm border border-subtle bg-surface-raised p-3 sm:grid-cols-2">
                <FieldControl label="IMAP username">
                  <Input
                    value={imapUsername}
                    onChange={(event) => setImapUsername(event.target.value)}
                    autoComplete="username"
                  />
                </FieldControl>
                <FieldControl
                  label="IMAP password"
                  hint="Stored encrypted with a key derived from SECRET_KEY. Leave blank to keep the existing password."
                >
                  <Input
                    type="password"
                    value={imapPassword}
                    onChange={(event) => setImapPassword(event.target.value)}
                    autoComplete="new-password"
                  />
                </FieldControl>
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <FieldControl
                label="Ignore senders"
                hint="Comma-separated addresses that should never create a draft."
              >
                <Input
                  value={ignoreSenders}
                  onChange={(event) => setIgnoreSenders(event.target.value)}
                  placeholder="noreply@example.com, spam@example.com"
                />
              </FieldControl>
              <FieldControl
                label="Only these subject keywords"
                hint="Optional. Comma-separated. Empty means accept every subject."
              >
                <Input
                  value={subjectKeywords}
                  onChange={(event) => setSubjectKeywords(event.target.value)}
                  placeholder="pricing, quote, support"
                />
              </FieldControl>
            </div>

            <div className="flex items-center justify-between gap-4 rounded-sm border border-subtle bg-surface-raised px-3 py-2.5">
              <div>
                <p className="text-sm text-primary">Automation enabled</p>
                <p className="text-xs text-tertiary">
                  When off, incoming mail is stored without an AI draft.
                </p>
              </div>
              <Toggle checked={automation} onCheckedChange={setAutomation} label="Automation enabled" />
            </div>

            {(provider === "gmail_oauth" || provider === "microsoft_oauth") && (
              <AlertBanner tone="warning">
                OAuth authorisation is not connected in this deployment. The provider
                choice and mailbox record are saved, but no live mailbox polling runs.
                Use the simulated mailbox to exercise the full workflow.
              </AlertBanner>
            )}
            {provider === "imap" && (
              <AlertBanner tone="warning">
                IMAP credentials are stored encrypted, but live IMAP polling is not
                enabled in this deployment. Use the simulated mailbox to exercise the
                workflow.
              </AlertBanner>
            )}

            <div className="flex justify-end">
              <Button size="sm" onClick={() => void saveConfig()} loading={saveIntegration.isPending}>
                Save mailbox
              </Button>
            </div>
          </div>
        )}
      </section>

      {/* Simulated inbox */}
      <section className="rounded-md border border-subtle bg-surface p-5 shadow-elevation-1">
        <h2 className="text-base font-medium text-primary">Simulate an incoming email</h2>
        <p className="mt-1 text-sm text-secondary">
          Creates a real incoming-email record, runs the retrieval + drafting
          pipeline, stores a simulated SMS and queues the draft for approval.
        </p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <FieldControl label="Sender name">
            <Input value={senderName} onChange={(event) => setSenderName(event.target.value)} />
          </FieldControl>
          <FieldControl label="Sender email">
            <Input
              type="email"
              value={senderEmail}
              onChange={(event) => setSenderEmail(event.target.value)}
            />
          </FieldControl>
          <FieldControl label="Subject">
            <Input value={subject} onChange={(event) => setSubject(event.target.value)} />
          </FieldControl>
          <FieldControl label="Message">
            <Textarea
              value={bodyText}
              onChange={(event) => setBodyText(event.target.value)}
              rows={3}
            />
          </FieldControl>
        </div>
        <div className="mt-4 flex justify-end">
          <Button
            size="sm"
            onClick={() => void runSimulation()}
            loading={simulate.isPending}
            disabled={!integration}
            iconLeft={<Inbox aria-hidden className="h-4 w-4" />}
          >
            Receive &amp; draft
          </Button>
        </div>
        {!integration && (
          <p className="mt-2 text-right text-xs text-tertiary">
            Save a mailbox first.
          </p>
        )}
      </section>

      {/* Draft queue */}
      <section className="flex flex-col gap-4">
        <div>
          <h2 className="text-base font-medium text-primary">Draft queue</h2>
          <p className="text-sm text-secondary">
            Review the AI reply, edit it if needed, then approve or reject. Approval
            is recorded in the audit log.
          </p>
        </div>

        {drafts.isError ? (
          <AlertBanner tone="danger" title="Drafts could not be loaded">
            {drafts.error instanceof Error ? drafts.error.message : "Please try again."}
          </AlertBanner>
        ) : drafts.isLoading ? (
          <Skeleton height={160} className="rounded-md" />
        ) : (drafts.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            icon={Mail}
            title="No drafts yet"
            description="Use the simulator above to receive an email. The AI draft appears here for review."
          />
        ) : (
          <div className="flex flex-col gap-3">
            {drafts.data?.items.map((draft) => (
              <article
                key={draft.id}
                className="rounded-md border border-subtle bg-surface p-4 shadow-elevation-1"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-primary">
                      {draft.email?.subject || "Email draft"}
                    </p>
                    <p className="text-xs text-tertiary">
                      {draft.email?.sender_name || draft.email?.sender_email} ·{" "}
                      {formatAbsoluteTime(draft.created_at)}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={STATUS_TONE[draft.status] ?? "neutral"}>
                      {statusLabel(draft.status)}
                    </Badge>
                    {Boolean(draft.sent_simulated) && (
                      <Badge tone="warning">Sent (simulated)</Badge>
                    )}
                  </div>
                </div>
                <p className="mt-3 line-clamp-2 whitespace-pre-wrap text-sm text-secondary">
                  {draft.body || draft.error_message || "The AI could not write a draft. Open it to write the reply manually."}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button variant="secondary" size="sm" onClick={() => openReview(draft)}>
                    Review draft
                  </Button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {/* Simulated SMS log */}
      <section className="flex flex-col gap-3">
        <div>
          <h2 className="text-base font-medium text-primary">Simulated SMS alerts</h2>
          <p className="text-sm text-secondary">
            Stored exactly as they would be sent. Provider and status are marked
            simulated.
          </p>
        </div>
        {(overview.data?.notifications.length ?? 0) === 0 ? (
          <p className="rounded-md border border-subtle bg-surface-raised p-4 text-sm text-tertiary">
            No SMS alerts yet. Add a notification phone and receive an email to see one.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {overview.data?.notifications.map((message) => (
              <div
                key={message.id}
                className="rounded-md border border-subtle bg-surface p-3 text-sm"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs text-tertiary">
                    To {message.recipient} · {formatAbsoluteTime(message.created_at)}
                  </span>
                  <Badge tone="warning">{message.status} SMS</Badge>
                </div>
                <p className="mt-1 text-secondary">{message.body}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Review modal */}
      <Modal
        open={reviewing !== null}
        onClose={() => setReviewing(null)}
        title={reviewing?.email?.subject || "Review draft"}
        description={
          reviewing?.email
            ? `From ${reviewing.email.sender_name || ""} <${reviewing.email.sender_email}>`
            : undefined
        }
        size="lg"
        footer={
          reviewing ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex gap-2">
                <Button
                  variant="dangerGhost"
                  size="sm"
                  onClick={() => setRejecting(true)}
                  iconLeft={<X aria-hidden className="h-4 w-4" />}
                >
                  Reject
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void saveDraft()}
                  loading={updateDraft.isPending}
                  disabled={reviewing.status === "sent" || reviewing.status === "rejected"}
                >
                  Save draft
                </Button>
              </div>
              <div className="flex items-center gap-3">
                <Button variant="secondary" size="sm" onClick={() => setReviewing(null)}>
                  Close
                </Button>
                <Button
                  size="sm"
                  onClick={() => void approve()}
                  loading={approveDraft.isPending}
                  disabled={
                    !confirmSend ||
                    reviewing.status === "sent" ||
                    reviewing.status === "rejected"
                  }
                  iconLeft={<Send aria-hidden className="h-4 w-4" />}
                >
                  Approve &amp; send (simulated)
                </Button>
              </div>
            </div>
          ) : undefined
        }
      >
        {reviewing && (
          <div className="flex flex-col gap-4">
            {reviewing.error_message && (
              <AlertBanner tone="warning" title="The AI draft needs attention">
                {reviewing.error_message}
              </AlertBanner>
            )}
            <div className="rounded-sm border border-subtle bg-surface-raised p-3">
              <p className="text-2xs uppercase tracking-wide text-tertiary">Incoming email</p>
              <p className="mt-1 whitespace-pre-wrap text-sm text-secondary">
                {reviewing.email?.body_text}
              </p>
            </div>
            <FieldControl label="Your reply">
              <Textarea
                value={draftBody}
                onChange={(event) => setDraftBody(event.target.value)}
                rows={10}
                disabled={reviewing.status === "sent" || reviewing.status === "rejected"}
              />
            </FieldControl>
            <label className="flex items-start gap-3 rounded-sm border border-warning-500/30 bg-warning-500/10 p-3 text-xs leading-5 text-warning-400">
              <input
                type="checkbox"
                checked={confirmSend}
                onChange={(event) => setConfirmSend(event.target.checked)}
                className="mt-0.5 h-4 w-4 accent-warning-500"
                disabled={reviewing.status === "sent" || reviewing.status === "rejected"}
              />
              <span>
                I understand that sending is simulated. No email will leave the
                server; the draft will be marked <strong>Sent (simulated)</strong>.
              </span>
            </label>
            {Boolean(reviewing.sent_simulated) && (
              <AlertBanner tone="success" title="Sent (simulated)">
                Approved {formatAbsoluteTime(reviewing.approved_at)}. No real email
                was delivered.
              </AlertBanner>
            )}
          </div>
        )}
      </Modal>

      <ConfirmationDialog
        open={rejecting}
        onClose={() => setRejecting(false)}
        title="Reject this draft?"
        body="The incoming email and its draft stay in your history, but the reply will not be approved. This cannot be undone."
        confirmLabel="Reject draft"
        confirmLoading={rejectDraft.isPending}
        onConfirm={() => void reject()}
      />

      <ConfirmationDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title="Remove the mailbox?"
        body="The integration and its encrypted credentials are deleted. Incoming emails and drafts already stored remain in the workspace."
        confirmLabel="Remove mailbox"
        confirmLoading={deleteIntegration.isPending}
        onConfirm={() => void removeIntegration()}
      />

      <div className="flex items-center gap-2 text-xs text-tertiary">
        <ShieldCheck aria-hidden className="h-4 w-4" />
        Credentials are encrypted at rest and never returned by the API. Email
        approvals and integration changes are written to the audit log.
      </div>
    </div>
  );
}
