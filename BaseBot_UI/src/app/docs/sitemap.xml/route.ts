import { getDocs } from "@/lib/docs/content";

export const dynamic = "force-static";

function xmlEscape(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

export function GET() {
  const base = (
    process.env.NEXT_PUBLIC_SITE_URL || "https://app.botbase.tz"
  ).replace(/\/+$/, "");
  const pages = getDocs();
  const urls = pages
    .map(
      (page) => `  <url>
    <loc>${xmlEscape(`${base}${page.href}`)}</loc>
    <lastmod>${page.updatedAt.slice(0, 10)}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>${page.slug.length === 0 ? "1.0" : "0.7"}</priority>
  </url>`,
    )
    .join("\n");

  return new Response(
    `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls}
</urlset>
`,
    {
      headers: {
        "Content-Type": "application/xml; charset=utf-8",
        "Cache-Control": "public, max-age=300, s-maxage=3600",
      },
    },
  );
}
