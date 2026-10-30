/*
 * app/todo/page.tsx: To Do: what's still open, and why, BotID first; rendered from docs/todo.md when Vercel builds the
 * app.
 */
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { MarkdownDoc } from "@/components/markdown-doc";
import { TODO_SLUG } from "@/lib/docs/doc-list";
import { readDocMarkdown } from "@/lib/docs/read-doc";

export const metadata: Metadata = { title: "To Do · Nimbus" };

/** Renders the to-do list. */
export default async function TodoPage(): Promise<ReactNode> {
  return (
    <main className="doc">
      <MarkdownDoc markdown={await readDocMarkdown({ slug: TODO_SLUG })} />
    </main>
  );
}
