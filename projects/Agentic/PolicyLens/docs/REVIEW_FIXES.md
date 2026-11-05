# Review findings and implemented fixes

The pasted review was checked against the delivered source and reproduced with offline tests. The findings were valid; items described as conditional or unconfirmed were addressed with bounded defensive fixes and tests rather than treated as proof of an exploit.

## Answer behavior and grounding

| Finding | Change | Verification |
|---|---|---|
| Policy words made unrelated qualifiers appear answerable | Added a separate passage-body scope assessment; titles/headings do not supply evidence coverage. Unsupported meaningful terms refuse in both modes, and requests for private employee balances or invented policies refuse explicitly. | Mars/Jupiter/personal-balance regression questions and unit tests |
| One specific topic always clarified | Clarification now depends on a missing/vague topic rather than fewer than two tokens. Short but informative source sentences are also eligible for extraction. | `What is Okta?`, `Explain PTO`, `Explain SEC-101` |
| Straight/curly apostrophes and quotes mismatched | A shared Unicode/punctuation normalizer serves retrieval and quote validation; possessives tokenize consistently. Local embedding identity is bumped to v2 so old lexical vectors require rebuilding. | Unicode retrieval, valid punctuation-variant quote and altered-claim rejection tests |
| Model refusals and truncated output became 503 | Catch the SDK's model-refusal, length-finish, content-filter and parser exceptions and return a fixed refusal without citations. Provider/network outages still surface as service errors. | Actual mocked SDK refusal/length/content-filter responses through the API |
| Uploaded excerpts could fake XML prompt structure | Question, title, chunk ID and text are serialized as one JSON data object; evidence remains untrusted in the system instruction. | Uploaded closing-tag and quote strings remain data in the real request schema |
| Literal `[1]` text turned into the wrong citation | Answers now carry typed text parts with explicit citation-number metadata. The browser never guesses citation links from source/model text. | Frontend rendering tests |

The scope gate is conservative lexical validation, not semantic entailment. It can reject unfamiliar paraphrases, and JSON serialization alone does not eliminate prompt injection. Exact quote validation and manual semantic review remain necessary.

## Server, indexing and document handling

| Finding | Change | Verification |
|---|---|---|
| Origin compared to an unvalidated Host | Added TrustedHostMiddleware for `localhost` and `127.0.0.1`, outside request parsing; retained Origin checking. | Rebinding-style Host/Origin pair rejected before upload handler; valid loopback Host accepted |
| Network calls/evaluation held a global lock | Queries pin an index snapshot and release the state lock before network calls. Evaluations reuse one snapshot across the full run; rebuilds serialize separately and publish briefly under the state lock. | Blocked embedding/query calls leave status and existing queries usable; an evaluation can span a rebuild consistently |
| Corpus SHA differed from Windows-written bytes | Fetcher hashes and writes identical UTF-8 byte strings and publishes complete files by rename. Existing snapshot files and manifest hashes were repaired. | Mocked refresh verifies SHA-256 against actual bytes and LF output |
| HTML extraction dropped parent-list text and formatted table rows | Recursive block extraction preserves a parent item's own text plus nested items; tables emit cell text once even when cells contain paragraphs. | Synthetic nested-list and table regression fixture |
| Duplicate upload changed mtime and forced a rebuild | Identical existing content returns immediately without rewriting. | Stable mtime, fingerprint and index readiness after repeated upload |
| Edit during embedding could stamp old chunks as fresh | Parsers ingest captured bytes and metadata; the persisted fingerprint belongs to those bytes. If the live corpus differs at commit, the previous index is kept. | Edit inside embedding mock causes a rejected rebuild and unchanged prior index |
| SQLite connections were not closed | Store context manager now commits/rolls back and always closes in `finally`. | Connection use fails after success and exception paths |
| Upload cap ran after full multipart parsing | Bounded ASGI middleware checks declared and actual body bytes before multipart parsing, including chunked bodies. File content remains limited to 10 MB, with 64 KB bounded multipart overhead. | Declared-length and streamed-body oversized requests return 413 without calling upload |
| Logs omitted useful diagnostics | API, per-case evaluation and background-worker errors record exception type and traceback frame locations. Exception messages, source lines and request bodies are omitted. | Error-path tests verify a useful stack without private exception text |
| Ambient LangSmith settings could enable exports | App graph/model/embedding operations explicitly enter tracing-disabled contexts. | An inherited `LANGSMITH_TRACING=true` remains disabled during the call |

## UI and evaluation

- Download links retain their native Enter/Space behavior; only a focused expandable table row intercepts those keys.
- Missing/error latency displays an em dash, not zero seconds.
- Non-JSON HTTP errors show a readable status message instead of a JSON parser exception.
- The original 15 assignment questions remain intact. Six separate review regressions cover unsupported qualifiers, personal records, short topics and apostrophe wording.
- Routing checks require the correct status and valid source-bearing output. A new complete-reference check additionally requires relevant sources, retrieved reference passages, displayed reference quotations and valid citations.
- JSON and Markdown reports publish atomically. All-error runs retain missing latency rather than claiming zero. Background job progress/counts and the UI use the real question count.

## Validation and remaining evidence gaps

**37 Python tests and 4 Node frontend tests passed.** Coverage now includes evaluation/report/job flows, latest-report routes, successful PDF upload, Host checks, model failure responses, concurrency, Unicode, upload idempotency, captured-byte indexing and frontend error/citation behavior.

The updated 21-case extractive run observed:

| Metric | Observed |
|---|---:|
| Expected routing | 21/21 |
| Complete reference checks | 15/21 |
| Source recall@5 | 100% |
| Chunk precision@5 | 70.77% |
| Retrieved reference evidence recall | 96.15% |
| Displayed reference evidence recall | 65.38% |
| Quoted citation validity | 100% |
| Faithfulness / semantic relevance | Not measured |

Q03, Q05, Q08, Q09, Q10 and R06 still omit some reference text in the displayed excerpts; Q10 also lacks one retrieved reference fragment. These failures remain visible. Complete reference checks are an exact-text proxy, not a claim of semantic accuracy, and live OpenAI quality still requires a separate run with configured credentials.

The original pre-review baseline is preserved in `reports/BASELINE.md`; the new report is in `reports/REVIEW_EVALUATION.md` and `reports/runs/`.

