"use client";

import {
  Coffee,
  Mountain,
  Ship,
  ShoppingBag,
  Store,
  Truck,
  UtensilsCrossed,
} from "lucide-react";

const LOGOS = [
  { icon: Coffee, name: "Kilimanjaro Coffee" },
  { icon: Truck, name: "Dar Express" },
  { icon: Store, name: "Acme Store" },
  { icon: UtensilsCrossed, name: "Mama Ntilie Foods" },
  { icon: Mountain, name: "Serengeti Safaris" },
  { icon: Ship, name: "Tanga Freight" },
  { icon: ShoppingBag, name: "Swahili Mart" },
] as const;

/**
 * Prompt 3 — logo marquee below the hero. A subtle band (off-white in light
 * mode, matching surface in dark) with top and bottom borders, carrying an
 * infinite wordmark loop. Pure CSS motion: pauses on hover and goes static
 * under prefers-reduced-motion via the global rule.
 */
export function LogoMarquee() {
  return (
    <section
      aria-label="Trusted by businesses across Tanzania"
      className="group border-y border-subtle bg-surface"
    >
      <div className="mx-auto w-full max-w-[1200px] px-4 py-10 sm:px-6">
        <p className="text-center text-2xs font-medium uppercase tracking-widest text-tertiary">
          Trusted by growing businesses across Tanzania
        </p>

        <div className="mt-7 overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_12%,black_88%,transparent)]">
          <div className="flex w-max animate-marquee group-hover:[animation-play-state:paused]">
            {[0, 1].map((copy) => (
              <div
                key={copy}
                aria-hidden={copy === 1}
                className="flex shrink-0 items-center"
              >
                {LOGOS.map((logo) => {
                  const Icon = logo.icon;
                  return (
                    <span
                      key={`${copy}-${logo.name}`}
                      className="mx-8 inline-flex shrink-0 items-center gap-2 whitespace-nowrap text-secondary"
                    >
                      <Icon aria-hidden className="h-5 w-5 text-tertiary" />
                      <span className="text-lg font-semibold tracking-tight">
                        {logo.name}
                      </span>
                    </span>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
