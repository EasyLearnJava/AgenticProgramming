/*
 * lib/docs/system-design-diagram.ts: the System design page's diagram, as data: how Nimbus is built today, in the four
 * bands of a common reference design for AI assistants (the request path, controlled execution, state, operations).
 * A box's badge is the reference's number for the part it plays; "+" marks a part only Nimbus has.
 */
import "server-only";
import type { ArrowKind, DiagramArrow, DiagramBand, DiagramBox, DiagramLabel, SystemDiagram } from "@/lib/types";

// ① The drawing's size, in its own units: the page scales it to fit.
const DIAGRAM_WIDTH = 1400;
const DIAGRAM_HEIGHT = 1200;

// ② The four bands, as the reference has them.
const DIAGRAM_BANDS: readonly DiagramBand[] = [
  { letter: "A", title: "Online request path", y: 10, height: 300 },
  { letter: "B", title: "Controlled execution", y: 320, height: 470 },
  { letter: "C", title: "State and data freshness", y: 800, height: 185 },
  { letter: "D", title: "09 · Production operations", y: 995, height: 155 },
];

// ③ The parts, band by band, left to right.
const DIAGRAM_BOXES: readonly DiagramBox[] = [
  // A: a question's way in, and its answer's way out.
  {
    band: "A",
    x: 30,
    y: 70,
    width: 190,
    height: 150,
    title: "You",
    lines: ["the chat page, on a", "computer or a phone", "(Next.js · useChat)", "you pick the lane"],
  },
  {
    band: "A",
    x: 260,
    y: 70,
    width: 210,
    height: 150,
    title: "Vercel's edge",
    badge: "02",
    lines: ["HTTPS · routing", "its x-vercel-id is", "our request id", "no sign-in: it's public"],
  },
  {
    band: "A",
    x: 510,
    y: 70,
    width: 250,
    height: 150,
    title: "Input rules",
    badge: "01",
    lines: [
      "≤ 20 messages · ≤ 2,000 chars",
      "the history ≤ 200,000 chars",
      "a live lane · a language tag",
      "only the parts the page sends",
    ],
  },
  {
    band: "A",
    x: 800,
    y: 70,
    width: 320,
    height: 150,
    title: "The chat turn",
    badge: "04",
    lines: [
      "POST /api/chat → runChat (AI SDK)",
      "the model picks the tools",
      "≤ 5 steps · 50 s for an answer",
      "10 s first chunk · 8 s a tool · Stop",
    ],
  },
  {
    band: "A",
    x: 1160,
    y: 70,
    width: 210,
    height: 150,
    title: "Your answer",
    lines: ["streamed as it's written", "a chip per tool call", "a weather card", "errors: our own sentence"],
  },
  {
    band: "A",
    x: 30,
    y: 236,
    width: 330,
    height: 64,
    title: "Nearby city",
    lines: ["a city near you, for one question"],
  },
  {
    band: "A",
    x: 390,
    y: 236,
    width: 370,
    height: 64,
    title: "Pages",
    lines: ["/docs · /issues · /system-design: static"],
  },
  // B: the tools behind each lane, and the model.
  {
    band: "B",
    x: 30,
    y: 395,
    width: 270,
    height: 130,
    title: "REST · no auth",
    lines: ["the tools run in /api/chat", "and call Open-Meteo", "no credentials"],
  },
  {
    band: "B",
    x: 340,
    y: 395,
    width: 300,
    height: 130,
    title: "MCP · no auth",
    lines: ["an MCP client (@ai-sdk/mcp)", "connects within 6 s", "sends x-request-id"],
  },
  {
    band: "B",
    x: 680,
    y: 395,
    width: 300,
    height: 130,
    title: "Our MCP server",
    badge: "+",
    lines: ["/api/mcp · mcp-handler", "public · one message ≤ 8 KB", "logs each call (mcp.call)"],
  },
  {
    band: "B",
    x: 1020,
    y: 395,
    width: 350,
    height: 130,
    title: "The model",
    badge: "07",
    lines: [
      "Gemini 3.5 Flash-Lite",
      "via @ai-sdk/google · key from env",
      "AI SDK retries twice · 2,000 tokens out",
      "one model, no fallback yet",
    ],
  },
  {
    band: "B",
    x: 30,
    y: 565,
    width: 610,
    height: 80,
    title: "Four weather tools",
    badge: "06",
    lines: [
      "geocode_location · get_current_weather · get_forecast · get_air_quality",
      "typed with Zod · read-only · written once, run by both doors",
    ],
  },
  {
    band: "B",
    x: 680,
    y: 565,
    width: 300,
    height: 80,
    title: "Open-Meteo client",
    lines: ["3 s a try · one retry", "Retry-After · timezone=auto"],
  },
  {
    band: "B",
    x: 1020,
    y: 565,
    width: 350,
    height: 80,
    title: "Open-Meteo APIs",
    lines: ["geocoding · forecast · air quality", "no key · sees places, not who asked"],
  },
  {
    band: "B",
    x: 30,
    y: 675,
    width: 270,
    height: 100,
    title: "The auth lanes",
    lines: ["REST and MCP, with a token", "the forecast: Apify's Actor tool", "fall back to their no-auth twin"],
  },
  {
    band: "B",
    x: 340,
    y: 675,
    width: 300,
    height: 100,
    title: "Apify clients",
    lines: ["REST: one POST · 18 s · $0.01", "MCP: mcp.apify.com · run, then items", "Bearer APIFY_TOKEN · no retry"],
  },
  {
    band: "B",
    x: 1020,
    y: 675,
    width: 350,
    height: 100,
    title: "Apify Actor",
    lines: [
      "gochujang/open-meteo-weather-forecast",
      "an item a day, or an hour · °C",
      "$0.005 a run · calls Open-Meteo",
    ],
  },
  // C: what the app keeps, and where.
  {
    band: "C",
    x: 30,
    y: 855,
    width: 300,
    height: 110,
    title: "The conversation",
    lines: ["kept in your browser tab", "each question sends the", "recent messages; no store"],
  },
  {
    band: "C",
    x: 370,
    y: 855,
    width: 270,
    height: 110,
    title: "Settings and secrets",
    lines: ["Vercel's environment", "variables; the keys are", "Secrets · lib/config.ts"],
  },
  {
    band: "C",
    x: 680,
    y: 855,
    width: 420,
    height: 110,
    title: "Runtime Cache (Vercel)",
    lines: [
      "Open-Meteo's answers, by their exact URL",
      "30 days geocoding · 10 min weather now",
      "30 min forecast and air quality",
    ],
  },
  {
    band: "C",
    x: 1130,
    y: 855,
    width: 240,
    height: 110,
    title: "Docs as Markdown",
    lines: ["docs/*.md in the repo", "built into the pages", "at each deployment"],
  },
  // D: how it's watched, tested and shipped.
  {
    band: "D",
    x: 30,
    y: 1055,
    width: 320,
    height: 80,
    title: "Observability",
    lines: ["pino lines → Vercel, Axiom", "errors → Sentry · one request id"],
  },
  {
    band: "D",
    x: 370,
    y: 1055,
    width: 320,
    height: 80,
    title: "Evaluation",
    lines: ["golden questions, live, per lane", "unit, browser and a11y tests"],
  },
  {
    band: "D",
    x: 710,
    y: 1055,
    width: 320,
    height: 80,
    title: "Reliability and scale",
    lines: ["Vercel Functions scale on demand", "budgets · retries · MCP guard"],
  },
  {
    band: "D",
    x: 1050,
    y: 1055,
    width: 320,
    height: 80,
    title: "Release and recovery",
    lines: ["each push: CI, and a deploy", "side by side · roll back in Vercel"],
  },
];

// ④ The lines between the parts.
const DIAGRAM_ARROWS: readonly DiagramArrow[] = [
  // A: you → the edge → the rules → the chat turn → your answer; the edge also serves the nearby city and the pages.
  { path: "M 220 145 H 256", kind: "request", hasHead: true },
  { path: "M 470 145 H 506", kind: "request", hasHead: true },
  { path: "M 760 145 H 796", kind: "request", hasHead: true },
  { path: "M 1120 145 H 1156", kind: "request", hasHead: true },
  { path: "M 300 220 V 232", kind: "request", hasHead: true },
  { path: "M 430 220 V 232", kind: "request", hasHead: true },
  // B: the chat turn's calls: to the tools, through the lane you picked, and to the model.
  { path: "M 960 220 V 380 M 165 380 H 1195", kind: "request", hasHead: false },
  { path: "M 165 380 V 391", kind: "request", hasHead: true },
  { path: "M 490 380 V 391", kind: "request", hasHead: true },
  { path: "M 1195 380 V 391", kind: "request", hasHead: true },
  { path: "M 165 525 V 561", kind: "request", hasHead: true },
  { path: "M 640 460 H 676", kind: "mcp", hasHead: true },
  { path: "M 830 525 V 545 H 560 V 561", kind: "mcp", hasHead: true },
  { path: "M 640 605 H 676", kind: "request", hasHead: true },
  { path: "M 980 605 H 1016", kind: "request", hasHead: true },
  // B: REST · with auth, reached around the left edge: geocoding through the tools, the forecast through Apify.
  { path: "M 165 380 H 18 V 725 H 26", kind: "request", hasHead: true },
  { path: "M 165 675 V 649", kind: "request", hasHead: true },
  { path: "M 300 725 H 336", kind: "request", hasHead: true },
  { path: "M 640 725 H 1016", kind: "request", hasHead: true },
  { path: "M 1195 675 V 649", kind: "request", hasHead: true },
  // C: the Open-Meteo client reads and fills the cache.
  { path: "M 830 645 V 851", kind: "state", hasHead: true },
];

// ⑤ What the lines carry, where it helps to say.
const DIAGRAM_LABELS: readonly DiagramLabel[] = [
  { x: 560, y: 371, text: "tool calls · model calls" },
  { x: 848, y: 690, text: "read, then fill" },
  { x: 660, y: 716, text: "Bearer token" },
];

// ⑥ The legend: each kind of line, and what the badges mean.
const LEGEND_ITEMS: readonly { kind: ArrowKind; text: string }[] = [
  { kind: "request", text: "Request and response" },
  { kind: "mcp", text: "Our MCP hop (x-request-id)" },
  { kind: "state", text: "Cache" },
];

/** The diagram, with its title, and its description for screen readers. */
export const SYSTEM_DIAGRAM: SystemDiagram = {
  width: DIAGRAM_WIDTH,
  height: DIAGRAM_HEIGHT,
  title: "How Nimbus is built today, steps 1 to 7",
  description:
    "Four bands. A: you ask in the chat page; Vercel's edge routes the request; the input rules check it; the chat " +
    "turn runs the model and streams your answer. B: the chat turn calls the tools through the lane you picked, REST " +
    "or MCP (through our own MCP server), and Gemini; the tools call Open-Meteo. On the auth lanes, the forecast " +
    "comes from Apify's Actor instead, with a token, through Apify's REST API or its MCP server, and falls back to " +
    "the no-auth lane behind the same door. C: the conversation stays in " +
    "your browser; settings are Vercel's environment variables; Open-Meteo's answers are cached; the docs are " +
    "Markdown. D: logs with one request id, golden questions and tests, Vercel Functions, and deploys from each push.",
  bands: DIAGRAM_BANDS,
  boxes: DIAGRAM_BOXES,
  arrows: DIAGRAM_ARROWS,
  labels: DIAGRAM_LABELS,
  legend: { y: 1175, items: LEGEND_ITEMS, note: "01–09: the reference's parts · +: only in Nimbus" },
};
