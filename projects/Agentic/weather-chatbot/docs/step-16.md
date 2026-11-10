# Step 16 · Park Guidance with Retrieved Sources

Step 16 adds reviewed National Park Service preparation guidance for Zion, Grand Canyon and Yosemite, including
selected trails. The agent resolves an explicit destination, retrieves applicable passages and combines them with
weather when requested. Source cards and the Knowledge pages expose the evidence and retrieval decisions.
See [step 17](step-17.md) for separate official notice checks; this index remains preparation guidance.

**In one line:** resolve the complete place name → retrieve scoped guidance and optional weather → cite the evidence.

## What you'll build

- A versioned Qdrant collection containing public passage text, provenance, native BM25 and dense vectors.
- Destination and seasonal constraints, with hosted MiniLM and BM25 combined through rank fusion.
- Shared park tools, source cards, source/vector browsers and a protected Retrieval Playground.
- Failure visibility, citation restrictions, health coverage and independently graded retrieval and answer checks.

## What you'll learn

- Why applicability metadata must be reviewed separately from relevance scores and document names.
- How to prepare text without generating vectors, then publish one verified hosted embedding per chunk.
- How to inspect actual ranking decisions and test failures without depending on a language model.
- Why citation presence, evidence retrieval and answer faithfulness are different measurements.

## Before you start

Use Python 3.13 and the committed lockfile. `uv sync --locked` installs the development tokenizer; production uses
`uv sync --locked --no-dev`. There are no local model weights or ML dependency group. Qdrant credentials are required
for both BM25 and semantic retrieval. Gemini's configured key is required only for chat answers. The credential-free
harness uses recorded provider scores and does not require a live Qdrant connection.

## The design

![Park guidance: ingestion, retrieval and inspection](images/step-16-design.svg)

| Decision | Why |
|---|---|
| Reviewed destination and season metadata | Similar names and waterfalls must not inherit unrelated advice |
| One Qdrant park collection | Public text, native BM25 and dense vectors share a single store |
| Compact release catalog with record hashes | Remote evidence must match approved text, metadata and scope |
| Tokenizer-only preparation | Keep safety qualifiers within the model budget without local vectors |
| Explicit, idempotent publication | Reuse verified points; embed each missing chunk once per generation |
| Separate provider outcomes | Distinguish dense fallback, database failure and genuine no-match results |
| Bounded POST bodies under `/api/` | Questions stay out of generated URLs and inside the edge rule's scope |
| Shared retrieval diagnostics | Playground scores and selected context cannot drift from chat search |
| Links restricted to retrieved URLs | Source cards and answer links follow the same evidence boundary |
| Weather failures retain their class | Guidance can survive while Activity still reports the outage |

## Files

| File | What it does |
|---|---|
| `nimbus/parks.py` | Destination resolution, scope, verified evidence and context selection |
| `nimbus/park_ranking.py` | Season interpretation and rank fusion |
| `nimbus/park_semantic.py` | Bounded Qdrant records, native BM25 and hosted dense retrieval |
| `tools/setup_park_search.py` | Explicit, verified hosted publication |
| `nimbus/park_tracing.py` | Private operational retrieval spans |
| `nimbus/park_ingest.py`, `data/parks/manifest.json` | Reviewed source sections and season metadata |
| `nimbus/park_text.py`, `tools/build_park_index.py` | Record hashing and tokenizer-only preparation |
| `nimbus/park_tools.py`, `nimbus/answer.py`, `nimbus/chat.py` | Agent, failures and validated citations |
| `nimbus/knowledge.py`, `nimbus/retrieval_gate.py` | Browsing, body-only requests and resource limits |
| `templates/knowledge_*.html`, `public/static/knowledge.css` | Escaped, accessible Knowledge views |
| `public/static/retrieval.css` | Responsive retrieval score display |
| `nimbus/config.py`, `nimbus/app.py`, `pyproject.toml`, `uv.lock` | Configuration and dependency boundary |
| `nimbus/health.py`, `nimbus/observability.py` | Published index health and operational outcomes |
| `tools/eval_parks.py`, `tools/eval_park_hybrid.py` | Real-provider retrieval comparisons |
| `tools/park_replay.py`, `evals/park-retrieval-recording.json` | Version-bound recorded retrieval |
| `evals/parks.json`, `evals/golden.json` | Labeled retrieval evidence and separate live-answer requirements |

## How it works

### `nimbus/park_ingest.py`

① Missing reviewed headings stop publication. ② Complete paragraphs and their qualifiers remain together.
`SourceSpec.section_seasons` explicitly marks seasonal sections; other sections inherit the source's reviewed
applicability. No season is inferred from a substring such as “Nevada Fall.” Publication validates all records and
writes prepared text and a matching compact catalog, each replaced atomically. Their versions must agree before
publication. Source publication dates and fetch timestamps remain distinct.

### `tools/build_park_index.py`

The default build reads reviewed snapshots. `--refresh` downloads allowlisted NPS pages with a 15-second source
limit and requires review before publication. A pinned tokenizer reserves title/heading tokens and splits text to
fit the 256-token MiniLM budget. It loads no model weights and produces no vectors. `prepared.json` carries the
public chunks; `catalog.json` carries only destination and integrity metadata. All 40 original passages are preserved.
Default preparation makes no network calls. Hosting the app never runs preparation or publication.

### `nimbus/parks.py`

Resolution matches reviewed aliases and rejects unknown geographic qualifiers. For example, Yellowstone's Grand
Canyon and Kanarra Creek narrows do not resolve to the covered Grand Canyon or Zion destinations. The resolver is
conservative and is not a global geographic search service; the agent should pass the complete place name.

Retrieval ① reads and verifies Qdrant text against the compact catalog, ② constrains both hosted ranking branches
by park, destination, generation and season, and ③ applies reciprocal rank fusion (RRF). Nimbus removes generic
query terms and expands reviewed concepts. Qdrant's native BM25 scores the prepared text field, which repeats section
headings for weighting. Hosted MiniLM supplies cosine scores; no second embedding is generated for BM25.

RRF combines ranks instead of incompatible raw scores: `1 / (60 + BM25_rank) + 0.1 / (60 + semantic_rank)`.
Missing/ineligible contributions are zero. Dense ranks start at cosine `0.30`; a candidate without a BM25 match
must reach `0.55` to enter. Ranking uses order, so first-ranked weak and strong dense matches receive the same bonus.
These calibrated heuristics are not confidence guarantees. Ties use chunk ID. At most four passages fit within
10,000 text characters; their text and citations come from verified Qdrant records.

An actual date determines the season. Without a date, an explicit season or one unambiguous seasonal phrase can
filter the candidates ("in spring", "winter gear"). "Fall" is surely the season only after a word such as "in",
"this" or "late"; any other "fall" may be the verb, a waterfall or a second season ("a fall hiking", "Yosemite Fall",
"summer and fall"), so the question gets no season from its words. A season joined to a word ("spring-fed") is
ignored. A question that names a month ("May" only as "in May" or "May 12") gets no season from its words, and
proper names such as Nevada Fall do not count. Conflicting explicit date/season inputs are rejected.

`search(..., explain=True)` adds the same raw scores, ranks and exclusion decisions used by normal search.
A missing semantic score is distinct from zero similarity. The corpus and per-request diagnostics do not store
visitor conversations or query history.

### `nimbus/park_semantic.py` and `tools/setup_park_search.py`

Setup ① verifies dedicated collection ownership and native scored-text support, ② embeds approved title/section/text
with hosted `sentence-transformers/all-minilm-l6-v2`, and ③ verifies payloads, vectors, counts and BM25 queryability
before publishing a readiness marker. It stores one 384-dimensional cosine vector per chunk. It reuses existing
verified points; repeated setup generates zero new embeddings. A partially uploaded generation can resume safely.
The park collection must differ from the private weather-answer cache, and publication never runs at startup.

Runtime requires the matching model/profile/generation marker and validates full records against complete-record
hashes and metadata from the compact catalog. Candidate scores must be finite, in range and within the same scope.
Provider calls have bounded responses and deadlines. A failed dense branch can retain successful BM25 guidance.
A failed catalog or BM25 request returns unavailable; there is no SQLite fallback. Cancellation propagates.

Search text is sent to Qdrant, and publication sends public source text. The adapter does not attach full chat
history or preferences. Logs and traces exclude questions, source bodies, vectors and keys.

### `nimbus/park_tracing.py`

A park retrieval span contains catalog, BM25, semantic lookup and rank-fusion children. Chat retrieval nests inside
its tool trace; a Playground run can have its own trace linked from Activity. Approved metadata records outcome,
provider,
mode, counts and whether the season came from a date, an explicit selection or the question. A semantic failure is
marked failed even when BM25 supplies usable guidance. No query or passage content is serialized.

### `nimbus/park_text.py` and configuration

Shared helpers produce the dense input and canonical complete-record hash. The tokenizer is development-only;
the runtime has no SentenceTransformer, Torch, local weights or SQLite connection. `PARKS_SEMANTIC_PROVIDER=qdrant`
is the sole provider, with `hybrid` the default mode. `lexical` uses only Qdrant BM25; `auto` also uses the hosted
hybrid path. `PARKS_ENABLED=false` disables park tools and Playground execution. The default collection is
`nimbus_park_guidance_v2`; it cannot share the weather-answer cache collection.

### `nimbus/app.py`

② The app creates one shared knowledge service and one playground request gate. The existing weather lanes retain
their contracts. Source browsing remains available independently of Gemini; no index download, ingestion or model
load occurs while creating the service.

### `nimbus/park_tools.py`

① Validated destination/search operations run within their existing deadline. ② Returned passages retain source
URLs and dates in a separate artifact. `knowledge.call` logs contain tool names, outcomes, versions and timings,
never question text, query vectors or passage bodies. Missing guidance does not manufacture a live weather result.

### `nimbus/answer.py`

① A weather lane opens only if a weather tool is invoked; concurrent calls share its lifetime. A document-only
request does not connect to MCP. Setup failures retain their original Nimbus error class in per-turn state while
being returned to the model as a sanitized tool failure. The SDK context opens and closes in its owner task.
The final Markdown renderer removes unsupported park citation targets, preserving readable labels; explicitly
reviewed weather-authority links remain available for warning references. Raw HTML and unsafe protocols stay disabled.

### `nimbus/chat.py`

② Tool events collect source URLs from this turn's successful retrieval. ③ Completion renders citations against
that set. A retained weather-setup failure finishes through the existing failure branch with `chat.failed`, its
original class and a visible note, while preserving any supported guidance. It cannot be logged as `chat.done`.
The fixed park prompt extensions preserve instruction-injection rules and city-weather behavior in both feature modes.

### `nimbus/knowledge.py` and `nimbus/retrieval_gate.py`

`/knowledge/sources` and `/knowledge/chunks` read verified Qdrant records without generating embeddings. The PCA
map uses actual stored Qdrant vectors, keeps its projection stable across filters and is not the retrieval algorithm.
`GET /knowledge/retrieval` displays an empty form; query-string submissions do not run retrieval.

① `POST /api/knowledge/retrieval` reads at most 16 KiB, rejects duplicate/unknown fields and foreign browser origins,
and validates the question, destination, date and optional season. ② The page calls the same search with diagnostics,
including actual keyword terms, raw scores, branch ranks, RRF contributions and context-selection reasons. The gate
permits twelve requests per minute per caller and two in flight per app instance, with bounded expiring bookkeeping.
The existing planned `/api/` edge rule additionally limits requests across serverless instances; verify it before
release. In-process limits alone are not a distributed firewall. Inputs/results are not persisted or cached.

Templates escape source and question text. Native forms and links need no JavaScript or inline styles. Missing
configuration, version mismatch and provider failure have explicit states; failed branches are not displayed as
zero similarity. The score table scrolls within its region on a phone.

### `nimbus/health.py` and `nimbus/observability.py`

Health includes a `park-index` check when parks are enabled. An invalid index makes overall health fail while
working weather lanes retain their own statuses. The check verifies the published Qdrant generation with a bounded
network request; it generates no embeddings and changes no stored records.
Activity includes `knowledge.call` and `lane.open.failed`, and tool filters accept knowledge operations. MCP setup
failures appear through the existing Errors and `?failed=McpLaneError` views. Questions and evidence remain absent
from operational logs.

### `tools/eval_parks.py` and the evaluation records

The retrieval cases include paraphrases, name collisions, unsupported questions and dated Mist Trail safety
checks. A source and its labeled evidence must appear in the same scoped passage. Reports include evidence recall@4,
top-1 evidence and MRR@4; rank-sensitive cases can require an earlier result. Small candidate sets remain weak tests
of ordering. These checks measure retrieval, not whether Gemini faithfully uses the evidence.

`tools.eval_park_hybrid` compares BM25, semantic-only and fused results using the same labeled evidence. It records
provider failures separately and exits unsuccessfully if hosted requests fail or fused evidence misses its rules.
Inspect top-1 and MRR as well as recall@4; a top-four pass alone does not prove better ranking. Its JSON contains
case IDs, grades and ranks, without question or passage text.
The semantic-only baseline independently uses the `0.30` hosted cutoff without the hybrid BM25 admission guard.
See [current validation](technical-details.md#qdrant-only-migration-validation) and the clearly labeled historical
calibration record for measured results and the limits of reusing tuning questions as evidence. Offline harness
checks use recorded Qdrant scores with the real fusion/scoping code; they do not measure current provider quality.

The original thirteen weather goldens remain, plus five park-answer scenarios. Three require official citations;
two check an unsupported geographic name and ambiguity. The answer evaluator preserves actual citation targets
and can require or restrict them. Live runs still need Gemini and a deployment/local instance of this code.

## Run it

```bash
uv sync --locked
uv run python -m tools.build_park_index
uv run python -m tools.setup_park_search
uv run uvicorn main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open `/knowledge/retrieval`, choose a destination and optionally a date, then submit a question. Results include
candidate scores, selected context, exclusions, timing and provenance. The native form submits to the API path
without putting the question in the address. Source refreshes and index writes remain separate operator actions.

For hosted retrieval, set `PARKS_SEMANTIC_PROVIDER=qdrant`, `PARKS_RETRIEVAL_MODE=hybrid`, `QDRANT_URL` and a private
credential in ignored `.env.local`, then run `uv run python -m tools.setup_park_search`. The optional
`PARKS_QDRANT_COLLECTION` defaults to `nimbus_park_guidance_v2`; `PARKS_QDRANT_API_KEY` can supply a separate
credential.
Serving needs read access; setup additionally needs collection/index/point write permission. The existing bundled
prepared text can be published without local inference. Local settings do not enable the feature on Vercel.
[Hosted configuration and validation](waiting-on-you.md#qdrant-hybrid-park-retrieval).

## Test it

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run pytest tests/e2e --browser-channel msedge
uv run python tools/mutation_check.py --hardening
uv run python -m tools.eval_parks --lexical-only
uv run python -m tools.eval_parks
uv run python -m tools.eval_park_hybrid
```

Current Qdrant-only provider validation uses generation `5b2eddcd5a2f6a24`: all 40 original public chunks are present.
BM25 and hybrid passed all 41 resolved cases, with no provider failures or hybrid evidence regressions. Semantic-only
passed 39/41; the two spring Narrows clothing cases still missed required supporting evidence. Hybrid top-1 was 78.9%
and MRR@4 was 0.890, versus BM25's 73.7% and 0.857. See `evals/park-hybrid-last-run.json` for individual case grades.

The full 47-case live retrieval run, including unsupported and ambiguous destinations, passed and supplied
`evals/park-retrieval-recording.json`. Credential-free replay then passed 461/461 harness scenarios, including those
47 recorded park cases. Recording binds method, scope, corpus and eval definitions; unknown requests fail closed.
Focused tests verify tokenizer-only preparation, unchanged source records, identity checks, replay privacy and
provider-failure grading. Replay does not recheck Qdrant availability, and retrieval checks do not grade Gemini.

**Historical local evidence:** the original SQLite/CPU implementation passed 853 unit tests, 227 Edge tests and
270 mutations. Its index was `d93691d32a848853`. Those counts and the production check below describe that older
build, not the current migration. They are retained as history, not substituted for current release validation.

## Deploy it

The evidence below predates hosted hybrid retrieval and the Qdrant-only migration. It validates neither current
production configuration nor a current tag. Use [the release checklist](waiting-on-you.md#qdrant-hybrid-park-retrieval)
for this migration; preserve the exact commit/deployment association in the historical evidence.

Production validation was performed on **4 November 2026**, starting at 13:33 UTC. The exact source was
`5de2c5c06300b4afc52c3ba0e4bec85f060d96f3`, with Vercel deployment `dpl_HXVLKC8omqqMG4giJheCaFCosfcE`.
Requests used [the production address](https://weather-chatbot-hazel.vercel.app). Vercel's API confirmed the same
deployment and full source SHA before and after each chat request. GitHub's `check` and `audit` jobs passed.
Vercel reported a ready FastAPI function of 63.72 MB; production used the expected keyword retrieval profile.

| Check | Observed result |
|---|---|
| Production health | All four weather lanes and the park index passed |
| Source documents and vectors | 13 documents and 40 stored vectors visible |
| POST Retrieval Playground | Four scoped Narrows passages and official links returned using keyword retrieval |
| Existing eighteen chat goldens, initial batch | 14 passed, two model timeouts and two completed expectation failures |
| Timeout-only rechecks | Both timed-out existing cases passed once rechecked; original failures remain recorded |
| Park guidance chat | Yosemite and Grand Canyon cases passed initially; Narrows passed on its timeout-only recheck |

Two completed failures remain: `too-far-ahead` called `geocode_location` despite its no-tools requirement;
`park-ambiguous-destination` resolved the two parks separately and retrieved guidance instead of requesting
clarification. Timeouts before any tool call were classified separately, without claiming that a tool was skipped.

**Release gate: failed.** Both completion tags were withheld for this validation run. The two completed failures
must be addressed and live checks repeated against the intended tag commit. No runtime or security implementation
was changed during this validation. Machine-readable evidence and the predefined plan were saved separately as
`steps-16-17-production-validation.json` and `steps-16-17-validation-plan.json` in the task outputs.

The recorded deployment can be inspected at
[Vercel](https://vercel.com/silverado/weather-chatbot/HXVLKC8omqqMG4giJheCaFCosfcE). Preserve the index for rollback.

The current hosted architecture excludes source-preparation tooling and local model dependencies from production.
Deployment still needs the configured Qdrant endpoint, read credential and matching published generation. A successful
local run or an older tagged deployment is not proof that the intended Vercel build uses those settings.

## Things to take care of, and pitfalls

- Published preparation advice does not establish current closures, warnings, water availability or river conditions.
- A forecast reference does not represent every elevation or the upstream watershed; never infer that a trip is safe.
- A heading can contain a place name such as Nevada Fall; applicability must come from reviewed metadata.
- Changing the embedding model requires compatible document and query vectors and a rebuilt index.
- Citation-target validation cannot establish that every generated claim is supported; live answer review is separate.
- Both ranking branches now depend on Qdrant; a complete database outage means guidance is unavailable.

## Issues we hit

The review found deployment-weight assumptions, missing MCP failure visibility, a waterfall/season collision,
question URLs, over-permissive aliases, prompt-only citation targets and weak test assertions. Issues 111–118 in
[Issues and fixes](issues.md) record their fixes and checks. The original dependency advisories, tokenizer budget,
source-review findings and browser-stream timing issue remain recorded there as issues 105–110.

## Interview questions

**Why filter by destination before ranking passages?** Because semantically similar advice can describe a different
trail. Identity and applicability are constraints, while relevance determines which applicable passages to return.

**Does RAG require a vector database?** No. Retrieval can use keywords, embeddings or both. Nimbus uses one Qdrant
park collection for public text, native BM25 and dense vectors. A compact local catalog holds integrity metadata,
not another searchable corpus. Weather answer reuse has a separate collection in the same database service.

**Are embeddings generated twice?** No. Tokenizer-only preparation generates no vectors. Publication creates one
hosted MiniLM vector for each missing chunk in a generation; repeated setup verifies and reuses it. Native BM25
indexes text without another embedding model. Runtime semantic queries still need their own query embedding.

**Why keep document retrieval separate from weather APIs?** Weather tools supply current conditions and forecasts.
Published guides supply preparation advice. Combining them must not turn a document into a claim about live status.

**What does offline replay prove?** Recorded Qdrant scores exercise the real resolver, scope, fusion and labeled
evidence rules without credentials. Replay cannot measure today's provider health or a model's answer faithfulness.
Separate live provider comparisons and answer evaluations measure those concerns.

**How do you keep a retrieval playground faithful to production search?** Add diagnostics to the shared retriever.
Report actual branch scores, ranks and selection limits; distinguish unavailable scores from zero similarity.
Tests compare explained and normal results, including dense-only failures, scoped candidates and context limits.

## Things to try

- Compare native BM25 and hybrid scores for the same question without calling Gemini.
- Ask about Mist Trail spray with spring and summer dates and inspect the safety passage.
- Try Yellowstone's Grand Canyon and Kanarra Creek narrows; no covered park should be substituted.
- Inspect the difference between a below-threshold candidate, the four-result limit and the context-character budget.
- Disable parks or use a missing index and inspect explicit UI and health states.

## What's next

Review corpus changes before publication and expand the benchmark before adding more destinations. A production
preview and live Gemini/citation evaluation remain required. Current notices use the separate step-17 NPS tool;
river conditions and other live safety facts cannot be inferred from stored preparation documents.
