"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import { AlertTriangle } from "lucide-react";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { CodeSnippet } from "@/components/ui/code-snippet";
import { CopyButton } from "@/components/ui/copy-button";
import { Modal } from "@/components/ui/modal";
import { SnippetChecklist } from "./snippet-checklist";

/** PREMIUM MOMENT 3 — lazily loaded glow behind this high-anxiety modal. */
const FocusGlow = dynamic(
  () => import("@/components/premium/focus-glow").then((m) => m.FocusGlow),
  { ssr: false },
);

/** PREMIUM MOMENT 4 — lazily loaded shimmer on the primary copy button. */
const ShinyText = dynamic(
  () => import("@/components/premium/shiny-text").then((m) => m.ShinyText),
  { ssr: false },
);

export type OneTimeToken = {
  token: string;
  label: string;
  snippet: string;
};

/**
 * The full embed token exists in exactly two responses: the 201 from token
 * creation and GET /tokens/{id}/snippet. This modal is the only place it is
 * rendered. It lives in component state only — never a store, URL,
 * localStorage, console or analytics.
 */
export function OneTimeTokenModal({
  value,
  onClose,
}: {
  value: OneTimeToken | null;
  onClose: () => void;
}) {
  const [copied, setCopied] = React.useState(false);
  const [guarded, setGuarded] = React.useState(false);

  React.useEffect(() => {
    if (value) {
      setCopied(false);
      setGuarded(false);
    }
  }, [value]);

  const handleClose = () => {
    if (!copied && !guarded) {
      // Dismissal guard: block the first attempt and warn harder.
      setGuarded(true);
      return;
    }
    onClose();
  };

  const acknowledge = () => {
    setCopied(true);
    onClose();
  };

  return (
    <Modal
      open={Boolean(value)}
      onClose={handleClose}
      title="Save your embed token"
      description="This is the only time the full token will be shown."
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose}>
            Close
          </Button>
          <Button variant="primary" onClick={acknowledge} disabled={!copied}>
            I&apos;ve copied it
          </Button>
        </>
      }
    >
      {value && (
        <FocusGlow className="-m-2 p-2">
          <div className="flex flex-col gap-5">
            <AlertBanner tone="warning" icon={AlertTriangle}>
              <p>
                <strong className="font-medium text-warning-400">
                  Copy this token now.
                </strong>{" "}
                For your security we only show it once. If you lose it, delete
                this token and create a new one — we cannot recover it for you.
              </p>
              {guarded && !copied && (
                <p className="mt-2 font-medium text-warning-400">
                  You closed this without copying. This is your last chance to
                  copy the token before it is gone.
                </p>
              )}
            </AlertBanner>

            <section className="flex flex-col gap-2">
              <h3 className="text-base font-medium text-primary">
                1. Copy the snippet
              </h3>
              <CodeSnippet
                code={value.snippet}
                copyLabel={<ShinyText className="inline-block">Copy snippet</ShinyText>}
                onCopy={() => setCopied(true)}
                context={
                  <>
                    <span>Paste before &lt;/body&gt;</span>
                    <span>Works on any website — no build step</span>
                  </>
                }
              />
            </section>

            <section className="flex flex-col gap-2">
              <h3 className="text-base font-medium text-primary">
                2. The token on its own
              </h3>
              <div className="flex items-center justify-between gap-3 rounded-lg border border-subtle bg-inset px-3 py-2.5">
                <code className="min-w-0 flex-1 overflow-x-auto font-mono text-xs text-primary">
                  {value.token}
                </code>
                <CopyButton
                  value={value.token}
                  label="Copy token"
                  onCopied={() => setCopied(true)}
                />
              </div>
            </section>

            <section className="flex flex-col gap-2">
              <h3 className="text-base font-medium text-primary">
                3. Check off each step
              </h3>
              <SnippetChecklist resetKey={value.token} />
            </section>

            <p className="text-xs text-tertiary">
              Labelled <span className="text-secondary">{value.label}</span>. You
              can reveal the snippet again at any time from this token&apos;s row
              — but the token stays masked in the list.
            </p>
          </div>
        </FocusGlow>
      )}
    </Modal>
  );
}