import * as React from "react";
import Link from "next/link";
import {
  Info,
  Lightbulb,
  ShieldAlert,
  TriangleAlert,
  ArrowRight,
} from "lucide-react";
import { CodeBlock, CodeTabs } from "./code-block";
import { slugify } from "@/lib/docs/content";

function textFromChildren(children: React.ReactNode): string {
  return React.Children.toArray(children)
    .map((child) => {
      if (typeof child === "string" || typeof child === "number") {
        return String(child);
      }
      if (React.isValidElement(child)) {
        return textFromChildren(
          (child.props as { children?: React.ReactNode }).children,
        );
      }
      return "";
    })
    .join("");
}

function MdxHeading({
  level,
  children,
}: {
  level: 2 | 3;
  children?: React.ReactNode;
}) {
  const text = textFromChildren(children);
  const id = slugify(text);
  const Tag = level === 2 ? "h2" : "h3";
  return (
    <Tag id={id}>
      <a
        href={`#${id}`}
        className="docs-heading-anchor"
        aria-label={`Link to ${text}`}
      >
        #
      </a>
      {children}
    </Tag>
  );
}

function MdxLink({
  href = "",
  children,
  ...props
}: React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  if (href.startsWith("/")) {
    return (
      <Link href={href} {...props}>
        {children}
      </Link>
    );
  }
  return (
    <a href={href} {...props}>
      {children}
    </a>
  );
}

function MdxPre({ children }: { children?: React.ReactNode }) {
  const child = React.Children.toArray(children)[0];
  if (React.isValidElement(child)) {
    const props = child.props as {
      className?: string;
      children?: React.ReactNode;
    };
    const match = /language-([\w-]+)/.exec(props.className ?? "");
    return (
      <CodeBlock
        code={textFromChildren(props.children)}
        language={match?.[1] ?? "text"}
      />
    );
  }
  return <pre className="docs-code-pre">{children}</pre>;
}

function MdxTable({ children }: { children?: React.ReactNode }) {
  return (
    <div className="docs-table-wrap">
      <table>{children}</table>
    </div>
  );
}

export function Callout({
  type = "note",
  title,
  children,
}: {
  type?: "note" | "tip" | "warning" | "danger";
  title?: string;
  children?: React.ReactNode;
}) {
  const Icon =
    type === "tip"
      ? Lightbulb
      : type === "warning"
        ? TriangleAlert
        : type === "danger"
          ? ShieldAlert
          : Info;

  return (
    <aside className="docs-callout" data-tone={type}>
      <Icon aria-hidden className="docs-callout-icon h-[18px] w-[18px]" />
      <div>
        {title && <p className="docs-callout-title">{title}</p>}
        <div className="docs-callout-body">{children}</div>
      </div>
    </aside>
  );
}

export function CardGrid({ children }: { children?: React.ReactNode }) {
  return <div className="docs-card-grid">{children}</div>;
}

export function Card({
  title,
  href,
  children,
}: {
  title: string;
  href?: string;
  children?: React.ReactNode;
}) {
  const content = (
    <>
      <p className="docs-card-title">{title}</p>
      <div className="docs-card-body">{children}</div>
      {href && (
        <span className="docs-card-arrow">
          Read guide <ArrowRight aria-hidden className="ml-1 inline h-3 w-3" />
        </span>
      )}
    </>
  );

  return href ? (
    <Link href={href} className="docs-card docs-card-link">
      {content}
    </Link>
  ) : (
    <div className="docs-card">{content}</div>
  );
}

export function Steps({ children }: { children?: React.ReactNode }) {
  return <ol className="docs-steps">{children}</ol>;
}

export function Step({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <li className="docs-step">
      <div>
        <p className="docs-step-title">{title}</p>
        <div className="docs-step-body">{children}</div>
      </div>
    </li>
  );
}

export function MdxComponents() {
  const components: Record<string, React.ElementType> = {
    h1: (props: React.HTMLAttributes<HTMLHeadingElement>) => <h1 {...props} />,
    h2: (props: { children?: React.ReactNode }) => (
      <MdxHeading level={2}>{props.children}</MdxHeading>
    ),
    h3: (props: { children?: React.ReactNode }) => (
      <MdxHeading level={3}>{props.children}</MdxHeading>
    ),
    a: MdxLink,
    pre: MdxPre,
    table: MdxTable,
    Callout,
    CardGrid,
    Card,
    Steps,
    Step,
    CodeTabs,
  };
  return components;
}
