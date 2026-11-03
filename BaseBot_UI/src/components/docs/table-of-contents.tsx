"use client";

import * as React from "react";
import type { DocHeading } from "@/lib/docs/content";

export function TableOfContents({ headings }: { headings: DocHeading[] }) {
  const [active, setActive] = React.useState<string>("");

  React.useEffect(() => {
    if (!headings.length) return;
    const elements = headings
      .map((heading) => document.getElementById(heading.id))
      .filter((element): element is HTMLElement => Boolean(element));

    let frame = 0;
    const update = () => {
      frame = 0;
      let current = elements[0]?.id ?? "";
      for (const element of elements) {
        if (element.getBoundingClientRect().top <= 120) {
          current = element.id;
        } else {
          break;
        }
      }
      setActive(current);
    };
    const onScroll = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(update);
    };

    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [headings]);

  if (!headings.length) return null;

  return (
    <nav className="docs-toc" aria-label="On this page">
      <p className="docs-toc-title">On this page</p>
      <ul className="docs-toc-list">
        {headings.map((heading) => (
          <li key={heading.id}>
            <a
              href={`#${heading.id}`}
              className={`docs-toc-link depth-${heading.level}${
                active === heading.id ? " is-active" : ""
              }`}
              aria-current={active === heading.id ? "location" : undefined}
            >
              {heading.text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
