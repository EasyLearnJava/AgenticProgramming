# PolicyLens — Week 2 project brief

## One-liner

My RAG app helps employees and new hires answer expense, time-away, password and communication policy questions from six named public GitLab handbook pages in a local web workspace, targeting 95% claim faithfulness and 90% answer relevance, with P95 responses under 10 seconds in configured OpenAI mode.

These are evaluation targets. The shipped extractive preview measures retrieval and citation mechanics; semantic faithfulness and relevance require human review. Live OpenAI-mode quality remains to be measured.

## Framework

| Field | Decision |
|---|---|
| Use case | Employees and new hires ask policy questions in a local browser interface. Responses cite specific handbook chunks or request clarification/refuse when evidence is insufficient. |
| Corpus | Six English public GitLab handbook pages: Spending Company Money, Global Travel and Expense Policy, Time Off and Absence, Time Off Types, Password Guidelines, and GitLab Communication; snapshots are Markdown with source manifests, and user uploads may be TXT/Markdown/PDF. GitLab's public handbook is the source of truth; the local corpus is a dated subset. |
| Ingestion + cleaning | A manual refresh script extracts main article content, removes navigation/scripts/boilerplate, decodes entities and preserves headings. Local loaders normalize whitespace, parse UTF-8 text, and extract PDF text with page numbers; scanned PDFs require prior OCR. |
| Ingestion + freshness | Starter snapshots ship with fetch times and content hashes; users upload additional local files through the UI. The freshness target is 7 days, checked visibly at runtime; refresh is manual with the provided script and requires a rebuild, so this version does not promise an automatic SLA. |
| Chunking + embedding | Markdown headings define sections; long sections are recursively split at 500 cl100k_base tokens with 75-token overlap. OpenAI mode uses text-embedding-3-small neural embeddings; extractive preview uses explicitly lexical hash vectors for an offline demonstration. |
| Retrieve | SQLite persists metadata, chunks and vectors; exact cosine search and BM25 are joined with reciprocal rank fusion, followed by a lexical coverage reranker. Retrieve up to 16 candidates per channel and keep top-5 chunks; the store and embedding adapters can be replaced independently. |

## Additional decisions

- Generation: LangChain `ChatOpenAI`, default `gpt-4.1-mini`, structured claims with quotations.
- Orchestration: LangGraph `retrieve → assess → answer/stop` with observable step timings.
- Refusal: missing topics ask for detail; unsupported query qualifiers and weak passage-body evidence refuse; OpenAI is instructed to refuse incomplete evidence; unverifiable generated citations withhold the answer.
- Citation contract: every displayed generated claim references retrieved chunk IDs and exact supporting quotations; quotation matching alone does not prove semantic entailment.
- Latency ceiling: P95 below 10 seconds is the target; provider request timeouts are 30 seconds with one retry, so this is an observed performance objective, not an enforced deadline.
- Evaluation: 15 original questions plus 6 first-review and 30 challenge questions including ambiguous, multi-document, out-of-corpus and instruction-attack cases; automatic retrieval metrics plus manual semantic review.

## Deliverables present

- Working local Q&A/evidence application with citations, upload, indexing and retrieval inspection.
- Modular, commented Python backend and browser JavaScript features.
- Completed framework and architecture guide.
- Fifteen assignment questions plus six first-review and thirty challenge cases, runnable evaluation, actual report, retrieval scores and failure analysis.
- Focused automated tests and reproducible locked dependencies.


## Current implementation notes

Preview uses stemmed, rarity-weighted local evidence; uncertain lexical matches in OpenAI mode reach model answerability and support checks. Chunk text remains an original cleaned-source span. The 30-case challenge is locked but used during development, so it is not a blind held-out result. Pipeline timing excludes HTTP/session setup; end-to-end latency remains a separately measured target.
