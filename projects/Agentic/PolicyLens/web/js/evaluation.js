import { request } from "./api.js";
import { $, date, escape, metric, percent, toast } from "./ui.js";
import { duration, isRowKey } from "./rendering.js";

function renderReport(report) {
  if (!report) return;
  const s = report.summary;
  const suiteNames = {assignment:"Assignment",review1:"First review",challenge:"Challenge"};
  const suiteSummary = Object.entries(report.suites || {}).map(([name, values]) => `${suiteNames[name] || escape(name)}: ${values.questions} questions · routing ${percent(values.behavior_pass_rate)} · complete checks ${percent(values.case_pass_rate)}`).join("<br>");
  const rows = report.cases.map((row, index) => `<tr class="case-row" data-case="${index}" tabindex="0" aria-label="Expand ${escape(row.id)}"><td>${escape(row.id)}</td><td>${escape(row.question)}<small>${escape(row.category)}</small></td><td><span class="badge ${row.case_pass ? "" : "pending"}">${row.case_pass ? "PASS" : "REVIEW"}</span><small>${escape(row.status)}</small></td><td>${percent(row.source_recall_at_k)}</td><td>${percent(row.chunk_precision_at_k)}</td><td>${duration(row.latency_ms)}</td></tr><tr class="case-detail hidden" id="case-${index}"><td colspan="6"><p><strong>Analysis</strong> · ${escape(row.analysis)}</p><p class="small-note">Routing: ${row.behavior_pass ? "PASS" : "FAIL"} · Retrieved reference recall: ${percent(row.reference_evidence_recall)} · Displayed reference recall: ${percent(row.answer_evidence_recall)} · Reciprocal rank: ${row.reciprocal_rank == null ? "—" : row.reciprocal_rank.toFixed(2)}</p><p style="margin-top:12px">${escape(row.answer.text)}</p><p class="small-note">Review each factual claim against its evidence. Human faithfulness and relevance scores are not yet recorded.</p></td></tr>`).join("");
  $("#evaluation-results").innerHTML = `<p class="report-meta">${date(report.created_at)} · ${escape(report.mode)} mode · ${s.questions} questions · top-${report.top_k} retrieval · ${s.errors} execution errors · pinned pipeline timings</p><div class="metric-grid">${metric("SOURCE RECALL@K", percent(s.source_recall_at_k), "Expected source documents found")}${metric("CHUNK PRECISION@K", percent(s.chunk_precision_at_k), "Chunks from expected source docs")}${metric("COMPLETE REFERENCE CHECKS", percent(s.case_pass_rate), "Routing + retrieved + displayed evidence")}${metric("PIPELINE P95", duration(s.p95_latency_ms), "Excludes HTTP and session setup")}</div><div class="review-notice"><strong>Faithfulness is not measured yet.</strong> Displayed citations passed ${percent(s.citation_validity)} of source-integrity checks. This is a validator invariant, not an answer-quality score. Human review is required for the 95% faithfulness and 90% relevance targets. Routing only: ${percent(s.behavior_pass_rate)} · Displayed reference recall: ${percent(s.answer_evidence_recall)} · Chunk precision: ${percent(s.chunk_precision_at_k)} · MRR: ${s.mrr == null ? "—" : s.mrr.toFixed(2)} · Reference evidence recall: ${percent(s.reference_evidence_recall)}.</div>${suiteSummary ? `<p class="report-meta">${suiteSummary}</p>` : ""}<div class="download-actions"><a class="button secondary" href="/api/reports/${escape(report.id)}.md" download>↓ Download report</a><a class="button secondary" href="/api/reports/${escape(report.id)}.json" download>↓ Raw results (JSON)</a></div><div class="table-wrap"><table class="evaluation-table"><thead><tr><th>ID</th><th>QUESTION · CLICK TO INSPECT</th><th>REFERENCE CHECKS</th><th>RECALL</th><th>PRECISION</th><th>LATENCY</th></tr></thead><tbody>${rows}</tbody></table></div><p class="small-note">Retrieval metrics are averaged over answerable cases. Refusal and clarification cases are included in behavior scores. Expand a row for failure analysis. This is a small development set.</p>`;
}

export async function loadLatestEvaluation() {
  try { renderReport(await request("/evaluations/latest")); }
  catch (error) { toast(error.message, true); }
}

export function initEvaluation(getStatus) {
  const result = $("#evaluation-results");
  function toggle(event) {
    const row = event.target.closest("[data-case]");
    if (row) $(`#case-${row.dataset.case}`).classList.toggle("hidden");
  }
  result.addEventListener("click", toggle);
  result.addEventListener("keydown", (event) => { if (isRowKey(event)) { event.preventDefault(); toggle(event); } });
  $("#evaluate-button").addEventListener("click", async () => {
    if (getStatus()?.needs_rebuild) return toast("Rebuild the index before running the test set.", true);
    const button = $("#evaluate-button");
    button.disabled = true;
    button.textContent = "Evaluation running…";
    $("#evaluation-progress").classList.remove("hidden");
    try {
      const job = await request("/evaluations", { method: "POST" });
      // A background server job survives navigation between workspace views.
      for (;;) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        const state = await request(`/evaluations/${job.id}`);
        $("#progress-label").textContent = `Evaluating ${state.completed} of ${state.total} questions…`;
        if (state.status === "failed") throw new Error(state.error);
        if (state.status === "completed") { renderReport(state.report); toast("Evaluation complete. Inspect the results and failure analysis."); break; }
      }
    } catch (error) { toast(error.message, true); }
    finally { button.disabled = false; button.textContent = "▶ Run evaluation"; $("#evaluation-progress").classList.add("hidden"); }
  });
}

