# Evaluation guide

## Run it

Open **Evaluation lab → Run evaluation**, or run `uv run python scripts/manage.py evaluate` from the project directory. Results are saved as Markdown and JSON in `reports/runs/`. The browser uses a background job and displays progress, so a long evaluation does not depend on one long HTTP request.

OpenAI-mode runs make embedding and generation calls. The shipped baseline was measured in extractive mode only. Use separate reports for each configuration and compare against the recorded corpus hash.

## The questions

`evaluation/questions.json` contains the original 15 questions, each with a category, expected response behavior, relevant source IDs, reference text fragments, and a rationale. Six additional review cases live in `evaluation/regression_questions.json`. The original set includes direct lookups, exact names, numeric constraints, two multi-document cases, two ambiguous questions, two missing-information cases and one instruction attack.

Ground truth is human-readable and never read by the retriever. The questions are a development set; tuning on them does not establish held-out performance. The fragments are partial reference evidence, not exhaustive gold answers.

## What each score means

| Metric | Definition | Limits |
|---|---|---|
| Source recall@k | Number of distinct expected sources in final retrieval / number of expected sources | Finding the right document can still miss the right section |
| Chunk precision@k | Retrieved chunks whose source is expected / all retrieved chunks | Coarse document labels can overrate an irrelevant section |
| MRR | Reciprocal rank of first expected source, averaged over answerable questions | Does not measure whether later evidence is complete |
| Reference evidence recall | Curated evidence fragments found in final chunks / all reference fragments | Exact normalized text matching; refreshes may require updated labels |
| Expected behavior | Fraction of questions with expected answer/evidence, refusal or clarification behavior | An evidence response is a preview success, not proof of an accurate full answer |
| Quote validity | Citations whose chunk IDs and normalized quotes match retrieval / citations shown | Not semantic faithfulness |
| Displayed evidence recall | Reference fragments present in shown citation quotations / all reference fragments | Exact-text completeness proxy, not semantic support |
| Complete reference checks | Correct routing plus complete source, retrieved/displayed reference and citation checks | Strict development check; not a human faithfulness grade |
| P95 latency | 95th percentile of measured end-to-end question times | Small sample; machine/provider/network dependent |

Retrieval metrics are averaged over answerable questions only. Current routing and complete-reference checks include all 51 questions, with suite-level results. Faithfulness and answer relevance are `null` in automatic reports; do not label retrieval or quotation scores as faithfulness. Execution errors are visible and count as failed checks.

## Human review required

For each generated answer:

1. Break the answer into factual claims.
2. Read the quoted source and the surrounding retrieved chunk.
3. Mark a claim supported only if the evidence establishes the full claim, including amounts, exceptions, jurisdiction and approvers.
4. Record `faithful_claims` and `total_claims` in the JSON report's `human_review` object.
5. Give relevance a 1–5 score: does the answer address the actual question completely and without distracting material?
6. Record notes for missing sources, partial answers and refusals.

Aggregate faithfulness = total supported factual claims / all factual claims. The target is at least 95%. The relevance target is at least 90% of answerable responses rated 4 or 5. Refusal correctness is reported separately so a system cannot inflate faithfulness by refusing everything. Manual scores are stored in exported JSON for review; the UI does not aggregate edited manual scores automatically.

## Historical pre-review baseline and failures

The first extractive run indexed six pages into 276 chunks, with 14/15 expected behaviors, source recall@5 of 100%, chunk precision@5 of 72%, MRR 1.00 and reference evidence recall of 95%. Every displayed quotation matched its retrieved source. These observations apply to that snapshot and configuration only.

**Q10 — incomplete multi-topic evidence.** Both expected source documents appeared, but the top five chunks did not include every reference fragment. Long communication sections and competing PTO chunks can crowd out the specific definition; inspect candidate rankings and consider topic-aware retrieval, larger candidates or a neural reranker, then remeasure.

**Q15 — historical refusal mismatch.** The pre-review extractive path returned real expense passages for a request to ignore instructions and invent a policy. This is fixed in the post-review run by the request/scope assessment. Prompt and semantic-support controls still require ongoing testing.

**Untested live generation.** Provider request construction is checked with mocked HTTP responses. Live OpenAI answer quality, cost and latency still require a configured key and a separate evaluation run. No 95% faithfulness claim can be made from the extractive baseline.

## Improve deliberately

Use the per-question report to identify a specific failure. Change one retrieval decision at a time (chunk size, overlap, candidates, top-k, neural mode, reranker), rerun the development set, and compare evidence recall and latency. Add unseen questions and human review before presenting a final quality claim.


## Post-review evaluation (version 2)

Six additional cases in `evaluation/regression_questions.json` cover Mars/Jupiter policy qualifiers, unavailable personal balances, short named topics and possessive apostrophes. The standard run evaluates all 21 questions on one pinned index snapshot without holding a network-duration lock.

Routing success requires the expected response type and relevant cited output for answerable questions. Complete reference checks additionally require full expected-source recall, full retrieved reference-fragment recall, full displayed-quotation reference recall, and valid citations. The UI's primary pass/review labels use this stricter check; routing alone is labeled separately. Missing or failed latency is not reported as zero. Reports publish atomically and execution/worker errors include local stack-frame diagnostics.

The post-review run has 21/21 routing checks, 15/21 complete reference checks, 100% source recall, 70.77% chunk precision, 96.15% retrieved reference recall and 65.38% displayed reference recall. Exact quote validity is 100%. Q03, Q05, Q08, Q09, Q10 and R06 retain evidence omissions; Q10 also misses one reference fragment in retrieval. These exact-match proxies still require manual semantic review. See `reports/REVIEW_EVALUATION.md` and `docs/REVIEW_FIXES.md`. The old baseline above is retained as history rather than replaced by a quality claim.

## Round-two evaluation (version 3)

Thirty cases in `challenge_questions.json` are recorded by SHA-256 in `challenge_manifest.json`. They were created before implementation and not edited afterward, but observed during development; they are a locked challenge set, not a statistically held-out benchmark. The current report has 50/51 routing checks and 41/51 complete reference checks; challenge-only results are 29/30 and 26/30. H05 remains a valid paraphrase that preview refuses. Human faithfulness/relevance are still null.

The citation percentage is a validator invariant on displayed answers, not a quality measurement. P95 measures the pinned pipeline only; `session_setup_ms`, `evaluation_wall_ms` and `latency_scope` state the omitted costs. A small separate local HTTP benchmark is diagnostic and does not establish production/OpenAI-mode latency. See `REVIEW2_FIXES.md` and `reports/REVIEW2_EVALUATION.md`.
