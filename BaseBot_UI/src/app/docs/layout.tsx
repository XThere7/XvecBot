import type { ReactNode } from "react";
import "./docs.css";
import { DocsShell, type DocsNavGroup } from "@/components/docs/docs-shell";
import { getDocGroups } from "@/lib/docs/content";

export default function DocsLayout({ children }: { children: ReactNode }) {
  const groups: DocsNavGroup[] = getDocGroups().map((group) => ({
    name: group.name,
    pages: group.pages.map((page) => ({
      href: page.href,
      title: page.title,
    })),
  }));

  return (
    <>
      <script
        dangerouslySetInnerHTML={{
          __html: `(function(){try{var t=localStorage.getItem("botbase-docs-theme");if(t==="light"||t==="dark"){document.documentElement.dataset.docsTheme=t;}}catch(e){}})();`,
        }}
      />
      <DocsShell groups={groups}>{children}</DocsShell>
    </>
  );
}
