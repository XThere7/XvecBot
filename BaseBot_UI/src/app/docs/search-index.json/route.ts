import { getSearchDocs } from "@/lib/docs/content";

export const dynamic = "force-static";

export function GET() {
  return Response.json(getSearchDocs(), {
    headers: {
      "Cache-Control": "public, max-age=300, s-maxage=3600",
      "Content-Type": "application/json; charset=utf-8",
    },
  });
}
