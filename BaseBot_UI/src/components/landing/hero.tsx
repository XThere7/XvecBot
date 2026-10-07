"use client";

import * as React from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { ArrowRight, Bot, FileText, Play, Sparkles, User, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

/**
 * Phase 1 — hero. Headline + dual CTA on the left, a live-looking product
 * visual on the right: a mock chat widget answering from a document, with a
 * source citation chip. Pure presentational markup, no backend.
 */
export function Hero() {
  const reduceMotion = useReducedMotion();

  const item = (delay: number) => ({
    initial: reduceMotion ? false : { opacity: 0, y: 20 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.45, delay, ease: "easeOut" as const },
  });

  return (
    <section className="relative overflow-hidden pt-16">
      {/* Ambient glow — one restrained premium moment for the landing hero. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_45%_at_50%_0%,rgba(99,102,241,0.16),transparent_70%)]"
      />
      <div className="relative mx-auto grid w-full max-w-[1200px] items-center gap-12 px-4 pb-16 pt-14 sm:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:pb-24 lg:pt-20">
        <div>
          <motion.div {...item(0)}>
            <Badge tone="accent" icon={<Sparkles aria-hidden className="h-3 w-3" />}>
              AI chat widgets for your business — no code
            </Badge>
          </motion.div>

          <motion.h1
            {...item(0.06)}
            className="mt-5 text-4xl font-semibold leading-[1.1] tracking-tight text-primary sm:text-5xl"
          >
            Turn your documents into a chat widget your customers will love
          </motion.h1>

          <motion.p {...item(0.12)} className="mt-5 max-w-xl text-base leading-6 text-secondary sm:text-lg sm:leading-7">
            BotBase turns your catalogue, price list or handbook into an AI
            assistant that answers from your own content — in English, Swahili
            and more. Paste one script tag and you&apos;re live.
          </motion.p>

          <motion.div {...item(0.18)} className="mt-8 flex flex-wrap items-center gap-3">
            <Button asChild variant="primary" size="lg" iconRight={<ArrowRight aria-hidden className="h-4 w-4" />}>
              <Link href="/register">Get started free</Link>
            </Button>
            <Button asChild variant="secondary" size="lg" iconLeft={<Play aria-hidden className="h-4 w-4" />}>
              <Link href="/dashboard">Open the dashboard</Link>
            </Button>
          </motion.div>

          <motion.p {...item(0.24)} className="mt-5 text-xs text-tertiary">
            No credit card · Works on any website · Live in minutes
          </motion.p>
        </div>

        {/* Product visual — a mocked chat panel with a grounded answer. */}
        <motion.div
          {...item(0.15)}
          className="relative mx-auto w-full max-w-[480px]"
          aria-label="Product preview: a BotBase chat widget answering a question with a cited source"
        >
          <div
            aria-hidden
            className="absolute -inset-6 rounded-[28px] bg-[radial-gradient(circle_at_50%_0%,rgba(99,102,241,0.28),transparent_65%)] blur-2xl"
          />
          <div className="relative overflow-hidden rounded-lg border border-subtle bg-surface shadow-elevation-3">
            <div className="flex items-center justify-between gap-3 border-b border-subtle px-4 py-3">
              <div className="flex items-center gap-2.5">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-tint text-xs font-semibold text-accent-300">
                  A
                </span>
                <div>
                  <p className="text-sm font-medium text-primary">Acme Store Support</p>
                  <p className="flex items-center gap-1.5 text-2xs text-success-400">
                    <span className="h-1.5 w-1.5 rounded-full bg-success-500" />
                    Online
                  </p>
                </div>
              </div>
              <Badge tone="neutral">
                <Zap aria-hidden className="h-3 w-3" /> Live
              </Badge>
            </div>

            <ol className="flex flex-col gap-4 px-4 py-5">
              <li className="flex justify-end">
                <p className="max-w-[80%] rounded-lg rounded-br-chip bg-accent-500 px-3.5 py-2.5 text-sm leading-5 text-inverse">
                  Do you deliver to Arusha, and what does it cost?
                </p>
              </li>
              <li className="flex flex-col gap-2">
                <div className="flex items-start gap-2.5">
                  <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-subtle bg-surface-raised text-tertiary">
                    <Bot aria-hidden className="h-3.5 w-3.5" />
                  </span>
                  <p className="max-w-[85%] whitespace-pre-wrap rounded-lg rounded-bl-chip border border-subtle bg-surface-raised px-3.5 py-2.5 text-sm leading-5 text-primary">
                    Yes — delivery to Arusha takes 2–3 days and costs 8,000 TZS
                    for orders under 100,000 TZS. Orders above that ship free.
                  </p>
                </div>
                <div className="pl-[38px]">
                  <span className="inline-flex items-center gap-1.5 rounded-chip border border-subtle bg-inset px-2 py-0.5 text-2xs text-secondary">
                    <FileText aria-hidden className="h-3 w-3 text-tertiary" />
                    delivery-policy.pdf
                    <span className="font-mono text-tertiary">#4</span>
                  </span>
                </div>
              </li>
              <li className="flex justify-end">
                <p className="flex max-w-[80%] items-center gap-2 rounded-lg rounded-br-chip bg-accent-500 px-3.5 py-2.5 text-sm leading-5 text-inverse">
                  <User aria-hidden className="h-3.5 w-3.5 opacity-80" />
                  Asante — na swali la pili…
                </p>
              </li>
            </ol>

            <div className="border-t border-subtle p-3">
              <div className="flex items-center gap-2 rounded-md border border-strong bg-inset px-3 py-2.5">
                <p className="flex-1 text-sm text-tertiary">Ask about products, prices, delivery…</p>
                <span className="rounded-sm bg-accent-500 px-3 py-1.5 text-xs font-medium text-inverse">
                  Send
                </span>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
