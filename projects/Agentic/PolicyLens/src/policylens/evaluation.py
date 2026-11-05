"""Assignment and review evaluations; proxy metrics are never called faithfulness.

Ground-truth source IDs and evidence fragments live in evaluation/questions.json.
Human semantic review is intentionally separate from mechanical citation checks.
"""

import json
import logging
import hashlib
from time import perf_counter
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from policylens.text import normalize
from policylens.diagnostics import log_exception
from policylens.grounding import body_text
from policylens import __version__

logger = logging.getLogger("policylens.evaluation")


def load_questions(root: Path) -> list[dict]:
    """Keep the 15 assignment questions and load separate review regressions too."""
    questions = []
    for name, suite in (("questions.json", "assignment"), ("regression_questions.json", "review1"),
                        ("challenge_questions.json", "challenge")):
        path = root / "evaluation" / name
        if path.is_file():
            questions.extend({**case, "suite": suite} for case in json.loads(path.read_text(encoding="utf-8")))
    return questions


def score_case(case: dict, answer) -> dict:
    relevant = set(case["expected_sources"])
    retrieved = answer.retrieved
    found = {hit.chunk.source_id for hit in retrieved}
    recall = len(relevant & found) / len(relevant) if relevant else None
    # Precision counts relevant chunks; recall and MRR use relevant source docs.
    precision = sum(hit.chunk.source_id in relevant for hit in retrieved) / len(retrieved) if relevant and retrieved else (0 if relevant else None)
    reciprocal_rank = next((1 / i for i, hit in enumerate(retrieved, 1)
                            if hit.chunk.source_id in relevant), 0) if relevant else None
    evidence = normalize(" ".join(hit.chunk.text for hit in retrieved))
    fragments = case.get("evidence_fragments", [])
    evidence_recall = sum(normalize(part) in evidence for part in fragments) / len(fragments) if fragments else None
    expected = case["expected_behavior"]
    behavior_pass = (answer.status in {"answered", "evidence"} and bool(answer.citations)
                     and (not relevant or any(c.source_id in relevant for c in answer.citations))
                     if expected == "answer" else answer.status == expected and not answer.citations)
    passages = {hit.chunk.id: normalize(body_text(hit.chunk.text)) for hit in retrieved}
    valid = sum(c.chunk_id in passages and normalize(c.quote) in passages[c.chunk_id] for c in answer.citations)
    citation_validity = valid / len(answer.citations) if answer.citations else None
    displayed = normalize(" ".join(c.quote for c in answer.citations))
    answer_evidence_recall = sum(normalize(part) in displayed for part in fragments) / len(fragments) if fragments else None
    case_pass = behavior_pass and all(value is None or value == 1 for value in
                                      (recall, evidence_recall, answer_evidence_recall, citation_validity))
    failures = []
    if not behavior_pass:
        failures.append(f"Expected {expected}; observed {answer.status}.")
    if recall is not None and recall < 1:
        failures.append("Some expected source documents were missing from top-k; inspect query wording and chunk boundaries.")
    if evidence_recall is not None and evidence_recall < 1:
        failures.append("Some reference evidence was absent from top-k even if the correct source appeared.")
    if citation_validity is not None and citation_validity < 1:
        failures.append("At least one quoted citation did not match the retrieved chunk.")
    if answer_evidence_recall is not None and answer_evidence_recall < 1:
        failures.append("The displayed quotations omit some reference evidence; a status label alone is not a complete answer.")
    return {**case, "status": answer.status, "behavior_pass": behavior_pass, "case_pass": case_pass,
            "source_recall_at_k": recall, "chunk_precision_at_k": precision,
            "reciprocal_rank": reciprocal_rank, "reference_evidence_recall": evidence_recall,
            "citation_validity": citation_validity, "latency_ms": answer.latency_ms,
            "answer_evidence_recall": answer_evidence_recall,
            "analysis": " ".join(failures) or "Expected behavior and reference retrieval checks passed; semantic answer review is still required.",
            "answer": answer.model_dump(),
            "human_review": {"faithful_claims": None, "total_claims": None, "relevance_1_to_5": None, "notes": ""}}


def mean(rows: list[dict], key: str):
    values = [row[key] for row in rows if row.get(key) is not None]
    return round(sum(values) / len(values), 4) if values else None


def render_markdown(report: dict) -> str:
    summary = report["summary"]
    lines = ["# PolicyLens evaluation report", "", f"Run: {report['id']} · {report['created_at']}",
             f"Mode: **{report['mode']}** · Index: `{report['index_identity']}`",
             f"Corpus fingerprint: `{report['corpus_hash']}`", "",
             "## What was measured", "",
             "Source recall@k measures expected source documents retrieved. Chunk precision@k measures the share of retrieved chunks from expected sources. MRR measures the first expected source's rank. Reference evidence recall checks curated text fragments in retrieved chunks. These are small-set retrieval proxies, not semantic answer quality.", "",
             "Citation validity checks source IDs and exact quotations; it does not establish that a generated claim follows from a quotation. Faithfulness and relevance remain unmeasured until a person reviews the answers.", "",
             "## Results", "", "| Metric | Observed |", "|---|---:|"]
    labels = {"case_pass_rate": "Complete reference checks", "behavior_pass_rate": "Expected behavior (routing only)", "source_recall_at_k": "Mean source recall@k",
              "chunk_precision_at_k": "Mean chunk precision@k", "mrr": "MRR",
              "reference_evidence_recall": "Retrieved reference evidence recall",
              "answer_evidence_recall": "Displayed reference evidence recall", "citation_validity": "Displayed citation invariant (not answer quality)"}
    for key, label in labels.items():
        value = summary.get(key)
        lines.append(f"| {label} | {value:.1%} |" if value is not None else f"| {label} | Not measured |")
    latency = summary.get("p95_latency_ms")
    lines += [f"| Pinned pipeline P95 (excludes HTTP/session setup) | {f'{latency:.1f} ms' if latency is not None else 'Not measured'} |",
              f"| Faithfulness (target 95%) | Not measured; manual review required |",
              f"| Answer relevance (target 90% rated ≥4/5) | Not measured; manual review required |", "",
              "## Per-question scores and failure analysis", ""]
    for suite, values in report.get("suites", {}).items():
        lines += [f"Suite {suite}: {values['questions']} questions; routing {values['behavior_pass_rate']:.1%}; complete reference checks {values['case_pass_rate']:.1%}.", ""]
    for row in report["cases"]:
        lines += [f"### {row['id']}: {row['question']}",
                  f"Category: {row['category']} · Expected: {row['expected_behavior']} · Observed: {row['status']}",
                  f"Behavior: {'PASS' if row['behavior_pass'] else 'FAIL'} · Source recall: {row.get('source_recall_at_k')} · Chunk precision: {row.get('chunk_precision_at_k')} · Evidence recall: {row.get('reference_evidence_recall')}",
                  f"Complete reference checks: {'PASS' if row.get('case_pass') else 'REVIEW'} · Displayed evidence recall: {row.get('answer_evidence_recall')}",
                  "", row["analysis"], "", "Answer / evidence:", "", row.get("answer", {}).get("text", "No answer"), ""]
        for citation in row.get("answer", {}).get("citations", []):
            lines += [f"- [{citation['number']}] {citation['title']} · {citation['location']} · {citation.get('url') or 'local document'}"]
        lines += ["", "Manual review: faithful claims ___ / total claims ___; relevance ___ / 5; notes ___", ""]
    lines += ["## Interpretation and next steps", "",
              "The development set includes the original 15 assignment questions plus separate review regressions, including on-topic unanswerable qualifiers. It is not a held-out production benchmark. Routing scores do not establish answer quality; complete reference checks also require reference fragments in both retrieval and displayed quotations. This exact-match proxy is still not semantic faithfulness.", "",
              "For generated answers, review each factual claim against its quoted evidence. Faithfulness = supported factual claims / all factual claims; unsupported claims count against the score. Also grade complete answers for relevance (1–5), tracking refusals and partial coverage separately. Do not treat exact quotation matching as a substitute.", ""]
    return "\n".join(lines)


def run_evaluation(service, run_id: str | None = None, progress=None) -> dict:
    started = perf_counter()
    settings = service.settings
    questions = load_questions(settings.root)
    if not questions:
        raise ValueError("No evaluation questions found.")
    cases = []
    # Pin one generation; no global lock is held while models or embeddings run.
    session = service.open_session()
    session_setup_ms = round((perf_counter() - started) * 1000, 1)
    metadata = session.metadata
    for index, case in enumerate(questions):
        try:
            answer = service.ask(case["question"], session=session)
            cases.append(score_case(case, answer))
        except Exception as error:
            log_exception(logger, f"Evaluation case {case['id']} failed", error)
            answerable = bool(case["expected_sources"])
            cases.append({**case, "status": "error", "behavior_pass": False, "case_pass": False, "latency_ms": None,
                              "source_recall_at_k": 0 if answerable else None,
                              "chunk_precision_at_k": 0 if answerable else None,
                              "reciprocal_rank": 0 if answerable else None,
                              "reference_evidence_recall": 0 if case.get("evidence_fragments") else None,
                              "answer_evidence_recall": 0 if case.get("evidence_fragments") else None,
                              "citation_validity": None,
                              "analysis": f"Execution failed ({type(error).__name__}); check server logs and provider configuration.",
                              "answer": {"text": "No answer; execution failed."}})
        if progress:
            progress(index + 1, len(questions))
    latencies = [row["latency_ms"] for row in cases if row["latency_ms"] is not None]
    summary = {"behavior_pass_rate": mean(cases, "behavior_pass"), "case_pass_rate": mean(cases, "case_pass"),
               "source_recall_at_k": mean(cases, "source_recall_at_k"),
               "chunk_precision_at_k": mean(cases, "chunk_precision_at_k"),
               "mrr": mean(cases, "reciprocal_rank"),
               "reference_evidence_recall": mean(cases, "reference_evidence_recall"),
               "answer_evidence_recall": mean(cases, "answer_evidence_recall"),
               "citation_validity": mean(cases, "citation_validity"),
               "p95_latency_ms": round(float(np.percentile(latencies, 95)), 1) if latencies else None,
               "faithfulness": None, "answer_relevance": None,
               "errors": sum(row["status"] == "error" for row in cases), "questions": len(cases)}
    suites = {suite: {"questions": len(rows), "behavior_pass_rate": mean(rows, "behavior_pass"),
                      "case_pass_rate": mean(rows, "case_pass")} for suite in sorted({row.get("suite", "assignment") for row in cases})
              if (rows := [row for row in cases if row.get("suite", "assignment") == suite])}
    challenge = settings.root / "evaluation" / "challenge_questions.json"
    report = {"id": run_id or uuid.uuid4().hex, "evaluation_version": 3, "app_version": __version__,
              "created_at": datetime.now(timezone.utc).isoformat(),
              "mode": settings.mode, "index_identity": settings.index_identity,
              "corpus_hash": metadata.get("corpus_hash"), "top_k": settings.top_k,
              "summary": summary, "cases": cases, "suites": suites,
              "challenge_sha256": hashlib.sha256(challenge.read_bytes()).hexdigest() if challenge.exists() else None,
              "latency_scope": "Pinned pipeline only: excludes HTTP, session setup, and client rendering.",
              "session_setup_ms": session_setup_ms,
              "evaluation_wall_ms": round((perf_counter() - started) * 1000, 1),
              "citation_metric_kind": "Validator invariant on displayed output, not a faithfulness measurement."}
    folder = settings.root / "reports" / "runs"
    folder.mkdir(parents=True, exist_ok=True)
    for extension, content in [("md", render_markdown(report)), ("json", json.dumps(report, indent=2))]:
        temporary = folder / f"{report['id']}.{extension}.tmp"
        temporary.write_bytes(content.encode("utf-8"))
        temporary.replace(folder / f"{report['id']}.{extension}")
    return report


class EvaluationJobs:
    """One local background job at a time; poll progress without blocking HTTP."""

    def __init__(self, service):
        self.service = service
        self.jobs = {}
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            if any(job["status"] == "running" for job in self.jobs.values()):
                raise ValueError("An evaluation is already running.")
            run_id = uuid.uuid4().hex
            total = len(load_questions(self.service.settings.root))
            self.jobs[run_id] = {"id": run_id, "status": "running", "completed": 0, "total": total}

        def progress(done, total):
            with self.lock:
                self.jobs[run_id].update(completed=done, total=total)

        def worker():
            try:
                report = run_evaluation(self.service, run_id, progress)
                with self.lock:
                    self.jobs[run_id].update(status="completed", report=report)
            except Exception as error:
                log_exception(logger, "Evaluation worker failed", error)
                with self.lock:
                    self.jobs[run_id].update(status="failed", error="Evaluation failed. Rebuild the index and check server logs.")

        threading.Thread(target=worker, daemon=True, name=f"evaluation-{run_id[:6]}").start()
        return {"id": run_id, "status": "running", "total": total}

    def get(self, run_id):
        with self.lock:
            return dict(self.jobs[run_id]) if run_id in self.jobs else None

