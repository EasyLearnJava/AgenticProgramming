/*
 * app/interview/page.tsx: the Interview Guide: what to tell an interviewer about the project, its production-grade
 * decisions and the incidents worth telling; rendered from docs/interview.md when Vercel builds the app.
 */
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { MarkdownDoc } from "@/components/markdown-doc";
import { INTERVIEW_SLUG } from "@/lib/docs/doc-list";
import { readDocMarkdown } from "@/lib/docs/read-doc";

export const metadata: Metadata = { title: "Interview Guide · Nimbus" };

/** Renders the interview guide. */
export default async function InterviewPage(): Promise<ReactNode> {
  return (
    <main className="doc">
      <MarkdownDoc markdown={await readDocMarkdown({ slug: INTERVIEW_SLUG })} />
    </main>
  );
}
