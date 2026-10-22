"use client";

import * as React from "react";
import { AlertTriangle } from "lucide-react";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { Modal } from "@/components/ui/modal";
import { API_BASE_URL } from "@/lib/api-client";
import type { DeveloperApiKeyCreated } from "@/types/api";

/**
 * The plaintext developer key exists only in the 201 response. This modal
 * receives it as component state; it is never stored, routed, logged, or
 * placed in React Query's mutation cache (the caller resets that mutation).
 */
export function OneTimeApiKeyModal({
  value,
  onClose,
}: {
  value: DeveloperApiKeyCreated | null;
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
      setGuarded(true);
      return;
    }
    onClose();
  };

  const curl = value
    ? [
        `curl -X POST "${API_BASE_URL}/api/v1/chat" \\`,
        `  -H "X-API-Key: ${value.key}" \\`,
        `  -H "Content-Type: application/json" \\`,
        `  -d '{"agent_id":"<agent-id>","message":"Hello"}'`,
      ].join("\n")
    : "";

  return (
    <Modal
      open={Boolean(value)}
      onClose={handleClose}
      title="Save your API key"
      description="This is the only time the full key will be shown."
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose}>
            Close
          </Button>
          <Button
            variant="primary"
            onClick={onClose}
            disabled={!copied}
          >
            I&apos;ve saved it
          </Button>
        </>
      }
    >
      {value && (
        <div className="flex flex-col gap-5">
          <AlertBanner tone="warning" icon={AlertTriangle}>
            <p>
              <strong className="font-medium text-warning-400">
                Copy this key now.
              </strong>{" "}
              It cannot be recovered. If you lose it, revoke it and create a new
              one.
            </p>
            {guarded && !copied && (
              <p className="mt-2 font-medium text-warning-400">
                You closed this without copying. Try again before dismissing.
              </p>
            )}
          </AlertBanner>

          <section className="flex flex-col gap-2">
            <h3 className="text-base font-medium text-primary">Your key</h3>
            <div className="flex items-center gap-2 rounded-md border border-subtle bg-inset px-3 py-2.5">
              <code className="min-w-0 flex-1 overflow-x-auto font-mono text-xs text-primary">
                {value.key}
              </code>
              <CopyButton
                value={value.key}
                label="Copy key"
                onCopied={() => setCopied(true)}
              />
            </div>
            <p className="text-xs text-tertiary">
              Labelled <span className="text-secondary">{value.name}</span>. The
              dashboard will show only the prefix{" "}
              <code className="font-mono">{value.key_prefix}</code> later.
            </p>
          </section>

          <section className="flex flex-col gap-2">
            <h3 className="text-base font-medium text-primary">
              Test it with curl
            </h3>
            <div className="relative rounded-md border border-subtle bg-inset">
              <pre className="overflow-x-auto p-3 pr-14 font-mono text-xs leading-5 text-secondary">
                {curl}
              </pre>
              <CopyButton
                value={curl}
                label="Copy"
                className="absolute right-2 top-2"
                onCopied={() => setCopied(true)}
              />
            </div>
            <p className="text-xs leading-5 text-tertiary">
              Replace <code className="font-mono">&lt;agent-id&gt;</code> with an
              agent from this workspace. The key is sent in the{" "}
              <code className="font-mono">X-API-Key</code> header and must never
              be shipped to a browser or mobile app.
            </p>
          </section>

          <p className="text-xs text-tertiary">{value.warning}</p>
        </div>
      )}
    </Modal>
  );
}
