"use client";

import * as React from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { Database, MessageSquarePlus, Rocket } from "lucide-react";

const STEPS = [
  {
    icon: Database,
    step: "Step 1",
    title: "Manage knowledge",
    body: "Upload your catalogue, price list or handbook — PDF, TXT or DOCX. BotBase trains it automatically, so your agents always answer from your own content.",
    href: "/workspaces",
    cta: "Explore workspaces",
  },
  {
    icon: MessageSquarePlus,
    step: "Step 2",
    title: "Build agents",
    body: "Give your assistant a name, a personality and a tone. Pick the model and language, test it in the dashboard preview, and watch every answer cite its source.",
    href: "/workspaces",
    cta: "See how agents work",
  },
  {
    icon: Rocket,
    step: "Step 3",
    title: "Deploy widgets",
    body: "Generate an embed token, copy the snippet, and paste one script tag into your site. The chat widget is live in minutes — no build step, no code.",
    href: "/account",
    cta: "Get your snippet",
  },
];

/**
 * Phase 1 — how it works. The same three jobs that drive the whole product,
 * each linking straight into the part of the app where it happens.
 */
export function HowItWorks() {
  const reduceMotion = useReducedMotion();

  return (
    <section id="how-it-works" className="border-t border-subtle bg-surface">
      <div className="mx-auto w-full max-w-[1200px] px-4 py-16 sm:px-6 lg:py-24">
        <div className="max-w-2xl">
          <p className="text-xs font-medium uppercase tracking-widest text-accent-300">
            How it works
          </p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight text-primary sm:text-3xl">
            Three steps to a live chat widget
          </h2>
          <p className="mt-3 text-base leading-6 text-secondary">
            Everything in BotBase serves three jobs: manage knowledge, build
            agents, deploy widgets. Nothing else to learn.
          </p>
        </div>

        <ol className="mt-10 grid gap-4 md:grid-cols-3">
          {STEPS.map((item, index) => {
            const Icon = item.icon;
            return (
              <motion.li
                key={item.title}
                initial={reduceMotion ? false : { opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-80px" }}
                transition={{ duration: 0.4, delay: index * 0.08, ease: "easeOut" }}
                className="flex flex-col rounded-md border border-subtle bg-canvas p-6"
              >
                <span className="flex h-11 w-11 items-center justify-center rounded-md border border-accent-500/30 bg-accent-tint text-accent-300">
                  <Icon aria-hidden className="h-5 w-5" />
                </span>
                <p className="mt-5 text-2xs font-medium uppercase tracking-widest text-tertiary">
                  {item.step}
                </p>
                <h3 className="mt-1.5 text-lg text-primary">{item.title}</h3>
                <p className="mt-2 flex-1 text-sm leading-5 text-secondary">{item.body}</p>
                <Link
                  href={item.href}
                  className="mt-5 inline-flex w-fit items-center gap-1.5 text-sm font-medium text-accent-300 hover:underline"
                >
                  {item.cta}
                  <span aria-hidden>→</span>
                </Link>
              </motion.li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
