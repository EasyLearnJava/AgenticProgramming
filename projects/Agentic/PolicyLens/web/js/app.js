// This file wires the views together. Each feature owns its own event handlers.
import { request } from "./api.js";
import { $, escape, initDialog, toast } from "./ui.js";
import { initAsk } from "./ask.js";
import { initKnowledge, renderKnowledge } from "./knowledge.js";
import { initEvaluation, loadLatestEvaluation } from "./evaluation.js";

let status = null;
const viewNames = { ask: "Ask a question", knowledge: "Knowledge base", evaluation: "Evaluation lab", pipeline: "How it works" };

async function refreshStatus() {
  status = await request("/status");
  $("#connection-dot").classList.add("online");
  $("#connection-label").textContent = "Local workspace connected";
  $("#mode-pill").textContent = status.mode === "openai" ? "OpenAI · Generated answers" : "Extractive preview · No key";
  $("#mode-note").textContent = status.mode === "openai"
    ? "OpenAI mode uses neural embeddings and generated, cited answers. Questions and retrieved passages are sent to your configured provider."
    : "Extractive preview runs locally with lexical vectors and verbatim passages. Switch to OpenAI mode in .env for semantic retrieval and generated answers.";
  $("#stat-docs").textContent = status.documents.length;
  $("#stat-chunks").textContent = status.chunk_count;
  $("#nav-doc-count").textContent = String(status.documents.length).padStart(2, "0");
  const previous = $("#source-filter").value;
  $("#source-filter").innerHTML = '<option value="">All documents</option>' + status.documents.map((doc) => `<option value="${escape(doc.source_id)}">${escape(doc.title)}</option>`).join("");
  if (status.documents.some((doc) => doc.source_id === previous)) $("#source-filter").value = previous;
  const notice = $("#global-notice");
  if (status.needs_rebuild) {
    notice.innerHTML = 'Your documents or configuration changed. Rebuild the index to use the latest collection. <a href="#knowledge"><u>Open knowledge base →</u></a>';
    notice.classList.remove("hidden");
  } else if (status.stale_sources.length) {
    notice.textContent = `${status.stale_sources.length} source snapshot(s) are older than the ${status.freshness_days}-day freshness target. Refresh the starter corpus and rebuild when current policies matter.`;
    notice.classList.remove("hidden");
  } else { notice.classList.add("hidden"); }
  $("#nav-eval-count").textContent = status.evaluation_count;
  $("#evaluation-subtitle").textContent = `${status.evaluation_count} questions. Real evidence. Honest failure analysis.`;
  renderKnowledge(status);
  renderPipeline(status);
  return status;
}

function renderPipeline(s) {
  const cards = [
    ["01", "Ingest & clean", "Read UTF-8 Markdown/TXT or text-based PDFs. Public pages are bundled with source URLs, snapshot dates and content hashes. Boilerplate is removed during refresh.", "ingestion/loaders.py"],
    ["02", "Split with context", `Preserve Markdown section headings, then split long sections at ${s.chunk_size} cl100k_base tokens with ${s.chunk_overlap} tokens of overlap. PDFs keep page numbers.`, "ingestion/chunking.py"],
    ["03", "Embed & store", s.mode === "openai" ? "Create neural embeddings with the configured OpenAI model. SQLite persists chunks, vectors and metadata in one atomic generation." : "Preview uses deterministic lexical hash vectors. They do not understand synonyms. OpenAI mode swaps in neural embeddings without changing the store.", "retrieval/embeddings.py · store.py"],
    ["04", "Retrieve & rerank", `Combine BM25 and vector cosine search using reciprocal rank fusion, rerank by lexical coverage, and keep the top ${s.top_k} chunks. Inspect each score in the answer.`, "retrieval/hybrid.py"],
    ["05", "Assess the evidence", "A shared topic check clarifies vague requests. Preview uses stems, rarity-weighted coverage and local evidence; OpenAI mode delegates uncertain paraphrases to model checks. Lexical heuristics can still refuse valid wording.", "pipeline.py"],
    ["06", "Answer, cite & evaluate", "Preview quotes the source. OpenAI mode generates structured claims with exact supporting quotations. Citation checks reject invented IDs and quotes; the evaluation report exposes retrieval failures.", "generation.py · evaluation.py"]
  ];
  $("#pipeline-cards").innerHTML = cards.map(([number, title, text, file]) => `<article class="pipeline-card"><span>${number}</span><h3>${title}</h3><p>${escape(text)}</p><code>${file}</code></article>`).join("");
}

function navigate() {
  const view = location.hash.slice(1) in viewNames ? location.hash.slice(1) : "ask";
  document.querySelectorAll(".view").forEach((section) => section.classList.toggle("active", section.id === `view-${view}`));
  document.querySelectorAll("[data-view]").forEach((link) => {
    link.classList.toggle("active", link.dataset.view === view);
    if (link.dataset.view === view) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
  });
  $("#breadcrumb").textContent = viewNames[view];
  if (view === "evaluation") loadLatestEvaluation();
  document.title = `${viewNames[view]} · PolicyLens`;
}

initDialog();
initAsk(() => status);
initKnowledge(refreshStatus);
initEvaluation(() => status);
window.addEventListener("hashchange", navigate);
navigate();
refreshStatus().catch((error) => {
  $("#connection-label").textContent = "Server unavailable";
  $("#mode-pill").textContent = "Connection needed";
  toast(`${error.message} Start the app with Start-PolicyLens.cmd.`, true);
});

