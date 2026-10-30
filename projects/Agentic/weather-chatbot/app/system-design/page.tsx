/*
 * app/system-design/page.tsx: System Design: how Nimbus is built today, drawn in the four bands of a common reference
 * design for AI assistants, then compared with it part by part; rendered from docs/system-design.md when Vercel builds
 * the app, with the diagram where the page's Markdown marks it.
 */
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { MarkdownDoc } from "@/components/markdown-doc";
import { SystemDesignDiagram } from "@/components/system-design-diagram";
import { SYSTEM_DESIGN_SLUG } from "@/lib/docs/doc-list";
import { readDocMarkdown } from "@/lib/docs/read-doc";
import { SYSTEM_DIAGRAM } from "@/lib/docs/system-design-diagram";
import { UnexpectedError } from "@/lib/errors";

export const metadata: Metadata = { title: "System Design · Nimbus" };

// Where the diagram goes in the page's Markdown: an HTML comment, which GitHub doesn't show either.
const DIAGRAM_MARKER = "<!-- the diagram -->";

/**
 * Renders the page: the Markdown before the marker, the diagram, then the rest. Without exactly one marker, the build
 * fails.
 */
export default async function SystemDesignPage(): Promise<ReactNode> {
  const parts = (await readDocMarkdown({ slug: SYSTEM_DESIGN_SLUG })).split(DIAGRAM_MARKER);
  if (parts.length !== 2) {
    throw new UnexpectedError(`docs/system-design.md must mark the diagram's place once, with ${DIAGRAM_MARKER}.`);
  }
  const [opening = "", rest = ""] = parts;
  return (
    <main className="doc doc-wide">
      <MarkdownDoc markdown={opening} />
      <SystemDesignDiagram diagram={SYSTEM_DIAGRAM} />
      <MarkdownDoc markdown={rest} />
    </main>
  );
}
