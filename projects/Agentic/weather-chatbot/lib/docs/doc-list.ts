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
  {
    slug: "step-2",
    step: 2,
    title: "The Chat Page, From a Sample",
    summary:
      "The chat page from a sample conversation: tool chips with their wire views, the 2×2 lane picker, the weather " +
      "card, the compare view, and end-to-end tests in a real browser.",
  },
  {
    slug: "step-3",
    step: 3,
    title: "The Live Chat, Through REST · No Auth",
    summary:
      "Gemini answers with our four weather tools, which call Open-Meteo directly: the chat route, the tools, the " +
      "ambiguity rule, time limits, retries and the cache, Stop, the location pin, and the golden questions.",
  },
  {
    slug: "step-4",
    step: 4,
    title: "MCP · No Auth, Through Our Own MCP Server",
    summary:
      "The same four tools on our own MCP server at /api/mcp; the chat reaches them as an MCP client: the handshake, " +
      "what each MCP answer carries, the bypass secret, and using the server from any MCP client.",
  },
  {
    slug: "step-5",
    step: 5,
    title: "Errors and Logs",
    summary:
      "One error map for every failure (its sentence, its log level, its retry rule), a request id that both " +
      "functions log under, the ref at the end of an error's sentence, and the lines a question writes.",
  },
];

// ② The issues log, docs/issues.md: the problems met in each step, and their fixes; and the system design,
// docs/system-design.md: how the app is built, against a reference design. Each has its own menu link.
export const ISSUES_SLUG = "issues";
export const SYSTEM_DESIGN_SLUG = "system-design";

/** Finds a documentation page by its slug. */
export function findDoc(slug: string): DocEntry | undefined {
  return DOC_PAGES.find((doc) => doc.slug === slug);
}
