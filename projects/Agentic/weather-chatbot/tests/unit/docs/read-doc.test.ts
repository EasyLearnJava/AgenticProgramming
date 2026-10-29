/*
 * tests/unit/docs/read-doc.test.ts: every listed documentation page has its Markdown file, headed by its own title.
 */
import { describe, expect, it } from "vitest";
import { DOC_PAGES, ISSUES_SLUG } from "@/lib/docs/doc-list";
import { readDocMarkdown } from "@/lib/docs/read-doc";

describe("readDocMarkdown", () => {
  it("reads each page's file, which starts with that step's number and title", async () => {
    for (const doc of DOC_PAGES) {
      const markdown = await readDocMarkdown(doc);
      expect(markdown.startsWith(`# Step ${doc.step} · ${doc.title}\n`)).toBe(true);
    }
  });

  it("reads the issues log, which has a section for each finished step", async () => {
    const markdown = await readDocMarkdown({ slug: ISSUES_SLUG });
    expect(markdown.startsWith("# Issues and Fixes\n")).toBe(true);
    for (const doc of DOC_PAGES) {
      expect(markdown).toContain(`\n## Step ${doc.step} · `);
    }
  });
});
