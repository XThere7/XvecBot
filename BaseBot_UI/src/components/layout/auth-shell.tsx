"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { APP_NAME } from "@/lib/constants";
import { cn } from "@/lib/cn";

const STEPS = [
  {
    title: "Upload",
    body: "Add your catalogue, price list or handbook. PDF, TXT or DOCX.",
  },
  {
    title: "Train",
    body: "XvecBot reads and indexes your documents. No AI expertise needed.",
  },
  {
    title: "Embed",
    body: "Paste one script tag into your site and the chat widget is live.",
  },
];

export function AuthShell({
  children,
  title,
  subtitle,
  footer,
}: {
  children: React.ReactNode;
  title: string;
  subtitle?: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[1fr_minmax(420px,44%)]">
      {/* Form */}
      <div className="flex flex-col px-5 py-8 sm:px-8">
        <Link href="/" className="flex items-center gap-2.5">
          <span
            aria-hidden
            className="flex h-7 w-7 items-center justify-center rounded-sm bg-accent-500 text-sm font-semibold text-inverse"
          >
            X
          </span>
          <span className="text-lg font-semibold text-primary">{APP_NAME}</span>
        </Link>

        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[400px]">
            <h1 className="text-2xl text-primary">{title}</h1>
            {subtitle && (
              <p className="mt-2 text-sm leading-5 text-secondary">{subtitle}</p>
            )}
            <div className="mt-8">{children}</div>
          </div>
        </div>

        {footer && <div className="text-sm text-secondary">{footer}</div>}
      </div>

      {/* Brand panel */}
      <aside className="relative hidden overflow-hidden border-l border-subtle bg-surface lg:flex lg:flex-col lg:justify-center lg:px-12">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(99,102,241,0.16),transparent_60%)]"
        />
        <div className="relative">
          <p className="text-2xl leading-8 text-primary">
            Your documents become a
            <br />
            chat widget on your website.
          </p>
          <p className="mt-3 max-w-sm text-sm leading-5 text-secondary">
            {APP_NAME} turns the files your business already has into an AI
            assistant that answers from your own content — in Swahili, English
            and more.
          </p>

          <ol className="mt-10 flex flex-col gap-6">
            {STEPS.map((step, index) => (
              <li key={step.title} className="flex gap-4">
                <span
                  aria-hidden
                  className={cn(
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-accent-500/40",
                    "bg-accent-tint text-sm font-medium text-accent-300",
                  )}
                >
                  {index + 1}
                </span>
                <div>
                  <p className="text-base font-medium text-primary">{step.title}</p>
                  <p className="mt-1 max-w-xs text-sm leading-5 text-secondary">
                    {step.body}
                  </p>
                </div>
              </li>
            ))}
          </ol>

          <p className="mt-12 text-xs text-tertiary">
            <ArrowLeft aria-hidden className="mr-1.5 inline h-3 w-3" />
            Built for Tanzanian businesses. Works on any website, no build step.
          </p>
        </div>
      </aside>
    </div>
  );
}