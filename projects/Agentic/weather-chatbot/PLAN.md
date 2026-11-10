# Plan: Nimbus, Rebuilt in Python

Nimbus is a weather chatbot: ask about the weather anywhere, and see each tool call behind the answer and the lane it
took. Its first version was built in TypeScript (Next.js and AI SDK); this plan rebuilds it in Python, as a
production-grade app and a tutorial at once: seventeen steps, each one adding one idea, each ending deployed and
working, and each with a chapter written while it's built. The first version's plan is kept as
[PLAN_deprecated.md](PLAN_deprecated.md).

## 1. The stack

| Layer | Choice |
|---|---|
| Language | Python 3.13, async throughout |
| Packages | uv: `pyproject.toml` and `uv.lock`, exact versions |
| Web framework | FastAPI; Uvicorn on a computer |
| Pages | Jinja2 templates; htmx 4 with its server-sent-events extension (from step 2); plain CSS |
| Markdown | markdown-it-py, raw HTML off: the answers and the docs |
| Agent | LangGraph (from step 4) |
| Model | Gemini, through `langchain-google-genai` (from step 3) |
| Tools | LangChain tools with Pydantic inputs; `httpx2` for the calls out, `tenacity` for retries (9.1.4: google-genai wants it below 9.2) |
| MCP | The official `mcp` SDK (FastMCP) for our server; `langchain-mcp-adapters` for the MCP lanes |
| Settings | pydantic-settings: one module reads the environment |
| State between requests | Chat stays in the browser (step 6); Open-Meteo uses Vercel Runtime Cache (step 7); public park guidance uses a dedicated Qdrant collection (step 16); explicitly approved travel defaults use optional Mem0 storage; optional Qdrant stores private weather answers with at most 120 seconds of reuse |
| Logs | structlog, JSON lines with a request id; Axiom (from step 12), read back onto the Observability pages (step 14) |
| Errors, traces | Sentry; LangSmith for the model's runs (from step 3), then the agent's (from step 4) |
| Tests | pytest; Playwright for Python with axe; mutation checks |
| Lint, types | Ruff; mypy in strict mode |
| CI, hosting | GitHub Actions with uv; Vercel's Python runtime |

Vercel runs many copies of the app, which share no process memory. The chat transcript lives in the visitor's browser;
agent requests send bounded conversation to Gemini. Weather data uses Vercel Runtime Cache. Step 16 uses Qdrant
for public park text, native BM25 and dense search; only approved metadata/hashes ship with the app. Optional Mem0
storage now holds only five typed travel defaults after explicit consent. An opaque signed browser cookie identifies
that preference scope; it is not an account or a LangGraph checkpoint. The app does not persist the conversation as
preference memory.
[Preference ownership, retention and deletion](docs/technical-details.md#follow-an-approved-preference).

The optional answer-cache extension checks exact and semantic matches before eligible weather-agent turns. Qdrant
Free hosts MiniLM inference and a dedicated 384-dimensional cosine collection through the existing async REST client;
the Vercel runtime gains no local ML stack. Signed one-day browser scopes and authenticated history are separate from
Mem0 consent. Request guards and original weather-data expiry constrain every hit. The cache is an optimization:
failures or uncertainty retain the existing agent, park and travel behavior.
[Cache architecture and validation](docs/technical-details.md#follow-a-weather-cache-hit).

Park retrieval uses one dedicated Qdrant collection for public text, source metadata, native BM25 and hosted
MiniLM and ColBERT vectors. Shared filters also scope BM25 statistics. Nimbus combines branch ranks, then Qdrant
ColBERT reorders at most 12 admitted candidates before four passages become context. Playground distinguishes
RRF and ColBERT scores; Activity links private retrieval-stage traces. A reranker failure retains RRF, a dense-only
failure retains BM25, and a full outage is unavailable. Preparation creates no embeddings; migration copies
verified MiniLM vectors and generates only ColBERT, while repeat publication reuses both.
[Retrieval setup and comparison](docs/technical-details.md#publish-and-validate-hosted-park-search).

## 2. The roadmap

| Step | What it builds | What you do |
|---|---|---|
| 1 | The project: uv, FastAPI, Ruff, mypy, pytest, CI, the first deploy; the page shell in Jinja2; the docs, the deprecated ones included, and the System design page; security headers; JSON logs with a request id | Switch the Framework Preset to FastAPI (done); delete the three `SENTRY_AUTH_TOKEN`/`ORG`/`PROJECT` variables |
| 2 | The chat streams a fixed answer over server-sent events with htmx; Stop; the question's checks and our own error sentences | |
| 3 | Gemini through LangChain, streamed; the system prompt; the input rules; a cap on each answer's length and time, since on Vercel, Stop never reaches the function | |
| 4 | The four weather tools and a prebuilt agent: the REST · no auth lane; tool chips with the wire view; LangSmith | The LangSmith variables (done) |
| 5 | The agent as our own LangGraph graph: step limit, last step without tools, time limits | |
| 6 | Chat memory: the conversation kept in the browser and sent back with each question, as untrusted input: only the visitor's and Nimbus's text, checked and capped, never a tool result (the tools run again); New chat | |
| 7 | Caching Open-Meteo's answers in Vercel's Runtime Cache, under our own namespace (on Hobby, a team's projects share one cache), with a key that can't collide or leak | |
| 8 | Our MCP server, with FastMCP, at `/api/mcp` | |
| 9 | The MCP · no auth lane, and the compare view | |
| 10 | The auth lanes: Apify's Actor over REST and over Apify's MCP server, each falling back to its no-auth twin | |
| 11 | Security: rate-limit rules, prompt-injection rules, privacy checks | The firewall's rules |
| 12 | Monitoring: Axiom, Sentry, LangSmith; `/api/health` with each lane's check, and the status dots | |
| 13 | Evals and release: golden questions as LangSmith datasets, a load test, rollback; Technical details; the backup deleted | |
| 14 | Observability: Activity, Performance, Evaluations and Health, read back from Axiom with a token that can only query; the menu in groups | The query token (done) |
| 15 | Activity by request: each a row that opens onto its timeline, shown only by its ref; every tool, lane, ending, reason and day on the other pages a link to its requests | |
| 16 | Park and trail preparation: official source ingestion, a versioned index, scoped Qdrant BM25 and semantic retrieval, citations and retrieval comparisons | Publish the dedicated public park collection and configure hosted settings before verifying the exact preview build |
| 17 | Official NPS notices: bounded API checks, a separate page, shared chat tool and source attribution | Configure the NPS key for the intended Vercel environments; verify notices and quota before releasing |
| 18 | Read-only Kiwi flights, trivago hotels and a shared national park trip planner | Local provider checks complete. Run repeated chat evaluations and verify the target preview before release |
| 19 | Deterministic replay, scored live trials, feedback and reviewed regression cases | Validate the operator-configured preview and review deployment evidence before promotion |

The current preference-memory extension adds explicit preview, save, edit, pause and verified deletion of an airport,
weather units, price currency, preparation interest and departure window. Current requests and explicit trip choices
remain authoritative; saved defaults never authorize a search or booking. It uses the existing chat, planner and
observability paths. Configuration and hosted validation remain separate release work on
[Waiting on you](docs/waiting-on-you.md#mem0-travel-preferences); checks must record the actual tested build.

The Qdrant answer-cache extension adds `off`, `shadow` and `on` rollout modes, a private
[Weather cache inventory](/weather-cache), cache-specific Activity outcomes and live embedding evaluations separate
from mocked adapter tests. The dedicated collection is configured locally, and mode `on` follows successful local
provider and chat checks. The validation record preserves the initial held-out recall shortfall and its subsequent
regression checks. Hosted settings and exact-build checks are on
[Waiting on you](docs/waiting-on-you.md#qdrant-weather-answer-cache). No new numbered completion tag is implied by
this extension or by local provider smoke checks.

Cache tracing records lookup and store outcomes, nested Qdrant operation timings, bounded similarity measurements
and fixed bypass reasons without private payloads. The same allowed details appear in the Nimbus trace explorer;
a cache hit keeps its request trace while avoiding a new model run. See
[Cache trace decisions](docs/technical-details.md#trace-a-cache-decision) and issue 177.

## 3. A chapter's sections

Each step's chapter (`docs/step-N.md`) has the same sections, in this order: the step in a paragraph and one line; What
you'll build; What you'll learn; Before you start; The design (a picture, and a table of decisions and why); Files; How
it works (a section per file, citing the circled numbers in its code); Run it; Test it; Deploy it (the build, and checks
on the live site); Things to take care of, and pitfalls; Issues we hit; Interview questions; Things to try; What's next.
Every output shown is from a real run. The Interview guide collects each chapter's questions word for word (a script
copies them; a test checks they match).

## 4. Code standards

- **Layout.** `main.py` is the entry point; `nimbus/` holds the app, one module per job; `nimbus/utils.py` the small
  pure helpers several modules share, each tested in `tests/unit/test_utils.py` (a helper is added only when the app
  uses it); `templates/` the Jinja2 templates; `public/static/` what Vercel's CDN serves; `docs/` the chapters and
  pages, with their pictures in `docs/images/`; `tests/unit/` and `tests/e2e/` the tests; `tools/` scripts for
  working on the app, such as the mutation check, which Vercel leaves out of the function.
- **Comments.** Each file opens with what it is; each step in a function is numbered (①, ②, ...), matching the
  chapter; each function has a docstring saying what it gives back.
- **Typing.** Every function is typed, and mypy runs in strict mode.
- **Lines.** At most 120 characters, in code and docs alike (a table's row is the one exception).
- **Tests first,** then the code, then the mutation check (`uv run python tools/mutation_check.py`): each rule
  broken on purpose must fail a test, and each new rule gets its mutation.
- **Versions.** Exact pins, chosen by uv with `exclude-newer` two weeks before the step (`[tool.uv]` in
  `pyproject.toml`), moved forward when a step adds packages.

| Thing | Convention | Example |
|---|---|---|
| Modules, functions, variables | snake_case | `read_markdown`, `request_id` |
| A function that converts | `to_...` | `to_request_id`, `to_app_url` |
| A boolean | `is_...` or `has_...` | `is_external` |
| Classes | PascalCase | `DocPage`, `RequestContextMiddleware` |
| Error classes | `...Error` | `UpstreamTimeoutError` (from step 3) |
| Constants | UPPER_SNAKE | `SECURITY_HEADERS` |
| Log events | dotted, lower case | `http.request` |
| Log fields | camelCase, as the TypeScript version's, so its Axiom queries still work | `requestId`, `deploymentId` |
| Templates | snake_case | `docs_index.html` |
| Tests | `test_` and what it checks, as a sentence | `test_every_page_has_its_file_and_every_file_its_page` |

## 5. How each step is done

1. **Build it:** the tests, the code, then the mutation check.
2. **Check it:** `ruff check`, `ruff format --check`, `mypy`, the unit tests, the browser tests.
3. **Write it down:** the chapter; the System design page and its diagram, with the parts the step adds; every
   problem met, in the issues log (how it was found, why, the fix, the check); the interview guide; the to-do list;
   the README's outputs, from one captured full run.
4. **Review it:** an independent review of the step, before the commit.
5. **Ship it:** commit (staged by path), tag `py-step-N`, push both; wait for CI and the deploy; check the live site,
   and add what the check found.

## 6. Rules at every step

- **A question is never logged or traced:** only its length (from step 3). A query string is never logged either.
- **Secrets** live only in Vercel's Sensitive variables, or in `.env.local` on a computer; only `config.py` reads the
  environment; no secret goes into code, docs, logs or a chat.
- **The Content Security Policy is enforced:** no inline script or style. Every response carries the security
  headers: the app's from its middleware, the CDN's files from `vercel.json`.
- **Every input is checked at the edge** with Pydantic, and every call out has a time limit (from step 3).
- **Every page passes axe's checks,** and none scrolls sideways on a phone.

## 7. The TypeScript version

The TypeScript documentation is archived in the repository. The app serves the current Python documentation.
The TypeScript code remains available in git history.
