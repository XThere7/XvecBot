"use client";

import * as React from "react";
import { motion, useTransform, type MotionValue } from "motion/react";
import {
  ArrowRight,
  Bot,
  Check,
  CircleAlert,
  Code2,
  FileSpreadsheet,
  FileText,
  Globe2,
  KeyRound,
  Layers3,
  Lock,
  MessageSquare,
  Send,
  ShieldCheck,
  Sparkles,
  Terminal,
  Unplug,
} from "lucide-react";
import { BotBaseMark } from "@/components/brand/botbase-mark";
import { cn } from "@/lib/cn";

export type StoryVisualProps = {
  progress: MotionValue<number>;
};

type MockWindowProps = {
  url?: string;
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
  chrome?: boolean;
};

/**
 * A small, self-contained browser shell for the story mockups. The chrome is
 * deliberately dark in both themes: these are product screenshots, not page
 * surfaces. They are always aria-hidden by the story wrapper.
 */
function MockWindow({
  url = "botbasex.com/dashboard",
  children,
  className,
  contentClassName,
  chrome = true,
}: MockWindowProps) {
  return (
    <div
      className={cn(
        "flex min-h-0 flex-col overflow-hidden rounded-xl border border-white/10 bg-[#0b0d12]",
        "shadow-[0_30px_90px_-28px_rgba(0,0,0,0.95)] ring-1 ring-white/5",
        className,
      )}
    >
      {chrome && (
        <div className="flex shrink-0 items-center gap-1.5 border-b border-white/10 bg-[#12151c] px-2.5 py-1.5 sm:px-3 sm:py-2">
          <span className="h-1.5 w-1.5 rounded-full bg-[#f87171]/80" />
          <span className="h-1.5 w-1.5 rounded-full bg-[#fbbf24]/80" />
          <span className="h-1.5 w-1.5 rounded-full bg-[#4ade80]/80" />
          <div className="ml-1.5 flex min-w-0 flex-1 items-center gap-1 rounded-md border border-white/10 bg-[#0e1116] px-1.5 py-0.5 sm:ml-2 sm:px-2 sm:py-1">
            <Lock aria-hidden className="h-2 w-2 shrink-0 text-[#6b7280]" />
            <span className="truncate font-mono text-[7px] text-[#9aa3b2] sm:text-[8px]">
              {url}
            </span>
          </div>
        </div>
      )}
      <div className={cn("min-h-0 flex-1", contentClassName)}>{children}</div>
    </div>
  );
}

function TinyDot({ tone = "green" }: { tone?: "green" | "amber" | "red" | "indigo" }) {
  return (
    <span
      aria-hidden
      className={cn(
        "h-1.5 w-1.5 shrink-0 rounded-full",
        tone === "green" && "bg-[#4ade80]",
        tone === "amber" && "bg-[#fbbf24]",
        tone === "red" && "bg-[#f87171]",
        tone === "indigo" && "bg-[#818cf8]",
      )}
    />
  );
}

function StatusPill({
  children,
  tone,
}: {
  children: React.ReactNode;
  tone: "green" | "amber" | "red" | "indigo";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 font-mono text-[6px] uppercase tracking-[0.08em] sm:text-[7px]",
        tone === "green" && "border-[#4ade80]/25 bg-[#4ade80]/10 text-[#86efac]",
        tone === "amber" && "border-[#fbbf24]/25 bg-[#fbbf24]/10 text-[#fcd34d]",
        tone === "red" && "border-[#f87171]/25 bg-[#f87171]/10 text-[#fca5a5]",
        tone === "indigo" && "border-[#818cf8]/25 bg-[#818cf8]/10 text-[#c7d2fe]",
      )}
    >
      {children}
    </span>
  );
}

function SourceBadge({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex max-w-full items-center gap-1 rounded border border-white/10 bg-[#0e1116] px-1.5 py-0.5 text-[6.5px] leading-3 text-[#9aa3b2] sm:text-[7px]">
      <FileText aria-hidden className="h-2.5 w-2.5 shrink-0 text-[#818cf8]" />
      <span className="truncate">{children}</span>
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* 01 — Hero / a real business site with the BotBase widget                    */
/* -------------------------------------------------------------------------- */

export function HeroStoryVisual({ progress }: StoryVisualProps) {
  const browserY = useTransform(progress, [0, 1], [0, -10]);
  const widgetY = useTransform(progress, [0, 1], [0, 8]);

  return (
    <div className="relative h-full w-full">
      <div className="absolute inset-0 mx-auto max-w-[640px]">
        <motion.div
          style={{ y: browserY }}
          className="absolute left-0 top-[3%] h-[74%] w-[86%] min-w-0"
        >
          <MockWindow
            url="kilimanjarocoffee.co.tz"
            className="h-full"
            contentClassName="flex flex-col"
          >
            <div className="flex shrink-0 items-center justify-between border-b border-white/10 px-2.5 py-1.5 sm:px-3">
              <span className="font-mono text-[6.5px] tracking-[0.22em] text-[#f4f4f5] sm:text-[8px]">
                KILIMANJARO
              </span>
              <span className="hidden items-center gap-3 font-mono text-[6px] uppercase tracking-[0.14em] text-[#6b7280] sm:flex">
                <span>Shop</span>
                <span>Story</span>
                <span>Visit</span>
              </span>
              <span className="rounded-full border border-white/10 px-1.5 py-0.5 font-mono text-[6px] text-[#9aa3b2]">
                EN
              </span>
            </div>

            <div className="grid min-h-0 flex-1 grid-cols-[1.08fr_0.92fr]">
              <div className="flex min-w-0 flex-col justify-center p-2.5 sm:p-4">
                <p className="font-mono text-[5.5px] uppercase tracking-[0.2em] text-[#a5b4fc] sm:text-[6.5px]">
                  Single origin · Arusha
                </p>
                <p className="mt-1 text-[clamp(13px,2.5vw,30px)] font-semibold uppercase leading-[0.94] tracking-[-0.04em] text-[#f4f4f5]">
                  Fresh from
                  <br />
                  the highlands.
                </p>
                <p className="mt-1.5 hidden max-w-[24ch] text-[7px] leading-3 text-[#9aa3b2] sm:block">
                  Small-batch coffee, roasted for the way you brew.
                </p>
                <span className="mt-2 inline-flex w-fit items-center gap-1 rounded-full bg-[#f4f4f5] px-1.5 py-1 text-[6.5px] font-medium text-[#0b0d12] sm:px-2 sm:text-[8px]">
                  Shop the roast
                  <ArrowRight aria-hidden className="h-2 w-2" />
                </span>
              </div>

              <div className="relative m-1.5 overflow-hidden rounded-lg bg-[radial-gradient(ellipse_at_38%_28%,#6b4423_0%,#2a1a0f_46%,#0b0d12_85%)] sm:m-2">
                <div
                  aria-hidden
                  className="absolute -left-4 top-1/3 h-16 w-16 rounded-full bg-[#c8a27a]/15 blur-xl"
                />
                <div className="absolute left-1/2 top-1/2 h-[64%] w-[36%] min-w-[34px] -translate-x-1/2 -translate-y-1/2 rounded-t-[8px] rounded-b-[3px] bg-[linear-gradient(160deg,#2a1b11,#120c08)] shadow-[0_12px_30px_rgba(0,0,0,0.6)] ring-1 ring-[#c8a27a]/25">
                  <div className="mx-auto mt-1.5 h-px w-2/3 bg-[#c8a27a]/40" />
                  <p className="mt-1.5 text-center font-mono text-[4.5px] tracking-[0.18em] text-[#e7d3bd] sm:text-[5.5px]">
                    KILIMANJARO
                  </p>
                  <p className="mt-0.5 text-center text-[6px] font-semibold leading-[1.05] text-[#f4f4f5] sm:text-[8px]">
                    DARK
                    <br />
                    ROAST
                  </p>
                  <span className="absolute bottom-1 left-1/2 h-2.5 w-2.5 -translate-x-1/2 rounded-full border border-[#c8a27a]/40" />
                </div>
                <p className="absolute bottom-1.5 left-2 font-mono text-[5.5px] uppercase tracking-[0.16em] text-[#e7d3bd]/80 sm:text-[6.5px]">
                  500 g · whole bean
                </p>
              </div>
            </div>
          </MockWindow>
        </motion.div>

        {/* Floating assistant — the product itself, grounded in the site's own content. */}
        <motion.div
          style={{ y: widgetY }}
          className="absolute bottom-[1%] right-0 z-20 w-[60%] max-w-[322px]"
        >
          <div className="overflow-hidden rounded-xl border border-white/15 bg-[#10131a] shadow-[0_24px_60px_-16px_rgba(0,0,0,0.9)]">
            <div className="flex items-center gap-2 border-b border-white/10 bg-[#151922] px-2.5 py-2">
              <span className="relative flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[#818cf8]/30 bg-[#6366f1]/15 text-[#c7d2fe]">
                <Bot aria-hidden className="h-3 w-3" />
                <span className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full border-2 border-[#151922] bg-[#4ade80]" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[8.5px] font-medium leading-3 text-[#f4f4f5] sm:text-[9px]">
                  Kilimanjaro Assistant
                </p>
                <p className="font-mono text-[6px] uppercase tracking-[0.12em] text-[#4ade80]">
                  Online
                </p>
              </div>
              <Sparkles aria-hidden className="h-3 w-3 text-[#818cf8]" />
            </div>

            <div className="space-y-2 p-2 sm:p-2.5">
              <div className="ml-auto w-[84%] rounded-lg rounded-br-sm bg-[#6366f1] px-2 py-1.5 text-[7.5px] leading-[11px] text-white sm:text-[8.5px]">
                Do you deliver to Arusha?
              </div>
              <div className="w-[94%] rounded-lg rounded-bl-sm border border-white/10 bg-[#181b23] px-2 py-1.5 text-[7.5px] leading-[11px] text-[#e8eaf0] sm:text-[8.5px]">
                Yes — 1–2 days to Arusha. Orders over 100,000 TZS ship free.
                <div className="mt-1.5">
                  <SourceBadge>delivery-policy.pdf · #4</SourceBadge>
                </div>
              </div>
              <div className="flex items-center gap-1.5 rounded-md border border-white/10 bg-[#0e1116] px-2 py-1.5">
                <span className="min-w-0 flex-1 truncate text-[7px] text-[#6b7280] sm:text-[8px]">
                  Ask about our coffee…
                </span>
                <span className="flex h-4 w-4 items-center justify-center rounded bg-[#6366f1] text-white">
                  <Send aria-hidden className="h-2 w-2" />
                </span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Small supporting chips keep the composition layered. */}
        <div className="absolute left-[1%] top-[7%] z-10 hidden w-[30%] max-w-[176px] rounded-lg border border-white/10 bg-[#12151c]/95 p-2 shadow-[0_18px_40px_-18px_rgba(0,0,0,0.9)] backdrop-blur sm:block">
          <p className="font-mono text-[6px] uppercase tracking-[0.18em] text-[#6b7280]">
            Grounded
          </p>
          <p className="mt-1 flex items-center gap-1 text-[8px] text-[#e8eaf0]">
            <Check aria-hidden className="h-2.5 w-2.5 text-[#4ade80]" />
            Every reply cites its source
          </p>
        </div>

        <div className="absolute bottom-[4%] left-[3%] z-10 hidden items-center gap-1.5 rounded-full border border-white/10 bg-[#12151c]/95 px-2 py-1 shadow-lg backdrop-blur sm:flex">
          <TinyDot />
          <span className="font-mono text-[6.5px] uppercase tracking-[0.12em] text-[#9aa3b2]">
            Live on the website
          </span>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 02 — Fragmented knowledge                                                   */
/* -------------------------------------------------------------------------- */

function FragmentCard({
  className,
  children,
  rotate,
  delayStyle,
}: {
  className?: string;
  children: React.ReactNode;
  rotate: string;
  delayStyle?: React.CSSProperties;
}) {
  return (
    <div className={cn("absolute", className)} style={delayStyle}>
      <div className={rotate}>
        <div className="overflow-hidden rounded-lg border border-white/10 bg-[#0f1218] shadow-[0_20px_50px_-20px_rgba(0,0,0,0.9)]">
          {children}
        </div>
      </div>
    </div>
  );
}

export function FragmentedStoryVisual({ progress }: StoryVisualProps) {
  const docX = useTransform(progress, [0.05, 0.72], [18, 0]);
  const docY = useTransform(progress, [0.05, 0.72], [-10, 0]);
  const sheetX = useTransform(progress, [0.08, 0.75], [-22, 0]);
  const sheetY = useTransform(progress, [0.08, 0.75], [12, 0]);
  const faqX = useTransform(progress, [0.1, 0.76], [12, 0]);
  const faqY = useTransform(progress, [0.1, 0.76], [18, 0]);
  const inboxX = useTransform(progress, [0.06, 0.72], [-14, 0]);
  const inboxY = useTransform(progress, [0.06, 0.72], [-16, 0]);
  const centerOpacity = useTransform(progress, [0.12, 0.34], [0, 1]);
  const centerScale = useTransform(progress, [0.12, 0.38], [0.92, 1]);

  return (
    <div className="relative h-full w-full">
      <div className="absolute inset-0 mx-auto max-w-[620px]">
        <svg
          aria-hidden
          className="pointer-events-none absolute inset-0 h-full w-full"
          viewBox="0 0 600 520"
          preserveAspectRatio="none"
          fill="none"
        >
          <defs>
            <linearGradient id="fragment-line" x1="0" y1="0" x2="1" y2="1">
              <stop stopColor="#f87171" stopOpacity="0.34" />
              <stop offset="1" stopColor="#fbbf24" stopOpacity="0.1" />
            </linearGradient>
          </defs>
          <path
            d="M170 110 C 235 150, 255 205, 300 250"
            stroke="url(#fragment-line)"
            strokeWidth="1"
            strokeDasharray="5 8"
          />
          <path
            d="M430 92 C 375 145, 350 205, 310 245"
            stroke="url(#fragment-line)"
            strokeWidth="1"
            strokeDasharray="5 8"
          />
          <path
            d="M160 410 C 225 365, 260 315, 296 275"
            stroke="url(#fragment-line)"
            strokeWidth="1"
            strokeDasharray="5 8"
          />
          <path
            d="M446 395 C 385 360, 350 310, 312 277"
            stroke="url(#fragment-line)"
            strokeWidth="1"
            strokeDasharray="5 8"
          />
        </svg>

        <motion.div style={{ x: docX, y: docY }} className="absolute inset-0">
          <FragmentCard
            rotate="-rotate-[3.5deg]"
            className="left-[2%] top-[5%] w-[46%] max-w-[252px]"
          >
            <div className="flex items-center gap-1.5 border-b border-white/10 px-2 py-1.5">
              <FileText aria-hidden className="h-2.5 w-2.5 text-[#f87171]" />
              <span className="truncate text-[7.5px] text-[#e8eaf0]">catalogue_v3.pdf</span>
              <StatusPill tone="red">outdated</StatusPill>
            </div>
            <div className="space-y-1.5 p-2">
              <div className="h-1 w-4/5 rounded bg-white/10" />
              <div className="h-1 w-3/5 rounded bg-white/8" />
              <div className="mt-2 flex items-end justify-between">
                <div className="space-y-1">
                  <div className="h-1 w-14 rounded bg-white/8" />
                  <div className="h-1 w-10 rounded bg-white/8" />
                </div>
                <span className="font-mono text-[5.5px] text-[#f87171]">edited 8 months ago</span>
              </div>
            </div>
          </FragmentCard>
        </motion.div>

        <motion.div style={{ x: sheetX, y: sheetY }} className="absolute inset-0">
          <FragmentCard
            rotate="rotate-[2.5deg]"
            className="right-[2%] top-[2%] w-[44%] max-w-[242px]"
          >
            <div className="flex items-center gap-1.5 border-b border-white/10 px-2 py-1.5">
              <FileSpreadsheet aria-hidden className="h-2.5 w-2.5 text-[#fbbf24]" />
              <span className="truncate text-[7.5px] text-[#e8eaf0]">price-list.xlsx</span>
              <StatusPill tone="amber">duplicate</StatusPill>
            </div>
            <div className="grid grid-cols-3 gap-px overflow-hidden bg-white/10 p-px text-[5.5px]">
              {[
                ["ITEM", "TZS", "STOCK"],
                ["500g", "18,000", "12"],
                ["1kg", "32,000", "—"],
                ["gift", "45,000", "4"],
              ].map((row, index) =>
                row.map((cell) => (
                  <span
                    key={`${index}-${cell}`}
                    className={cn(
                      "bg-[#0f1218] px-1 py-1 text-[#9aa3b2]",
                      index === 0 && "font-mono uppercase tracking-[0.1em] text-[#6b7280]",
                    )}
                  >
                    {cell}
                  </span>
                )),
              )}
            </div>
          </FragmentCard>
        </motion.div>

        <motion.div style={{ x: faqX, y: faqY }} className="absolute inset-0">
          <FragmentCard
            rotate="rotate-[2deg]"
            className="bottom-[4%] left-[10%] w-[43%] max-w-[240px] max-sm:hidden"
          >
            <div className="flex items-center gap-1.5 border-b border-white/10 px-2 py-1.5">
              <Globe2 aria-hidden className="h-2.5 w-2.5 text-[#818cf8]" />
              <span className="truncate text-[7.5px] text-[#e8eaf0]">faq-page.html</span>
            </div>
            <div className="p-2">
              <p className="text-[6.5px] leading-3 text-[#9aa3b2]">
                Delivery info missing
              </p>
              <div className="mt-1.5 flex items-center gap-1 rounded border border-[#f87171]/20 bg-[#f87171]/5 px-1.5 py-1 text-[6px] text-[#fca5a5]">
                <CircleAlert aria-hidden className="h-2 w-2" />
                answer not on the page
              </div>
            </div>
          </FragmentCard>
        </motion.div>

        <motion.div style={{ x: inboxX, y: inboxY }} className="absolute inset-0">
          <FragmentCard
            rotate="-rotate-[4deg]"
            className="bottom-[8%] right-[4%] w-[40%] max-w-[224px]"
          >
            <div className="flex items-center gap-1.5 border-b border-white/10 px-2 py-1.5">
              <MessageSquare aria-hidden className="h-2.5 w-2.5 text-[#9aa3b2]" />
              <span className="truncate text-[7.5px] text-[#e8eaf0]">Support inbox</span>
              <StatusPill tone="amber">after hours</StatusPill>
            </div>
            <div className="space-y-1.5 p-2">
              <div className="rounded bg-[#181b23] px-1.5 py-1 text-[6px] text-[#9aa3b2]">
                “Do you ship to Mwanza?”
              </div>
              <div className="rounded bg-[#181b23] px-1.5 py-1 text-[6px] text-[#9aa3b2]">
                “Is the 1 kg bag in stock?”
              </div>
              <p className="font-mono text-[5.5px] uppercase tracking-[0.12em] text-[#f87171]">
                waiting for an answer
              </p>
            </div>
          </FragmentCard>
        </motion.div>

        <motion.div
          style={{ opacity: centerOpacity, scale: centerScale }}
          className="absolute left-1/2 top-1/2 z-20 -translate-x-1/2 -translate-y-1/2"
        >
          <div className="flex items-center gap-2 rounded-full border border-[#f87171]/25 bg-[#160f12]/95 py-1.5 pl-2 pr-3 shadow-[0_16px_40px_-12px_rgba(0,0,0,0.9)] backdrop-blur">
            <span className="flex h-6 w-6 items-center justify-center rounded-full border border-[#f87171]/30 bg-[#f87171]/10 text-[#fca5a5]">
              <Unplug aria-hidden className="h-3 w-3" />
            </span>
            <span className="whitespace-nowrap text-[8px] font-medium text-[#f4f4f5] sm:text-[9px]">
              No single source of truth
            </span>
          </div>
        </motion.div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 03 — Knowledge becomes structured                                           */
/* -------------------------------------------------------------------------- */

function IncomingSource({
  progress,
  children,
  className,
  delay,
}: {
  progress: MotionValue<number>;
  children: React.ReactNode;
  className?: string;
  delay: number;
}) {
  const start = 0.1 + delay;
  const opacity = useTransform(progress, [start, start + 0.15], [0, 1]);
  const x = useTransform(progress, [start, start + 0.2], [24, 0]);

  return (
    <motion.div
      style={{ opacity, x }}
      className={cn(
        "absolute z-20 hidden items-center gap-1.5 rounded-md border border-white/10 bg-[#12151c]/95 px-2 py-1.5 shadow-[0_12px_30px_-12px_rgba(0,0,0,0.9)] backdrop-blur lg:flex",
        className,
      )}
    >
      {children}
      <span className="hidden font-mono text-[6px] uppercase tracking-[0.1em] text-[#4ade80] xl:inline">
        indexed
      </span>
      <ArrowRight aria-hidden className="h-2.5 w-2.5 text-[#4ade80]" />
    </motion.div>
  );
}

export function KnowledgeStoryVisual({ progress }: StoryVisualProps) {
  const fill = useTransform(progress, [0.12, 0.5], [0.15, 1]);
  const agentOpacity = useTransform(progress, [0.28, 0.5], [0, 1]);
  const agentY = useTransform(progress, [0.28, 0.5], [12, 0]);
  const readyOpacity = useTransform(progress, [0.3, 0.5], [0.45, 1]);

  const documents = [
    { name: "catalogue.pdf", meta: "PDF · 2.4 MB", status: "Ready" },
    { name: "delivery-policy.pdf", meta: "PDF · 380 KB", status: "Ready" },
    { name: "price-list.docx", meta: "DOCX · 96 KB", status: "Ready" },
  ];

  return (
    <div className="relative h-full w-full">
      <div className="absolute inset-0 mx-auto max-w-[650px]">
        <IncomingSource progress={progress} delay={0.02} className="left-[1%] top-[18%]">
          <FileText aria-hidden className="h-3 w-3 text-[#818cf8]" />
          <span className="font-mono text-[7px] text-[#c7d2fe]">catalogue.pdf</span>
        </IncomingSource>
        <IncomingSource progress={progress} delay={0.12} className="left-[3%] top-[40%]">
          <Globe2 aria-hidden className="h-3 w-3 text-[#818cf8]" />
          <span className="font-mono text-[7px] text-[#c7d2fe]">website</span>
        </IncomingSource>

        <div className="absolute right-0 top-[2%] h-[82%] w-[88%] max-lg:w-full">
          <MockWindow
            url="botbasex.com/workspaces/knowledge"
            className="h-full"
            contentClassName="flex"
          >
            <div className="flex w-8 shrink-0 flex-col items-center gap-3 border-r border-white/10 bg-[#0e1116] py-2 sm:w-10">
              <BotBaseMark className="h-4 w-4" />
              <span className="h-4 w-4 rounded bg-[#6366f1]/20 ring-1 ring-inset ring-[#818cf8]/30" />
              <span className="h-4 w-4 rounded bg-white/5" />
              <span className="h-4 w-4 rounded bg-white/5" />
              <span className="mt-auto h-4 w-4 rounded-full bg-white/10" />
            </div>

            <div className="flex min-w-0 flex-1 flex-col">
              <div className="flex items-center justify-between gap-2 border-b border-white/10 px-2.5 py-2 sm:px-3">
                <div className="min-w-0">
                  <p className="text-[9px] font-medium leading-3 text-[#f4f4f5] sm:text-[10px]">
                    Knowledge
                  </p>
                  <p className="truncate font-mono text-[6px] uppercase tracking-[0.12em] text-[#6b7280]">
                    Kilimanjaro Coffee
                  </p>
                </div>
                <span className="inline-flex items-center gap-1 rounded bg-[#6366f1] px-1.5 py-1 text-[6.5px] font-medium text-white sm:text-[7px]">
                  <Layers3 aria-hidden className="h-2 w-2" />
                  Add knowledge
                </span>
              </div>

              <div className="flex shrink-0 items-center gap-3 border-b border-white/10 px-2.5 py-1.5 font-mono text-[6.5px] uppercase tracking-[0.1em] text-[#6b7280] sm:px-3">
                <span className="border-b border-[#818cf8] pb-1 text-[#c7d2fe]">Documents</span>
                <span>Website</span>
                <span className="ml-auto text-[#4ade80]">3 / 3 ready</span>
              </div>

              <div className="flex flex-1 flex-col gap-2 p-1.5 sm:p-2">
                <div className="space-y-1">
                  {documents.map((document) => (
                    <div
                      key={document.name}
                      className="flex items-center gap-2 rounded-md border border-white/10 bg-[#12151c] px-2 py-1.5"
                    >
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded border border-[#818cf8]/20 bg-[#6366f1]/10 text-[#a5b4fc]">
                        <FileText aria-hidden className="h-2.5 w-2.5" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[7.5px] leading-3 text-[#e8eaf0]">
                          {document.name}
                        </p>
                        <p className="truncate font-mono text-[5.5px] text-[#6b7280]">
                          {document.meta}
                        </p>
                      </div>
                      <StatusPill tone="green">{document.status}</StatusPill>
                    </div>
                  ))}

                  <div className="flex items-center gap-2 rounded-md border border-white/10 bg-[#12151c] px-2 py-1.5">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded border border-[#818cf8]/20 bg-[#6366f1]/10 text-[#a5b4fc]">
                      <Globe2 aria-hidden className="h-2.5 w-2.5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[7.5px] leading-3 text-[#e8eaf0]">
                        kilimanjarocoffee.co.tz
                      </p>
                      <p className="truncate font-mono text-[5.5px] text-[#6b7280]">
                        Website source · connected
                      </p>
                    </div>
                    <StatusPill tone="green">indexed</StatusPill>
                  </div>
                </div>

                <div className="hidden grid-cols-3 gap-1 lg:grid">
                  {[
                    ["Documents", "3"],
                    ["Website", "1"],
                    ["Sources", "4"],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      className="rounded-md border border-white/10 bg-[#0e1116] px-1.5 py-1.5"
                    >
                      <p className="truncate font-mono text-[5px] uppercase tracking-[0.1em] text-[#6b7280]">
                        {label}
                      </p>
                      <p className="mt-0.5 text-[9px] font-medium leading-3 text-[#e8eaf0]">
                        {value}
                      </p>
                    </div>
                  ))}
                </div>

                <div className="mt-auto hidden rounded-md border border-white/10 bg-[#0e1116] px-2 py-1.5 lg:block">
                  <div className="flex items-center justify-between font-mono text-[5px] uppercase tracking-[0.1em] text-[#6b7280]">
                    <span>Training pipeline</span>
                    <span className="text-[#4ade80]">complete</span>
                  </div>
                  <div className="mt-1.5 flex items-center gap-1">
                    {["Extract", "Index", "Ground"].map((step, index) => (
                      <React.Fragment key={step}>
                        <span className="flex min-w-0 flex-1 items-center gap-1 rounded bg-[#12151c] px-1 py-1">
                          <span className="flex h-2.5 w-2.5 shrink-0 items-center justify-center rounded-full bg-[#4ade80]/15 text-[#4ade80]">
                            <Check aria-hidden className="h-1.5 w-1.5" />
                          </span>
                          <span className="truncate text-[5.5px] text-[#9aa3b2]">{step}</span>
                        </span>
                        {index < 2 && (
                          <ArrowRight aria-hidden className="h-2 w-2 shrink-0 text-[#4b5563]" />
                        )}
                      </React.Fragment>
                    ))}
                  </div>
                </div>
              </div>

              <div className="hidden space-y-1.5 border-t border-white/10 px-2.5 py-2 sm:px-3 lg:block">
                <div className="flex items-center justify-between font-mono text-[5.5px] uppercase tracking-[0.12em] text-[#6b7280]">
                  <span>Building the knowledge base</span>
                  <motion.span style={{ opacity: readyOpacity }} className="text-[#4ade80]">
                    complete
                  </motion.span>
                </div>
                <div className="h-1 overflow-hidden rounded-full bg-white/10">
                  <motion.div
                    style={{ scaleX: fill }}
                    className="h-full origin-left rounded-full bg-[linear-gradient(90deg,#4f46e5,#818cf8)]"
                  />
                </div>
              </div>
            </div>
          </MockWindow>
        </div>

        <motion.div
          style={{ opacity: agentOpacity, y: agentY }}
          className="absolute bottom-[1%] right-[1%] z-30 hidden w-[44%] max-w-[236px] rounded-xl border border-white/15 bg-[#10131a] p-2.5 shadow-[0_24px_60px_-18px_rgba(0,0,0,0.9)] backdrop-blur lg:block"
        >
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-full border border-[#818cf8]/30 bg-[#6366f1]/15 text-[#c7d2fe]">
              <Bot aria-hidden className="h-3.5 w-3.5" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[8.5px] font-medium text-[#f4f4f5]">
                Kilimanjaro Assistant
              </p>
              <p className="font-mono text-[6px] uppercase tracking-[0.12em] text-[#9aa3b2]">
                English · Live
              </p>
            </div>
            <TinyDot />
          </div>
          <div className="mt-2 flex flex-wrap gap-1">
            <StatusPill tone="indigo">Grounded</StatusPill>
            <StatusPill tone="green">3 sources</StatusPill>
          </div>
          <p className="mt-1.5 text-[6.5px] leading-3 text-[#9aa3b2]">
            The agent answers from your own material.
          </p>
        </motion.div>

        <div className="absolute bottom-[6%] left-[2%] z-10 hidden items-center gap-1.5 rounded-md border border-[#4ade80]/20 bg-[#0f1714]/95 px-2 py-1.5 shadow-lg sm:flex">
          <ShieldCheck aria-hidden className="h-3 w-3 text-[#4ade80]" />
          <span className="font-mono text-[6px] uppercase tracking-[0.1em] text-[#86efac]">
            source-cited answers
          </span>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 04 — The connected system                                                   */
/* -------------------------------------------------------------------------- */

function EcosystemNode({
  progress,
  start,
  icon: Icon,
  title,
  detail,
  meta,
  className,
}: {
  progress: MotionValue<number>;
  start: number;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  detail: string;
  meta: string;
  className?: string;
}) {
  const opacity = useTransform(progress, [start, start + 0.18], [0, 1]);
  const y = useTransform(progress, [start, start + 0.18], [14, 0]);

  return (
    <motion.div
      style={{ opacity, y }}
      className={cn(
        "absolute rounded-xl border border-white/10 bg-[#10131a]/96 p-3 shadow-[0_24px_60px_-22px_rgba(0,0,0,0.95)] backdrop-blur",
        className,
      )}
    >
      <div className="flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-md border border-[#818cf8]/20 bg-[#6366f1]/10 text-[#a5b4fc]">
          <Icon className="h-3 w-3" />
        </span>
        <span className="text-[9.5px] font-medium text-[#e8eaf0]">{title}</span>
        <TinyDot />
      </div>
      <p className="mt-2 hidden text-[7px] leading-[13px] text-[#9aa3b2] sm:block">{detail}</p>
      <p className="mt-1.5 font-mono text-[6px] uppercase tracking-[0.1em] text-[#818cf8]">
        {meta}
      </p>
    </motion.div>
  );
}

export function ConnectedStoryVisual({ progress }: StoryVisualProps) {
  const lineOpacity = useTransform(progress, [0.1, 0.3], [0, 0.9]);
  const dash = useTransform(progress, [0.1, 0.85], [34, 0]);
  const coreScale = useTransform(progress, [0.05, 0.35], [0.88, 1]);
  const coreOpacity = useTransform(progress, [0.03, 0.22], [0, 1]);
  const haloRotate = useTransform(progress, [0, 1], [0, 14]);

  return (
    <div className="relative h-full w-full">
      <div className="absolute inset-0 mx-auto max-w-[680px]">
        <div
          aria-hidden
          className="absolute left-1/2 top-1/2 h-[62%] w-[62%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#818cf8]/10 bg-[radial-gradient(circle,rgba(99,102,241,0.12),transparent_66%)]"
        />
        <svg
          aria-hidden
          className="pointer-events-none absolute inset-0 h-full w-full"
          viewBox="0 0 600 520"
          preserveAspectRatio="none"
          fill="none"
        >
          <defs>
            <linearGradient id="ecosystem-line" x1="0" y1="0" x2="1" y2="1">
              <stop stopColor="#818cf8" stopOpacity="0.7" />
              <stop offset="1" stopColor="#38bdf8" stopOpacity="0.22" />
            </linearGradient>
          </defs>
          {[
            "M 300 260 C 245 220, 205 180, 170 145",
            "M 300 260 C 355 218, 400 180, 438 142",
            "M 300 260 C 242 305, 202 345, 166 382",
            "M 300 260 C 358 305, 398 342, 438 382",
          ].map((path) => (
            <motion.path
              key={path}
              d={path}
              stroke="url(#ecosystem-line)"
              strokeWidth="1.2"
              strokeDasharray="4 7"
              style={{ opacity: lineOpacity, strokeDashoffset: dash }}
            />
          ))}
          <motion.circle
            cx="300"
            cy="260"
            r="88"
            stroke="#818cf8"
            strokeOpacity="0.18"
            strokeDasharray="2 8"
            style={{ opacity: lineOpacity }}
          />
        </svg>

        <motion.div
          style={{ opacity: coreOpacity, scale: coreScale, rotate: haloRotate }}
          className="absolute left-1/2 top-1/2 z-20 -translate-x-1/2 -translate-y-1/2"
        >
          <div className="relative flex h-28 w-28 items-center justify-center rounded-full border border-[#818cf8]/25 bg-[radial-gradient(circle_at_35%_30%,rgba(99,102,241,0.42),rgba(11,13,18,0.96)_70%)] shadow-[0_0_70px_-8px_rgba(99,102,241,0.6)] sm:h-36 sm:w-36">
            <span className="absolute inset-1.5 rounded-full border border-dashed border-[#93c5fd]/20" />
            <BotBaseMark className="h-14 w-14 sm:h-[72px] sm:w-[72px]" />
          </div>
          <div className="absolute left-1/2 top-full mt-2.5 -translate-x-1/2 whitespace-nowrap text-center">
            <p className="font-mono text-[6.5px] uppercase tracking-[0.2em] text-[#c7d2fe] sm:text-[7px]">
              One knowledge layer
            </p>
            <p className="mt-0.5 font-mono text-[5.5px] uppercase tracking-[0.14em] text-[#6b7280]">
              connected by BotBase
            </p>
          </div>
        </motion.div>

        <EcosystemNode
          progress={progress}
          start={0.1}
          icon={FileText}
          title="Knowledge"
          detail="Documents and website sources, indexed and refreshed."
          meta="grounded input"
          className="left-0 top-[1%] w-[42%] max-w-[250px] -rotate-2"
        />
        <EcosystemNode
          progress={progress}
          start={0.16}
          icon={Bot}
          title="Agents"
          detail="Personality, language, model and welcome message."
          meta="your assistant"
          className="right-0 top-[7%] w-[42%] max-w-[250px] rotate-2"
        />
        <EcosystemNode
          progress={progress}
          start={0.22}
          icon={Code2}
          title="Widgets"
          detail="Website embed or a hosted chat link."
          meta="customer-facing"
          className="bottom-[3%] left-[1%] w-[42%] max-w-[250px] rotate-1"
        />
        <EcosystemNode
          progress={progress}
          start={0.28}
          icon={Terminal}
          title="Developer API"
          detail="Workspace-scoped keys for your own interface."
          meta="build on it"
          className="bottom-[1%] right-[1%] w-[42%] max-w-[250px] -rotate-1"
        />

        <div className="absolute bottom-[28%] left-1/2 z-10 hidden -translate-x-1/2 items-center gap-1.5 rounded-full border border-white/10 bg-[#0b0d12]/90 px-2.5 py-1 font-mono text-[6px] uppercase tracking-[0.12em] text-[#9aa3b2] backdrop-blur sm:flex">
          <TinyDot />
          same source · every channel
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 05 — Calm, minimal, focused                                                 */
/* -------------------------------------------------------------------------- */

export function FocusStoryVisual({ progress }: StoryVisualProps) {
  const bubble1Opacity = useTransform(progress, [0.08, 0.18], [0, 1]);
  const bubble1Y = useTransform(progress, [0.08, 0.18], [10, 0]);
  const bubble2Opacity = useTransform(progress, [0.2, 0.32], [0, 1]);
  const bubble2Y = useTransform(progress, [0.2, 0.32], [10, 0]);
  const sourceOpacity = useTransform(progress, [0.34, 0.44], [0, 1]);

  return (
    <div className="relative h-full w-full">
      <div className="absolute inset-0 mx-auto max-w-[560px]">
        <div
          aria-hidden
          className="absolute left-1/2 top-1/2 h-[78%] w-[78%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#818cf8]/10 bg-[radial-gradient(circle,rgba(99,102,241,0.12),transparent_66%)]"
        />
        <div
          aria-hidden
          className="absolute left-1/2 top-1/2 h-[58%] w-[58%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-dashed border-[#818cf8]/15"
        />

        <div className="absolute left-1/2 top-1/2 h-[84%] w-[88%] -translate-x-1/2 -translate-y-1/2 sm:w-[78%]">
          <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-white/12 bg-[#10131a]/96 shadow-[0_36px_90px_-26px_rgba(0,0,0,0.95)] backdrop-blur">
            <div className="flex shrink-0 items-center gap-2 border-b border-white/10 px-3 py-2.5">
              <span className="flex h-7 w-7 items-center justify-center rounded-full border border-[#818cf8]/30 bg-[#6366f1]/15 text-[#c7d2fe]">
                <Bot aria-hidden className="h-3.5 w-3.5" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[9px] font-medium text-[#f4f4f5] sm:text-[10px]">
                  Kilimanjaro Assistant
                </p>
                <p className="flex items-center gap-1 font-mono text-[6px] uppercase tracking-[0.12em] text-[#4ade80]">
                  <TinyDot />
                  online
                </p>
              </div>
              <StatusPill tone="indigo">cites sources</StatusPill>
            </div>

            <div className="flex min-h-0 flex-1 flex-col justify-center gap-2 p-2.5 sm:gap-2.5 sm:p-3">
              <div className="mb-1 flex items-center gap-2 self-center font-mono text-[5.5px] uppercase tracking-[0.16em] text-[#4b5563]">
                <span className="h-px w-5 bg-white/10" />
                Today
                <span className="h-px w-5 bg-white/10" />
              </div>

              <motion.div
                style={{ opacity: bubble1Opacity, y: bubble1Y }}
                className="ml-auto w-[82%] rounded-xl rounded-br-sm bg-[#6366f1] px-2.5 py-1.5 text-[8px] leading-[12px] text-white sm:text-[9px] sm:leading-4"
              >
                What coffee works best for espresso?
              </motion.div>

              <motion.div style={{ opacity: bubble2Opacity, y: bubble2Y }} className="w-[92%]">
                <div className="rounded-xl rounded-bl-sm border border-white/10 bg-[#181b23] px-2.5 py-2 text-[8px] leading-[12px] text-[#e8eaf0] sm:text-[9px] sm:leading-4">
                  Our Dark Roast is the espresso pick — chocolate, caramel, low
                  acidity. Whole bean or ground.
                </div>
                <motion.div style={{ opacity: sourceOpacity }} className="mt-1.5">
                  <SourceBadge>catalogue.pdf · #12</SourceBadge>
                </motion.div>
              </motion.div>

              <motion.div
                style={{ opacity: sourceOpacity }}
                className="flex items-center gap-1.5 self-start rounded-full border border-[#4ade80]/15 bg-[#4ade80]/5 px-2 py-1"
              >
                <Check aria-hidden className="h-2.5 w-2.5 text-[#4ade80]" />
                <span className="font-mono text-[5.5px] uppercase tracking-[0.12em] text-[#86efac]">
                  answered from your content
                </span>
              </motion.div>
            </div>

            <div className="flex shrink-0 items-center gap-1.5 border-t border-white/10 px-2.5 py-2">
              <span className="min-w-0 flex-1 truncate rounded-md border border-white/10 bg-[#0e1116] px-2 py-1.5 text-[7px] text-[#6b7280] sm:text-[8px]">
                Ask anything about the business…
              </span>
              <span className="flex h-6 w-6 items-center justify-center rounded-md bg-[#6366f1] text-white">
                <Send aria-hidden className="h-2.5 w-2.5" />
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 06 — Resolve / final CTA                                                    */
/* -------------------------------------------------------------------------- */

export function FinalStoryVisual({ progress }: StoryVisualProps) {
  const ringScale = useTransform(progress, [0, 1], [0.92, 1.03]);
  const ringOpacity = useTransform(progress, [0.1, 0.5], [0.2, 0.8]);
  const coreOpacity = useTransform(progress, [0.08, 0.38], [0, 1]);
  const chipOpacity = useTransform(progress, [0.3, 0.55], [0, 1]);
  const chipY = useTransform(progress, [0.3, 0.55], [10, 0]);
  const snippetOpacity = useTransform(progress, [0.42, 0.66], [0, 1]);

  return (
    <div className="relative h-full w-full">
      <div className="absolute inset-0 mx-auto max-w-[600px]">
        <div className="absolute left-1/2 top-[45%] aspect-square w-[74%] max-w-[420px] -translate-x-1/2 -translate-y-1/2">
          <motion.div
            style={{ scale: ringScale, opacity: ringOpacity }}
            className="absolute inset-0 rounded-full border border-[#818cf8]/20 bg-[radial-gradient(circle_at_50%_45%,rgba(99,102,241,0.22),transparent_62%)]"
          />
          <motion.div
            style={{ scale: ringScale }}
            className="absolute inset-[12%] rounded-full border border-dashed border-[#93c5fd]/25"
          />
          <div className="absolute inset-[27%] rounded-full border border-[#818cf8]/30 bg-[#0b0d12]/80" />
          <motion.div
            style={{ opacity: coreOpacity }}
            className="absolute inset-0 flex items-center justify-center"
          >
            <div className="relative flex h-24 w-24 items-center justify-center rounded-full border border-[#818cf8]/35 bg-[#10131a] shadow-[0_0_70px_-6px_rgba(99,102,241,0.65)] sm:h-32 sm:w-32">
              <BotBaseMark className="h-14 w-14 sm:h-[74px] sm:w-[74px]" />
              <span className="absolute -bottom-6 whitespace-nowrap font-mono text-[6px] uppercase tracking-[0.22em] text-[#c7d2fe] sm:text-[7px]">
                BotBase
              </span>
            </div>
          </motion.div>

          <motion.div
            style={{ opacity: chipOpacity, y: chipY }}
            className="absolute left-0 top-[20%] -rotate-2 rounded-lg border border-white/10 bg-[#12151c]/95 px-2 py-1.5 shadow-lg backdrop-blur"
          >
            <span className="flex items-center gap-1.5 text-[7.5px] text-[#e8eaf0]">
              <FileText aria-hidden className="h-2.5 w-2.5 text-[#818cf8]" />
              Knowledge indexed
            </span>
          </motion.div>
          <motion.div
            style={{ opacity: chipOpacity, y: chipY }}
            className="absolute right-0 top-[42%] rotate-2 rounded-lg border border-white/10 bg-[#12151c]/95 px-2 py-1.5 shadow-lg backdrop-blur"
          >
            <span className="flex items-center gap-1.5 text-[7.5px] text-[#e8eaf0]">
              <Bot aria-hidden className="h-2.5 w-2.5 text-[#4ade80]" />
              Agent live
            </span>
          </motion.div>
          <motion.div
            style={{ opacity: chipOpacity, y: chipY }}
            className="absolute bottom-[7%] left-[6%] rotate-1 rounded-lg border border-white/10 bg-[#12151c]/95 px-2 py-1.5 shadow-lg backdrop-blur"
          >
            <span className="flex items-center gap-1.5 text-[7.5px] text-[#e8eaf0]">
              <Code2 aria-hidden className="h-2.5 w-2.5 text-[#a5b4fc]" />
              Widget embedded
            </span>
          </motion.div>
        </div>

        <motion.div
          style={{ opacity: snippetOpacity }}
          className="absolute bottom-[1%] right-[2%] hidden w-[48%] max-w-[268px] rounded-xl border border-white/12 bg-[#0e1116]/95 p-2.5 shadow-[0_24px_60px_-20px_rgba(0,0,0,0.95)] backdrop-blur sm:block"
        >
          <div className="flex items-center justify-between border-b border-white/10 pb-1.5">
            <span className="flex items-center gap-1 font-mono text-[6px] uppercase tracking-[0.14em] text-[#6b7280]">
              <KeyRound aria-hidden className="h-2.5 w-2.5 text-[#818cf8]" />
              embed snippet
            </span>
            <StatusPill tone="green">live</StatusPill>
          </div>
          <div className="mt-2 space-y-1 overflow-hidden font-mono text-[6px] leading-3 text-[#9aa3b2] sm:text-[6.5px]">
            <p className="text-[#6b7280]">{"// paste before </body>"}</p>
            <p>
              <span className="text-[#f472b6]">{"<script"}</span>{" "}
              <span className="text-[#a5b4fc]">src</span>=
              <span className="text-[#86efac]">&quot;…/widget.js&quot;</span>
            </p>
            <p className="pl-3">
              <span className="text-[#a5b4fc]">data-token</span>=
              <span className="text-[#86efac]">&quot;bbx_live_••••&quot;</span>
              <span className="text-[#f472b6]">{">"}</span>
              <span className="text-[#f472b6]">{"</script>"}</span>
            </p>
          </div>
          <p className="mt-2 flex items-center gap-1 text-[6px] text-[#9aa3b2]">
            <Check aria-hidden className="h-2.5 w-2.5 text-[#4ade80]" />
            Works on any website — no build step
          </p>
        </motion.div>
      </div>
    </div>
  );
}
