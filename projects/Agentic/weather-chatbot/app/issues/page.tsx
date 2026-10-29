/*
 * app/issues/page.tsx: Issues and Fixes: every problem met while building and deploying the app, why it happened, and
 * how it was fixed, step by step; rendered from docs/issues.md when Vercel builds the app.
 */
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { MarkdownDoc } from "@/components/markdown-doc";
import { ISSUES_SLUG } from "@/lib/docs/doc-list";
import { readDocMarkdown } from "@/lib/docs/read-doc";

export const metadata: Metadata = { title: "Issues and Fixes · Nimbus" };

/** Renders the issues log. */
export default async function IssuesPage(): Promise<ReactNode> {
  return (
    <main className="doc">
      <MarkdownDoc markdown={await readDocMarkdown({ slug: ISSUES_SLUG })} />
    </main>
  );
}
