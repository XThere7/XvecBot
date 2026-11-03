import fs from "node:fs";
import path from "node:path";
import matter from "gray-matter";

export type DocHeading = {
  id: string;
  text: string;
  level: 2 | 3;
};

export type DocPage = {
  slug: string[];
  href: string;
  title: string;
  description: string;
  group: string;
  order: number;
  body: string;
  headings: DocHeading[];
  updatedAt: string;
};

export type DocGroup = {
  name: string;
  pages: DocPage[];
};

export type SearchDoc = {
  title: string;
  description: string;
  href: string;
  group: string;
  headings: string[];
  text: string;
};

export const DOCS_LOCALE = "en";
const DOCS_ROOT = path.join(process.cwd(), "src", "content", "docs");

function walkMarkdownFiles(directory: string): string[] {
  if (!fs.existsSync(directory)) return [];
  const files: string[] = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...walkMarkdownFiles(fullPath));
    } else if (entry.isFile() && /\.mdx?$/.test(entry.name)) {
      files.push(fullPath);
    }
  }
  return files.sort();
}

function slugify(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim()
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function stripInlineMarkdown(value: string): string {
  return value
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/[`*_~]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function extractHeadings(body: string): DocHeading[] {
  const headings: DocHeading[] = [];
  let fence: string | null = null;

  for (const line of body.split("\n")) {
    const fenceMatch = line.match(/^\s*(```+|~~~+)/);
    if (fenceMatch) {
      if (!fence) fence = fenceMatch[1][0];
      else if (line.trim().startsWith(fence)) fence = null;
      continue;
    }
    if (fence) continue;

    const match = line.match(/^(##|###)\s+(.+?)\s*#*\s*$/);
    if (!match) continue;
    const text = stripInlineMarkdown(match[2]);
    const id = slugify(text);
    if (id) headings.push({ id, text, level: match[1].length as 2 | 3 });
  }

  return headings;
}

function toPlainText(body: string): string {
  return body
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<CodeTabs[\s\S]*?\/>/g, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/~~~[\s\S]*?~~~/g, " ")
    .replace(/^\s*\|?[-: |]+\|[-: |]*$/gm, " ")
    .replace(/[#>*_`~]/g, " ")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function fileToPage(filePath: string): DocPage {
  const raw = fs.readFileSync(filePath, "utf8");
  const parsed = matter(raw);
  const data = parsed.data as Record<string, unknown>;
  const missing = ["title", "description", "group", "order"].filter(
    (key) => data[key] === undefined || data[key] === null || data[key] === "",
  );
  if (missing.length) {
    throw new Error(
      `Docs frontmatter is missing ${missing.join(", ")} in ${path.relative(
        DOCS_ROOT,
        filePath,
      )}`,
    );
  }
  if (typeof data.order !== "number" || !Number.isFinite(data.order)) {
    throw new Error(`Docs frontmatter "order" must be a number in ${filePath}`);
  }

  const relative = path
    .relative(path.join(DOCS_ROOT, DOCS_LOCALE), filePath)
    .replace(/\\/g, "/")
    .replace(/\.mdx?$/, "");
  const parts = relative.split("/").filter(Boolean);
  if (parts[parts.length - 1] === "index") parts.pop();
  const slug = parts;
  const body = parsed.content.trim();
  const stat = fs.statSync(filePath);

  return {
    slug,
    href: ["/docs", ...slug].join("/"),
    title: String(data.title).trim(),
    description: String(data.description).trim(),
    group: String(data.group).trim(),
    order: data.order,
    body,
    headings: extractHeadings(body),
    updatedAt: stat.mtime.toISOString(),
  };
}

export function getDocs(locale = DOCS_LOCALE): DocPage[] {
  const root = path.join(DOCS_ROOT, locale);
  return walkMarkdownFiles(root)
    .map(fileToPage)
    .sort((a, b) => a.order - b.order || a.title.localeCompare(b.title));
}

export function getDocBySlug(
  slug: string[],
  locale = DOCS_LOCALE,
): DocPage | undefined {
  const target = slug.join("/");
  return getDocs(locale).find((page) => page.slug.join("/") === target);
}

export function getDocGroups(locale = DOCS_LOCALE): DocGroup[] {
  const pages = getDocs(locale);
  const groups = new Map<string, DocPage[]>();
  for (const page of pages) {
    const existing = groups.get(page.group) ?? [];
    existing.push(page);
    groups.set(page.group, existing);
  }
  return [...groups.entries()].map(([name, groupPages]) => ({
    name,
    pages: groupPages,
  }));
}

export function getSearchDocs(locale = DOCS_LOCALE): SearchDoc[] {
  return getDocs(locale).map((page) => ({
    title: page.title,
    description: page.description,
    href: page.href,
    group: page.group,
    headings: page.headings.map((heading) => heading.text),
    text: toPlainText(page.body).slice(0, 20_000),
  }));
}

export function getDocNeighbours(
  slug: string[],
  locale = DOCS_LOCALE,
): { previous?: DocPage; next?: DocPage } {
  const pages = getDocs(locale);
  const target = slug.join("/");
  const index = pages.findIndex((page) => page.slug.join("/") === target);
  if (index === -1) return {};
  return {
    previous: index > 0 ? pages[index - 1] : undefined,
    next: index + 1 < pages.length ? pages[index + 1] : undefined,
  };
}

export { slugify };
