# Round-two review: implemented changes and measured limits

The second review was valid. The v1.0.1 all-terms gate was too strict about language and too weak about meaning. It has been replaced; the application does not claim that a lexical gate or a second model proves faithfulness.

## Findings and disposition

| Finding | Implemented change |
|---|---|
| Word forms and contractions caused false refusals | Shared Unicode tokenization, a thread-local Snowball English stemmer, contraction expansion and split hyphen features replace the hand-written word-family mapping. |
| All query terms had to appear | Preview uses IDF-weighted coverage, a specific anchor and co-occurrence in a short passage. It no longer requires every term. Section metadata can supply a named subject, but the body must contain evidence and any requested amount/time/contact value. |
| Common words produced unrelated evidence | Question-type checks require a relevant value for amount, clock-time and phone-number requests. Explicit named-topic person questions can use a body role/name instead of an exact predicate word. This remains a heuristic. |
| Ambiguity differed between modules | One topic-feature function now serves vague-request detection, scope checks, retrieval and sentence extraction. Rule/process/pronoun-only questions clarify. |
| Lexical gate blocked neural paraphrases | OpenAI mode refuses clearly irrelevant requests but permits uncertain lexical matches to reach semantic answerability and claim-support checks. |
| 21/21 was presented too broadly | Original assignment and review questions remain separate from 30 locked challenge cases. Reports show per-suite results. The challenge file was created before implementation, kept unchanged and hashed, but used during development: it is not a blind/statistically held-out benchmark. |
| ASCII tokens lost accented/CJK text | Unicode words and accents are retained. CJK bigrams give a nonzero lexical fallback and support overlap-based retrieval; this is not a full multilingual segmenter or neural language understanding. |
| Uploaded text was HTML-unescaped | Upload cleaning preserves literal entities and URL query parameters. HTML decoding occurs only while parsing fetched HTML. |
| Full exceptions could reach uvicorn logs | An ASGI middleware catches unexpected errors before Starlette can re-raise them to uvicorn. Only exception type and frame locations are logged; expected validation errors retain their handlers. |
| Every request reread all vectors and content | Immutable index/profile/token caches are reused by generation. File hashes are reused by stat identity, with a 30-second forced verification bound. Rebuilds always verify captured bytes freshly. |
| P95 skipped session/HTTP costs | Reports explicitly label pinned pipeline timing and separately record session setup and evaluation wall time. A small local HTTP smoke benchmark measures the request path separately; neither is a production latency guarantee. |
| Revised uploads contradicted old versions | Cleaned filename plus extension defines a stable logical identity. Re-upload replaces the active revision and retains previous bytes in `data/upload_history/`. Legacy versions are grouped by logical name, newest active, with original files retained. |
| No way to remove uploads | DELETE performs reversible removal; restore/list-removed endpoints and UI actions provide normal recovery. Changes require reindexing. Starter documents remain managed by the corpus refresh workflow. |
| Valid quotes could support contradictory claims | Direct polarity reversals are rejected, then OpenAI answers require a separate structured semantic support/completeness review. Unsupported, unclear, incomplete or unreviewable answers are withheld. This adds a model call and can still share model errors. |
| Hyphenated quote variant was rejected | Quote normalization folds typographic dash variants and surrounding dash spacing consistently. |
| Balance navigation was treated as private-record lookup | Asking where/how to check a balance is allowed; asking for the individual's value still refuses without a data source. Attack checks match imperative requests rather than every quoted occurrence. |
| Heading-only/rewritten chunks | Chunking slices original section spans, drops heading-only fragments and asserts every chunk is a source-text substring. Six documents now produce 269 chunks. |
| Page could be framed | Responses set `X-Frame-Options: DENY` and CSP `frame-ancestors 'none'`. |
| Sentence scoring used filler words | Sentence extraction uses the same stemmed, information-weighted query features; missing-receipt queries now prioritize receipt evidence. |
| Citation validity looked like answer quality | Reports/UI label it as an accepted-output validator invariant, not a faithfulness/answer-quality score. Body-only citation checks reject heading-only evidence. |
| Same bytes in .md/.txt collided | Stable source identity includes the extension; the viewer/index can distinguish both files. |
| Redirect checked only after following it | Scheme, exact host, port and credentials are checked before every request and every redirect hop; automatic redirects are disabled. |
| Missing backend/UI regression coverage | Tests cover varied language, refusals/clarifications, semantic rejection, Unicode/PDF uploads, revisions/removal/restoration, cached reads, ASGI failure handling, redirects, and real ask/knowledge/evaluation DOM event flows. |

## Validation

The release passes **61 Python tests and 8 frontend tests**. The frontend tests use the actual markup and feature modules with mocked HTTP; Node dependencies are development-only and no frontend build is needed to run the app.

The final extractive development run contains 51 questions: 15 assignment, 6 first-review, and 30 challenge cases. Its observed routing is **50/51 overall** and **29/30 on the challenge set**; complete reference checks pass **41/51 overall** and **26/30 on the challenge set**. These are development-set results, not generalization or faithfulness claims.

The remaining routing failure is H05, “What happens if an expense is submitted late?” The preview misses the semantic relationship between “late” and the documented 90-day rule. This failure remains visible. The neural path is designed to handle paraphrases, but live OpenAI quality/latency has not been measured with user credentials. Several displayed excerpts still omit reference text; see the per-case report.

Human claim faithfulness and semantic relevance remain unmeasured. A model support check can be wrong or correlated with generation, and an exact-text reference match can undercount a correct paraphrase. The original targets remain targets.

Current evaluation: `reports/REVIEW2_EVALUATION.md`. The original and round-one reports remain available. The locked challenge manifest is `evaluation/challenge_manifest.json`.

