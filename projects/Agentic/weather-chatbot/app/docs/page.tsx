/*
 * app/docs/page.tsx: the documentation's first page: how it's organised, and one link per finished build step.
 */
import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { DOC_PAGES } from "@/lib/docs/doc-list";

export const metadata: Metadata = { title: "Documentation · Nimbus" };

/** Lists the documentation pages, one per finished build step. */
export default function DocsIndexPage(): ReactNode {
  return (
    <main className="doc">
      <h1>Documentation</h1>
      <p>
        One page per build step, written when the step is done: what was built, how it works, and how to check it
        yourself. Read them in order; each step builds on the one before.
      </p>
      <ol className="doc-list">
        {DOC_PAGES.map((doc) => (
          <li key={doc.slug}>
            <Link href={`/docs/${doc.slug}`}>
              Step {doc.step}: {doc.title}
            </Link>
            <p>{doc.summary}</p>
          </li>
        ))}
      </ol>
    </main>
  );
}
