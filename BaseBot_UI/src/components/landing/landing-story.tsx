"use client";

import * as React from "react";
import Link from "next/link";
import {
  motion,
  useMotionValue,
  useMotionValueEvent,
  useScroll,
  useTransform,
  type MotionValue,
} from "motion/react";
import { ArrowRight, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import {
  ConnectedStoryVisual,
  FinalStoryVisual,
  FocusStoryVisual,
  FragmentedStoryVisual,
  HeroStoryVisual,
  KnowledgeStoryVisual,
  type StoryVisualProps,
} from "./story-visuals";

type StoryTone = "indigo" | "ember" | "resolve" | "connect" | "calm" | "final";

type StoryLine = {
  text: string;
  accent?: boolean;
};

type StoryAction = {
  href: string;
  label: string;
  variant: "primary" | "secondary";
};

type Story = {
  eyebrow: string;
  tone: StoryTone;
  lines: StoryLine[];
  body: string;
  note?: string;
  actions?: StoryAction[];
  Visual: React.ComponentType<StoryVisualProps>;
};

const STORY_COUNT = 6;

const STORIES: Story[] = [
  {
    eyebrow: "AI knowledge, handled",
    tone: "indigo",
    lines: [
      { text: "You run" },
      { text: "your business." },
      { text: "we handle the technology.", accent: true },
    ],
    body:
      "BotBase turns the documents, website and policies you already have into an AI assistant that answers customers instantly — with the source attached to every reply.",
    note: "No credit card · Works on any website · Live in minutes",
    actions: [
      { href: "/register", label: "Get started free", variant: "primary" },
      { href: "#how-it-works", label: "See how it works", variant: "secondary" },
    ],
    Visual: HeroStoryVisual,
  },
  {
    eyebrow: "The cost of complexity",
    tone: "ember",
    lines: [
      { text: "Technology" },
      { text: "shouldn't" },
      { text: "slow you down.", accent: true },
    ],
    body:
      "The answer is buried in a PDF. The price changed last month. A customer is waiting while your team searches three tools and one inbox. Growth gets bottlenecked by the systems meant to support it.",
    Visual: FragmentedStoryVisual,
  },
  {
    eyebrow: "The BotBase way",
    tone: "resolve",
    lines: [
      { text: "You take care" },
      { text: "of your" },
      { text: "customers." },
      { text: "we take care of", accent: true },
      { text: "the technology.", accent: true },
    ],
    body:
      "Upload the catalogue, connect the website, or point us at the knowledge you already use. BotBase indexes it, trains the agent and keeps every answer grounded in your own content.",
    Visual: KnowledgeStoryVisual,
  },
  {
    eyebrow: "One connected system",
    tone: "connect",
    lines: [
      { text: "More than" },
      { text: "software." },
      { text: "everything working together.", accent: true },
    ],
    body:
      "Documents, website pages, agents, widgets, hosted chat links and your API — connected through one knowledge layer. Update the source once, and the answers follow.",
    Visual: ConnectedStoryVisual,
  },
  {
    eyebrow: "The quiet advantage",
    tone: "calm",
    lines: [
      { text: "Less time" },
      { text: "figuring out technology.", accent: true },
      { text: "More time" },
      { text: "building your business.", accent: true },
    ],
    body:
      "When customers get instant, cited answers, your team gets its attention back. That's the whole point.",
    Visual: FocusStoryVisual,
  },
  {
    eyebrow: "Your next move",
    tone: "final",
    lines: [
      { text: "Your next move" },
      { text: "starts here.", accent: true },
    ],
    body:
      "Bring the documents you already have. BotBase handles the knowledge, the agent and the widget — so you can get back to your business.",
    note: "21-day Pro trial · No card required",
    actions: [
      { href: "/register", label: "Get started free", variant: "primary" },
      { href: "/pricing", label: "See pricing", variant: "secondary" },
    ],
    Visual: FinalStoryVisual,
  },
];

type SlideRange = {
  enterStart: number;
  enterEnd: number;
  exitStart: number;
  exitEnd: number;
};

function getSlideRange(index: number): SlideRange {
  const span = 1 / STORY_COUNT;
  const overlap = 0.028;
  const start = index * span;
  const end = (index + 1) * span;

  if (index === 0) {
    return { enterStart: 0, enterEnd: 0.03, exitStart: end - overlap, exitEnd: end + overlap };
  }

  if (index === STORY_COUNT - 1) {
    return {
      enterStart: start - overlap,
      enterEnd: start + overlap,
      // Keep the final composition on screen as the sticky section releases.
      exitStart: 0.999,
      exitEnd: 1,
    };
  }

  return {
    enterStart: start - overlap,
    enterEnd: start + overlap,
    exitStart: end - overlap,
    exitEnd: end + overlap,
  };
}

/**
 * Interpolate a scroll range ourselves instead of asking Motion to accelerate
 * it through WAAPI. The accelerated path requires offsets inside [0, 1]; some
 * chapter ranges intentionally sit at the edges, and clamping here also keeps
 * copy perfectly still once its reveal has finished.
 */
function useScrollTransform<T extends number | string>(
  progress: MotionValue<number>,
  inputRange: readonly number[],
  outputRange: readonly T[],
): MotionValue<T> {
  return useTransform(progress, (value) => {
    const lastIndex = inputRange.length - 1;
    if (value <= inputRange[0]) return outputRange[0];
    if (value >= inputRange[lastIndex]) return outputRange[lastIndex];

    let index = 0;
    while (index < lastIndex && value > inputRange[index + 1]) index += 1;

    const span = inputRange[index + 1] - inputRange[index];
    const t = span === 0 ? 0 : (value - inputRange[index]) / span;
    const from = outputRange[index];
    const to = outputRange[index + 1];

    if (typeof from === "number" && typeof to === "number") {
      return (from + (to - from) * t) as T;
    }

    if (typeof from === "string" && typeof to === "string") {
      const fromParts = /^(-?\d*\.?\d+)(.*)$/.exec(from);
      const toParts = /^(-?\d*\.?\d+)(.*)$/.exec(to);
      if (fromParts && toParts && fromParts[2] === toParts[2]) {
        const start = Number(fromParts[1]);
        const finish = Number(toParts[1]);
        return `${start + (finish - start) * t}${fromParts[2]}` as T;
      }
    }

    return (t < 1 ? from : to) as T;
  });
}

function useReveal(
  progress: MotionValue<number>,
  start: number,
  end: number,
  distance = 14,
  revealed = false,
) {
  const opacity = useScrollTransform(
    progress,
    [start, end],
    revealed ? [1, 1] : [0, 1],
  );
  const y = useScrollTransform(
    progress,
    [start, end],
    revealed ? [0, 0] : [distance, 0],
  );
  return { opacity, y };
}

/* -------------------------------------------------------------------------- */
/* Copy primitives                                                             */
/* -------------------------------------------------------------------------- */

function StoryEyebrow({
  index,
  label,
  style,
}: {
  index: number;
  label: string;
  style?: React.ComponentProps<typeof motion.div>["style"];
}) {
  return (
    <motion.div
      style={style}
      className="flex items-center gap-2.5 font-mono text-[9px] uppercase tracking-[0.2em] text-accent-300 sm:tracking-[0.22em] lg:text-[10px]"
    >
      <span aria-hidden className="h-px w-6 bg-accent-500/60" />
      <span>{label}</span>
      <span className="ml-auto hidden text-tertiary sm:inline">
        {String(index + 1).padStart(2, "0")} / {String(STORY_COUNT).padStart(2, "0")}
      </span>
    </motion.div>
  );
}

function HeadlineLine({
  line,
  progress,
  start,
  end,
  exitStart,
  exitEnd,
  initiallyVisible = false,
  holdAtEnd = false,
}: {
  line: StoryLine;
  progress: MotionValue<number>;
  start: number;
  end: number;
  exitStart: number;
  exitEnd: number;
  initiallyVisible?: boolean;
  holdAtEnd?: boolean;
}) {
  const y = useScrollTransform(
    progress,
    holdAtEnd ? [start, end] : [start, end, exitStart, exitEnd],
    holdAtEnd
      ? initiallyVisible
        ? ["0%", "0%"]
        : ["112%", "0%"]
      : initiallyVisible
        ? ["0%", "0%", "0%", "-34%"]
        : ["112%", "0%", "0%", "-34%"],
  );
  const opacity = useScrollTransform(
    progress,
    [start, end],
    initiallyVisible ? [1, 1] : [0, 1],
  );

  return (
    <span className="block overflow-hidden pb-[0.1em]">
      <motion.span
        style={{ y, opacity }}
        className={cn(
          "block",
          line.accent
            ? "story-accent mt-0.5 text-[0.74em] font-light leading-[1.04] tracking-[-0.025em] sm:mt-1"
            : "font-semibold uppercase leading-[0.95] tracking-[-0.05em]",
        )}
      >
        {line.text}{" "}
      </motion.span>
    </span>
  );
}

function StoryHeadline({
  index,
  lines,
  progress,
  range,
}: {
  index: number;
  lines: StoryLine[];
  progress: MotionValue<number>;
  range: SlideRange;
}) {
  const Tag = index === 0 ? "h1" : "h2";
  const isFirst = index === 0;

  return (
    <Tag
      aria-label={lines.map((line) => line.text).join(" ")}
      className="story-heading mt-4 text-[clamp(2.15rem,7.4vw,3.3rem)] leading-[0.95] text-primary lg:mt-5 lg:text-[clamp(2.6rem,4.5vw,4.6rem)]"
    >
      {lines.map((line, lineIndex) => {
        const start = isFirst
          ? 0
          : range.enterStart - 0.014 + lineIndex * 0.006;
        const end = isFirst ? 0.001 : start + 0.022;

        return (
          <HeadlineLine
            key={`${line.text}-${lineIndex}`}
            line={line}
            progress={progress}
            start={start}
            end={end}
            exitStart={range.exitStart}
            exitEnd={range.exitEnd}
            initiallyVisible={isFirst}
            holdAtEnd={index === STORY_COUNT - 1}
          />
        );
      })}
    </Tag>
  );
}

function StoryActions({
  actions,
  active,
}: {
  actions: StoryAction[];
  active: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2.5">
      {actions.map((action) => (
        <Button
          key={action.href}
          asChild
          variant={action.variant}
          size="lg"
          iconRight={
            action.variant === "primary" ? (
              <ArrowRight aria-hidden className="h-4 w-4" />
            ) : undefined
          }
        >
          <Link href={action.href} tabIndex={active ? undefined : -1}>
            {action.label}
          </Link>
        </Button>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* The pinned, scroll-scrubbed sequence                                        */
/* -------------------------------------------------------------------------- */

function StoryBackdrop({ tone }: { tone: StoryTone }) {
  return (
    <div aria-hidden className="absolute inset-0 overflow-hidden">
      <div className={cn("story-scene", `story-scene--${tone}`)} />
      <div className="story-grid absolute inset-0" />
      <div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-canvas/55 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-canvas/60 to-transparent" />
    </div>
  );
}

function StorySlide({
  story,
  index,
  progress,
  active,
}: {
  story: Story;
  index: number;
  progress: MotionValue<number>;
  active: boolean;
}) {
  const isFirst = index === 0;
  const isLast = index === STORY_COUNT - 1;
  const range = getSlideRange(index);
  const nominalStart = index / STORY_COUNT;
  const nominalEnd = (index + 1) / STORY_COUNT;

  const slidePoints = isLast
    ? [range.enterStart, range.enterEnd]
    : isFirst
      ? [0, range.exitStart, range.exitEnd]
      : [range.enterStart, range.enterEnd, range.exitStart, range.exitEnd];

  const textOpacity = useScrollTransform(
    progress,
    isFirst
      ? [0, nominalEnd - 0.045, nominalEnd - 0.022]
      : isLast
        ? [nominalStart - 0.025, nominalStart - 0.002]
        : [
            nominalStart - 0.025,
            nominalStart - 0.002,
            nominalEnd - 0.045,
            nominalEnd - 0.022,
          ],
    isFirst ? [1, 1, 0] : isLast ? [0, 1] : [0, 1, 1, 0],
  );

  const visualOpacity = useScrollTransform(
    progress,
    isFirst
      ? [0, nominalEnd - 0.04, nominalEnd - 0.018]
      : isLast
        ? [nominalStart - 0.035, nominalStart - 0.008]
        : [
            nominalStart - 0.035,
            nominalStart - 0.008,
            nominalEnd - 0.04,
            nominalEnd - 0.018,
          ],
    isFirst ? [1, 1, 0] : isLast ? [0, 1] : [0, 1, 1, 0],
  );

  const opacity = useScrollTransform(
    progress,
    slidePoints,
    isLast ? [0, 1] : isFirst ? [1, 1, 0] : [0, 1, 1, 0],
  );

  const textY = useScrollTransform(
    progress,
    slidePoints,
    isLast ? [42, 0] : isFirst ? [0, 0, -28] : [42, 0, 0, -26],
  );

  const visualX = useScrollTransform(
    progress,
    slidePoints,
    isLast ? [60, 0] : isFirst ? [0, 0, -44] : [60, 0, 0, -42],
  );
  const visualY = useScrollTransform(
    progress,
    slidePoints,
    isLast ? [18, 0] : isFirst ? [0, 0, -10] : [18, 0, 0, -12],
  );
  const visualScale = useScrollTransform(
    progress,
    slidePoints,
    isLast ? [0.94, 1] : isFirst ? [1, 1, 0.97] : [0.94, 1, 1, 0.97],
  );
  const visualRotate = useScrollTransform(
    progress,
    slidePoints,
    isLast ? [2.4, 0] : isFirst ? [0, 0, -1.1] : [2.4, 0, 0, -1.1],
  );

  const localProgress = useScrollTransform<number>(
    progress,
    isFirst ? [0, range.exitEnd] : [range.enterStart, isLast ? 1 : range.exitEnd],
    [0, 1],
  );

  const eyebrowReveal = useReveal(
    progress,
    isFirst ? 0 : range.enterStart - 0.005,
    isFirst ? 0.001 : range.enterStart + 0.018,
    8,
    isFirst,
  );
  const copyReveal = useReveal(
    progress,
    isFirst ? 0 : range.enterStart + 0.012,
    isFirst ? 0.001 : range.enterStart + 0.036,
    16,
    isFirst,
  );
  const actionReveal = useReveal(
    progress,
    isFirst ? 0 : range.enterStart + 0.032,
    isFirst ? 0.001 : range.enterStart + 0.06,
    14,
    isFirst,
  );
  const noteReveal = useReveal(
    progress,
    isFirst ? 0 : range.enterStart + 0.048,
    isFirst ? 0.001 : range.enterStart + 0.077,
    10,
    isFirst,
  );

  return (
    <motion.div
      className={cn(
        "absolute inset-0 z-10",
        !active && "pointer-events-none",
      )}
      data-story={index + 1}
    >
      <motion.div aria-hidden style={{ opacity }} className="absolute inset-0">
        <StoryBackdrop tone={story.tone} />
      </motion.div>      <div className="story-slide-grid relative z-10 mx-auto grid h-full w-full max-w-[1400px] grid-rows-[auto_minmax(0,1fr)] items-center gap-3 px-4 pb-5 pt-[4.5rem] sm:px-6 sm:pb-6 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)] lg:grid-rows-1 lg:gap-10 lg:px-10 lg:pb-12 lg:pt-24">
        <motion.div
          style={{ y: textY, opacity: textOpacity }}
          className="story-copy-block relative z-10 max-w-[640px]"
        >
          <StoryEyebrow
            index={index}
            label={story.eyebrow}
            style={{ opacity: eyebrowReveal.opacity, y: eyebrowReveal.y }}
          />

          <StoryHeadline
            index={index}
            lines={story.lines}
            progress={progress}
            range={range}
          />

          <motion.p
            style={{ opacity: copyReveal.opacity, y: copyReveal.y }}
            className="story-body mt-3 max-w-[54ch] text-[13px] leading-[20px] text-secondary sm:mt-5 sm:text-[15px] sm:leading-[24px]"
          >
            {story.body}
          </motion.p>

          {story.actions && (
            <motion.div
              style={{ opacity: actionReveal.opacity, y: actionReveal.y }}
              className="story-actions mt-4 sm:mt-6"
            >
              <StoryActions actions={story.actions} active={active} />
            </motion.div>
          )}

          {story.note && (
            <motion.p
              style={{ opacity: noteReveal.opacity, y: noteReveal.y }}
              className="story-note mt-3 font-mono text-[9px] uppercase tracking-[0.12em] text-tertiary sm:mt-4"
            >
              {story.note}
            </motion.p>
          )}
        </motion.div>

        <motion.div
          style={{
            opacity: visualOpacity,
            x: visualX,
            y: visualY,
            scale: visualScale,
            rotate: visualRotate,
          }}
          className="story-visual relative h-full min-h-[150px] w-full"
          aria-hidden
        >
          <div
            className="story-float h-full w-full"
            style={{ animationPlayState: active ? "running" : "paused" }}
          >
            <story.Visual progress={localProgress} />
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
}

function StoryRail({
  active,
  progress,
}: {
  active: number;
  progress: MotionValue<number>;
}) {
  const scaleY = useScrollTransform(progress, [0, 1], [0.015, 1]);

  return (
    <div
      aria-hidden
      className="pointer-events-none absolute right-5 top-1/2 z-30 hidden -translate-y-1/2 flex-col items-center gap-3 xl:flex"
    >
      <span className="font-mono text-[10px] tracking-[0.14em] text-primary">
        {String(active + 1).padStart(2, "0")}
      </span>
      <div className="relative h-36 w-px overflow-hidden rounded-full bg-primary/15">
        <motion.div
          style={{ scaleY }}
          className="absolute inset-0 origin-top rounded-full bg-accent-400"
        />
      </div>
      <span className="font-mono text-[9px] tracking-[0.14em] text-tertiary">
        {String(STORY_COUNT).padStart(2, "0")}
      </span>
    </div>
  );
}

function PinnedStory() {
  const sectionRef = React.useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start start", "end end"],
  });
  const [active, setActive] = React.useState(0);

  useMotionValueEvent(scrollYProgress, "change", (value) => {
    const next = Math.min(
      STORY_COUNT - 1,
      Math.max(0, Math.floor(value * STORY_COUNT + 0.0001)),
    );
    setActive((current) => (current === next ? current : next));
  });

  const hintOpacity = useScrollTransform(scrollYProgress, [0, 0.035], [1, 0]);

  return (
    <section
      ref={sectionRef}
      aria-label="BotBase product story"
      className="relative h-[560vh] lg:h-[660vh]"
    >
      <div className="sticky top-0 h-[100svh] overflow-hidden">
        <div aria-hidden className="absolute inset-0 bg-canvas" />

        {STORIES.map((story, index) => (
          <StorySlide
            key={story.eyebrow}
            story={story}
            index={index}
            progress={scrollYProgress}
            active={index === active}
          />
        ))}

        <StoryRail active={active} progress={scrollYProgress} />

        <motion.div
          style={{ opacity: hintOpacity }}
          className="pointer-events-none absolute bottom-4 left-1/2 z-30 hidden -translate-x-1/2 items-center gap-2 font-mono text-[9px] uppercase tracking-[0.2em] text-tertiary sm:flex"
        >
          <span>Scroll to explore</span>
          <ChevronDown aria-hidden className="h-3 w-3 text-accent-300" />
        </motion.div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* Reduced-motion fallback — every chapter readable without pinning            */
/* -------------------------------------------------------------------------- */

function StaticStory() {
  const staticProgress = useMotionValue(1);

  return (
    <section
      aria-label="BotBase product story"
      className="border-b border-subtle bg-canvas pt-20"
    >
      <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-6 px-4 py-12 sm:px-6 lg:py-16">
        <h1 className="sr-only">
          BotBase — AI assistants built from the content you already have.
        </h1>
        {STORIES.map((story, index) => {
          const Tag = "h2";

          return (
            <article
              key={story.eyebrow}
              className="relative overflow-hidden rounded-xl border border-subtle bg-surface"
            >
              <div aria-hidden className="absolute inset-0">
                <div className={cn("story-scene", `story-scene--${story.tone}`)} />
                <div className="story-grid absolute inset-0" />
              </div>

              <div className="relative z-10 grid gap-8 p-6 sm:p-8 lg:grid-cols-[0.95fr_1.05fr] lg:items-center lg:gap-12 lg:p-12">
                <div>
                  <StoryEyebrow index={index} label={story.eyebrow} />
                  <Tag
                    aria-label={story.lines.map((line) => line.text).join(" ")}
                    className="mt-4 text-[clamp(2rem,5vw,3.6rem)] leading-[0.95] text-primary"
                  >
                    {story.lines.map((line, lineIndex) => (
                      <span
                        key={`${line.text}-${lineIndex}`}
                        className={cn(
                          "block",
                          line.accent
                            ? "story-accent mt-1 text-[0.74em] font-light leading-[1.04] tracking-[-0.025em]"
                            : "font-semibold uppercase leading-[0.95] tracking-[-0.05em]",
                        )}
                      >
                        {line.text}
                      </span>
                    ))}
                  </Tag>
                  <p className="mt-4 max-w-[54ch] text-[14px] leading-[22px] text-secondary sm:text-[15px] sm:leading-[24px]">
                    {story.body}
                  </p>
                  {story.actions && (
                    <div className="mt-6">
                      <StoryActions actions={story.actions} active />
                    </div>
                  )}
                  {story.note && (
                    <p className="mt-4 font-mono text-[9px] uppercase tracking-[0.12em] text-tertiary">
                      {story.note}
                    </p>
                  )}
                </div>

                <div className="relative h-[280px] sm:h-[380px]" aria-hidden>
                  <story.Visual progress={staticProgress} />
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export function LandingStory() {
  return (
    <>
      <noscript>
        <style>{`.motion-story{display:none!important}.reduce-story{display:block!important}`}</style>
      </noscript>
      <div className="motion-story">
        <PinnedStory />
      </div>
      <div className="reduce-story">
        <StaticStory />
      </div>
    </>
  );
}
