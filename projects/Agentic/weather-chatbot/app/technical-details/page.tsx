/*
 * app/technical-details/page.tsx: Technical Details: one real question, followed through each file and function from
 * the input box to the answer, how it's kept safe, and what Axiom and Sentry get; rendered from
 * docs/technical-details.md when Vercel builds the app.
 */
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { MarkdownDoc } from "@/components/markdown-doc";
import { TECHNICAL_DETAILS_SLUG } from "@/lib/docs/doc-list";
import { readDocMarkdown } from "@/lib/docs/read-doc";

export const metadata: Metadata = { title: "Technical Details · Nimbus" };

/** Renders the technical details. */
export default async function TechnicalDetailsPage(): Promise<ReactNode> {
  return (
    <main className="doc">
      <MarkdownDoc markdown={await readDocMarkdown({ slug: TECHNICAL_DETAILS_SLUG })} />
    </main>
  );
}
