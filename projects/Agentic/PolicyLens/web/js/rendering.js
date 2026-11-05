// Pure rendering helpers are easy to test without a browser or a build system.
import { escape } from "./ui.js";

export const duration = (value) => value == null || !Number.isFinite(value) ? "—" : `${(value / 1000).toFixed(2)}s`;

export function renderParagraphs(answer) {
  const parts = answer.parts?.length ? answer.parts : answer.text.split(/\n\n+/).map((text) => ({ text, citations: [] }));
  const known = new Set(answer.citations.map((citation) => citation.number));
  return parts.map((part) => {
    const buttons = (part.citations || []).filter((n) => Number.isInteger(n) && known.has(n)).map((n) =>
      `<button class="citation-marker" data-citation="${n}" aria-label="Open citation ${n}">${n}</button>`).join("");
    return `<p>${escape(part.text)}${buttons ? " " + buttons : ""}</p>`;
  }).join("");
}

export function isRowKey(event) {
  return ["Enter", " "].includes(event.key) && event.target.matches?.("[data-case]");
}
