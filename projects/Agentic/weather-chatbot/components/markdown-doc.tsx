/*
 * components/markdown-doc.tsx: shows a Markdown document, with GitHub-style tables; raw HTML in it is never rendered.
 */
import type { ReactNode } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";

type MarkdownDocProps = { markdown: string };

/**
 * A link to another page is written for GitHub ("step-3.md", "issues.md"); in the app it goes to that page
 * ("/docs/step-3", "/issues").
 */
function toAppUrl(url: string): string {
  const appUrl = url
    .replace(/^(step-\d+)\.md$/, "/docs/$1")
    .replace(/^(issues|system-design|technical-details)\.md$/, "/$1");
  return defaultUrlTransform(appUrl);
}

/** Renders Markdown as HTML: headings, lists, tables, code; no raw HTML. */
export function MarkdownDoc({ markdown }: MarkdownDocProps): ReactNode {
  return (
    <article className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]} urlTransform={toAppUrl}>
        {markdown}
      </ReactMarkdown>
    </article>
  );
}
