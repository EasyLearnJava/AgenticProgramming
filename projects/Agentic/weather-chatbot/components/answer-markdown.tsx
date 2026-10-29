/*
 * components/answer-markdown.tsx: the bot's answer, as Markdown: paragraphs, lists, bold. No raw HTML, and no images,
 * which the browser would fetch at once from wherever the model pointed; links open in a new tab, so the chat stays.
 */
import type { ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

type AnswerMarkdownProps = { text: string };

const DISALLOWED_ELEMENTS = ["img"];

const COMPONENTS: Components = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
};

/** An answer's Markdown, rendered safely. */
export function AnswerMarkdown({ text }: AnswerMarkdownProps): ReactNode {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} disallowedElements={DISALLOWED_ELEMENTS} components={COMPONENTS}>
      {text}
    </ReactMarkdown>
  );
}
