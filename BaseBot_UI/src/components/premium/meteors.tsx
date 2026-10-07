"use client";

import { cn } from "@/lib/cn";

/**
 * PREMIUM MOMENT 6 — Magic UI "Meteors", used once as the illustration behind
 * empty-state blocks. Lazy-loaded with next/dynamic.
 */
export function Meteors({
  count = 12,
  className,
}: {
  count?: number;
  className?: string;
}) {
  const spans = Array.from({ length: count }, (_, i) => {
    const left = `${(i * 97) % 100}%`;
    const top = `${(i * 53) % 100}%`;
    const delay = `${(i % 7) * 0.45}s`;
    const duration = `${3 + (i % 4) * 0.7}s`;
    return { left, top, delay, duration, key: i };
  });

  return (
    <div aria-hidden className={cn("overflow-hidden", className)}>
      {spans.map((span) => (
        <span
          key={span.key}
          className="pointer-events-none absolute -z-10 h-0.5 w-0.5 rotate-[215deg] animate-meteor rounded-full bg-accent-400/70 shadow-[0_0_0_1px_rgba(129,140,248,0.1)]"
          style={{
            left: span.left,
            top: span.top,
            animationDelay: span.delay,
            animationDuration: span.duration,
          }}
        />
      ))}
    </div>
  );
}

export default Meteors;