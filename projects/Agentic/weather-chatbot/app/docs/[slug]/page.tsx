/*
 * app/docs/[slug]/page.tsx: one documentation page, rendered from its Markdown file when Vercel builds the app.
 */
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { MarkdownDoc } from "@/components/markdown-doc";
import { DOC_PAGES, findDoc } from "@/lib/docs/doc-list";
import { readDocMarkdown } from "@/lib/docs/read-doc";

type DocPageProps = { params: Promise<{ slug: string }> };

// ① Only the listed pages exist; any other address under /docs is a 404.
export const dynamicParams = false;

/** The pages Next.js builds, one per listed step. */
export function generateStaticParams(): { slug: string }[] {
  return DOC_PAGES.map((doc) => ({ slug: doc.slug }));
}

/** The browser tab's title, from the list. */
export async function generateMetadata({ params }: DocPageProps): Promise<Metadata> {
  const doc = findDoc((await params).slug);
  return { title: doc ? `Step ${doc.step}: ${doc.title} · Nimbus` : "Documentation · Nimbus" };
}

/** Renders one documentation page. */
export default async function DocPage({ params }: DocPageProps): Promise<ReactNode> {
  // ② Find the page, or answer 404.
  const doc = findDoc((await params).slug);
  if (!doc) notFound();
  // ③ Read its Markdown, and render it.
  return (
    <main className="doc">
      <MarkdownDoc markdown={await readDocMarkdown(doc)} />
    </main>
  );
}
