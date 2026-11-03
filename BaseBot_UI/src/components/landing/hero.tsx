"use client";

import * as React from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { ArrowRight, Play, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

/**
 * Phase 1 — hero. Headline + dual CTA on the left, the BotBase product film
 * on the right. The film is a self-hosted MP4 with a poster so the hero never
 * shifts while it loads.
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

        {/* Product film — one clean, self-hosted loop. */}
        <motion.div
          {...item(0.15)}
          className="relative mx-auto w-full max-w-[560px]"
          aria-label="BotBase product film"
        >
          <div
            aria-hidden
            className="absolute -inset-6 rounded-[28px] bg-[radial-gradient(circle_at_50%_0%,rgba(99,102,241,0.28),transparent_65%)] blur-2xl"
          />
          <div className="relative aspect-video overflow-hidden rounded-lg border border-subtle bg-surface shadow-elevation-3">
            <video
              className="h-full w-full object-cover"
              autoPlay
              muted
              loop
              playsInline
              preload="metadata"
              poster="/videos/botbase-hero-poster.jpg"
              aria-label="BotBase turns your documents into an AI chat agent"
            >
              <source src="/videos/botbase-hero.mp4" type="video/mp4" />
            </video>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
