import Link from "next/link";

export default function DocsNotFound() {
  return (
    <div className="docs-page-grid">
      <article className="docs-article">
        <nav className="docs-breadcrumbs" aria-label="Breadcrumb">
          <Link href="/docs">Docs</Link>
          <span aria-hidden>/</span>
          <span aria-current="page">Page not found</span>
        </nav>
        <h1>Page not found</h1>
        <p className="docs-description">
          That documentation page does not exist or has moved. Search the docs,
          or start from the overview.
        </p>
        <div className="docs-prose">
          <p>
            <Link href="/docs">Go to the documentation home</Link>
          </p>
        </div>
      </article>
    </div>
  );
}
