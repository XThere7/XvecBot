"use client";

import * as React from "react";
import { ExternalLink, Link2, QrCode } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { API_BASE_URL } from "@/lib/api-client";

/**
 * The hosted page is a full-capability link: anyone with the URL can chat.
 * Keep it out of the snippet's iframe/script paths and make that clear here.
 */
export function HostedLinkCard({
  hostedUrl,
  token,
}: {
  hostedUrl: string;
  token: string;
}) {
  const qrHref = `${API_BASE_URL}/public/qr/${encodeURIComponent(token)}`;

  return (
    <section className="rounded-lg border border-accent-500/25 bg-accent-tint/40 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2">
          <Link2 aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-accent-300" />
          <div className="min-w-0">
            <h3 className="text-sm font-medium text-primary">Hosted chat page</h3>
            <p className="mt-0.5 text-xs leading-5 text-tertiary">
              Share this link or print the QR code. It works without the embed
              snippet and keeps the full token in the URL.
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button asChild variant="secondary" size="sm">
            <a href={hostedUrl} target="_blank" rel="noreferrer">
              <ExternalLink aria-hidden className="h-3.5 w-3.5" />
              Open
            </a>
          </Button>
          <Button asChild variant="ghost" size="sm">
            <a href={qrHref} target="_blank" rel="noreferrer">
              <QrCode aria-hidden className="h-3.5 w-3.5" />
              QR code
            </a>
          </Button>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2 rounded-md border border-subtle bg-inset px-3 py-2">
        <code className="min-w-0 flex-1 overflow-x-auto font-mono text-xs text-primary">
          {hostedUrl}
        </code>
        <CopyButton value={hostedUrl} label="Copy link" />
      </div>
    </section>
  );
}
