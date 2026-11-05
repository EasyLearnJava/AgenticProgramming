import { request } from "./api.js";
import { $, escape, openDialog, safeUrl, toast } from "./ui.js";
import { renderParagraphs } from "./rendering.js";

let currentAnswer = null;

function showCitation(number) {
  const cite = currentAnswer?.citations.find((item) => item.number === number);
  if (!cite) return;
  const url = safeUrl(cite.url);
  openDialog(cite.title, `Citation ${cite.number} · ${cite.location}`,
    `<div class="quote-block">${escape(cite.quote)}</div><p class="dialog-location">Chunk ${escape(cite.chunk_id)}</p>` +
    (url ? `<a class="button secondary" href="${url}" target="_blank" rel="noopener noreferrer">Open original source ↗</a>` : "<p>From a locally uploaded document.</p>"));
}

function renderAnswer(answer) {
  currentAnswer = answer;
  const labels = { answered: "CITED ANSWER", evidence: "SOURCE EVIDENCE", refused: "MORE EVIDENCE NEEDED", clarify: "LET’S GET MORE SPECIFIC" };
  // Only explicit backend metadata creates buttons; source text such as [1] stays literal.
  const paragraphs = renderParagraphs(answer);
  const uniqueSources = [...new Map(answer.citations.map((cite) => [cite.source_id, cite])).values()];
  const sources = uniqueSources.map((cite) => `<button class="source-chip" data-citation="${cite.number}">▤ ${escape(cite.title)} ↗</button>`).join("");
  const trace = answer.trace.map((step) => `<div class="trace-step"><strong>${escape(step.step)}</strong><span>${escape(step.detail)}</span><span>${step.ms} ms</span></div>`).join("");
  const retrieved = answer.retrieved.map((hit, index) => `<div class="retrieval-item"><h4>${index + 1}. ${escape(hit.chunk.title)}</h4><p>${escape(hit.chunk.location)}</p><p>${escape(hit.chunk.text.slice(0, 430))}${hit.chunk.text.length > 430 ? "…" : ""}</p><div class="score-row"><span>Rerank ${hit.score.toFixed(3)}</span><span>BM25 ${hit.keyword_score.toFixed(2)}</span><span>Cosine ${hit.vector_score.toFixed(3)}</span><span>Term coverage ${Math.round(hit.coverage * 100)}%</span></div></div>`).join("");
  $("#answer-container").innerHTML = `<article class="answer-card"><div class="answer-header"><span class="answer-tag ${escape(answer.status)}">${labels[answer.status] || "RESULT"}</span><span class="answer-meta">${(answer.latency_ms / 1000).toFixed(2)}s · ${answer.citations.length} citations</span></div><div class="answer-body">${paragraphs}</div>${answer.note ? `<div class="answer-note">${escape(answer.note)}</div>` : ""}${sources ? `<div class="answer-sources">${sources}</div>` : ""}<details class="details"><summary>Follow the pipeline</summary><div class="trace-steps">${trace}</div></details>${retrieved ? `<details class="details"><summary>Inspect ${answer.retrieved.length} retrieved chunks and ranking scores</summary><p class="small-note">Ranking scores and term coverage are retrieval heuristics, not answer confidence.</p>${retrieved}</details>` : ""}</article>`;
  $("#starter-prompts").classList.add("hidden");
}

export function initAsk(getStatus) {
  const question = $("#question");
  question.addEventListener("input", () => { $("#question-length").textContent = `${question.value.length} / 1500`; });
  question.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (!$("#ask-button").disabled) $("#ask-form").requestSubmit();
    }
  });
  document.querySelectorAll("[data-question]").forEach((button) => button.addEventListener("click", () => {
    question.value = button.dataset.question;
    question.dispatchEvent(new Event("input"));
    $("#ask-form").requestSubmit();
  }));
  $("#answer-container").addEventListener("click", (event) => {
    const button = event.target.closest("[data-citation]");
    if (button) showCitation(Number(button.dataset.citation));
  });
  $("#ask-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if ($("#ask-button").disabled) return;
    if (!question.value.trim()) return;
    if (getStatus()?.needs_rebuild) return toast("Rebuild the index in Knowledge base before asking questions.", true);
    const button = $("#ask-button");
    button.disabled = true;
    button.textContent = "Searching…";
    $("#ask-loading").classList.remove("hidden");
    try {
      const sourceId = $("#source-filter").value;
      const answer = await request("/ask", { method: "POST", body: JSON.stringify({ question: question.value.trim(), source_ids: sourceId ? [sourceId] : [] }) });
      renderAnswer(answer);
    } catch (error) { toast(error.message, true); }
    finally { button.disabled = false; button.innerHTML = "Find evidence <span>↗</span>"; $("#ask-loading").classList.add("hidden"); }
  });
}

