/*
 * lib/docs/doc-list.ts: the documentation pages, one per finished build step, in order.
 */
import "server-only";

export type DocEntry = { slug: string; step: number; title: string; summary: string };

// ① One entry per finished step. Each page's text is in docs/<slug>.md (read by lib/docs/read-doc.ts).
export const DOC_PAGES: readonly DocEntry[] = [
  {
    slug: "step-1",
    step: 1,
    title: "The Project Skeleton",
    summary:
      "The Next.js app, this left menu and documentation, the build line, the checks, CI, and how Vercel deploys it.",
  },
];

/** Finds a documentation page by its slug. */
export function findDoc(slug: string): DocEntry | undefined {
  return DOC_PAGES.find((doc) => doc.slug === slug);
}
