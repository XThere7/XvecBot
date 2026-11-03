import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { MDXRemote } from "next-mdx-remote/rsc";
import remarkGfm from "remark-gfm";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { MdxComponents } from "@/components/docs/mdx-components";
import { TableOfContents } from "@/components/docs/table-of-contents";
import {
  getDocBySlug,
  getDocGroups,
  getDocNeighbours,
  getDocs,
} from "@/lib/docs/content";

type DocsPageProps = {
  params: Promise<{ slug?: string[] }>;
};

export const dynamicParams = false;

export function generateStaticParams() {
  return getDocs().map((page) => ({ slug: page.slug }));
}

export async function generateMetadata({
  params,
}: DocsPageProps): Promise<Metadata> {
  const { slug = [] } = await params;
  const page = getDocBySlug(slug);
  if (!page) return {};

  const isHome = page.slug.length === 0;
  const title = isHome
    ? "BotBase documentation — turn your content into an AI assistant"
    : `${page.title} · BotBase Docs`;

  return {
    title: { absolute: title },
    description: page.description,
    alternates: { canonical: page.href },
    openGraph: {
      title,
      description: page.description,
      url: page.href,
      siteName: "BotBase Docs",
      type: isHome ? "website" : "article",
    },
    twitter: {
      card: "summary",
      title,
      description: page.description,
    },
    robots: { index: true, follow: true },
  };
}

function readingTime(body: string) {
  const words = body
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/<[^>]+>/g, " ")
    .split(/\s+/)
    .filter(Boolean).length;
  return Math.max(1, Math.ceil(words / 220));
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(value));
}

export default async function DocsPage({ params }: DocsPageProps) {
  const { slug = [] } = await params;
  const page = getDocBySlug(slug);
  if (!page) notFound();

  const groups = getDocGroups();
  const groupFirst = groups
    .find((group) => group.name === page.group)
    ?.pages.at(0);
  const { previous, next } = getDocNeighbours(page.slug);
  const isHome = page.slug.length === 0;

  return (
    <div className="docs-page-grid">
      <article className="docs-article">
        <nav className="docs-breadcrumbs" aria-label="Breadcrumb">
          <Link href="/docs">Docs</Link>
          {!isHome && <span aria-hidden>/</span>}
          {!isHome && groupFirst && page.group !== "Home" ? (
            groupFirst.href === page.href ? (
              <span>{page.group}</span>
            ) : (
              <Link href={groupFirst.href}>{page.group}</Link>
            )
          ) : null}
          {!isHome && page.group !== "Home" && <span aria-hidden>/</span>}
          <span aria-current="page">{isHome ? "Overview" : page.title}</span>
        </nav>

        <h1>{page.title}</h1>
        <p className="docs-description">{page.description}</p>
        <p className="docs-meta-row">
          <span>{page.group}</span>
          <span aria-hidden>·</span>
          <span>{readingTime(page.body)} min read</span>
          <span aria-hidden>·</span>
          <span>Updated {formatDate(page.updatedAt)}</span>
        </p>

        <div className="docs-prose">
          <MDXRemote
            source={page.body}
            components={MdxComponents()}
            options={{
              mdxOptions: {
                remarkPlugins: [remarkGfm],
              },
            }}
          />
        </div>

        {(previous || next) && (
          <nav className="docs-pagination" aria-label="Documentation pages">
            {previous ? (
              <Link href={previous.href}>
                <span className="docs-pagination-label">
                  <ArrowLeft aria-hidden className="mr-1 inline h-3 w-3" />
                  Previous
                </span>
                <span className="docs-pagination-title">{previous.title}</span>
              </Link>
            ) : (
              <span />
            )}
            {next ? (
              <Link href={next.href} className="is-next">
                <span className="docs-pagination-label">
                  Next <ArrowRight aria-hidden className="ml-1 inline h-3 w-3" />
                </span>
                <span className="docs-pagination-title">{next.title}</span>
              </Link>
            ) : (
              <span />
            )}
          </nav>
        )}
      </article>

      <TableOfContents headings={page.headings} />
    </div>
  );
}
