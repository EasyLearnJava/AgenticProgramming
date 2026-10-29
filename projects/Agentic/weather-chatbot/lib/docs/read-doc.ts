/*
 * lib/docs/read-doc.ts: reads a documentation page's Markdown from docs/, while Vercel builds the pages.
 */
import "server-only";
import { readFile } from "node:fs/promises";
import path from "node:path";
import type { DocEntry } from "@/lib/docs/doc-list";

const DOCS_FOLDER = path.join(process.cwd(), "docs");

/** Reads a documentation page's Markdown; it runs at build time, so every page is static. */
export async function readDocMarkdown(doc: DocEntry): Promise<string> {
  return readFile(path.join(DOCS_FOLDER, `${doc.slug}.md`), "utf8");
}
