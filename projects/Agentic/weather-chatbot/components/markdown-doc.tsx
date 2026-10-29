/*
 * components/markdown-doc.tsx: shows a Markdown document, with GitHub-style tables; raw HTML in it is never rendered.
 */
import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type MarkdownDocProps = { markdown: string };

/** Renders Markdown as HTML: headings, lists, tables, code; no raw HTML. */
export function MarkdownDoc({ markdown }: MarkdownDocProps): ReactNode {
  return (
    <article className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
    </article>
  );
}
