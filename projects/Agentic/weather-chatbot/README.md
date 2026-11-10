# Nimbus: a Weather Chatbot, Rebuilt in Python

Nimbus answers questions about the weather anywhere, and shows each tool call behind an answer and the path it took.
Its first version was built in TypeScript; this is its rebuild in Python, with FastAPI, LangGraph and Jinja2, as a
production-grade app and a step-by-step tutorial at once. Each chapter covers the design, the code, the checks
performed, the pitfalls and interview questions. Live at https://weather-chatbot-hazel.vercel.app/.

Run `uv run python -m tools.harness run --mode replay` for a credential-free competition demonstration.
Open **Observability → Evaluations** for the scorecard and weekend matrix. The chapter includes a three-minute
walkthrough and instructions for a named preview. [The Evaluation Harness](docs/step-19.md)

**Optional travel preferences:** [My preferences](/preferences) lets a visitor explicitly save an airport,
weather units, price currency, preparation interest and departure window through Mem0. Current trip details take
priority. Preferences belong to this browser profile; no account or cross-device sync is provided. Weather,
notices, prices and availability still use the existing evidence sources.
[How memory works](docs/technical-details.md#follow-an-approved-preference).

**Optional weather answer cache:** Qdrant Free hosts MiniLM embeddings and short-lived weather answers. Exact lookup
precedes semantic matching; browser, location, dates, units, context and original data freshness must agree.
An accepted hit avoids Gemini and fresh tool execution. **Observability → [Weather cache](/weather-cache)** shows
this browser's normalized labels, source age and remaining lifetime. The maximum is two minutes, never renewed
by a hit. Local reuse is enabled after live checks; hosted activation requires its own validation and settings.
[How answer caching works](docs/technical-details.md#follow-a-weather-cache-hit).

**Task-scope checks:** recognized creative-writing requests receive an application-written redirect before memory,
cache or tool work. Normal weather and trip tasks continue; uncertain requests use a bounded Gemini classifier.
Tool chips still update live, while generated prose waits for a complete output check. An unavailable checker hides
the unchecked narrative, marks the request failed and can retain verified weather cards; it does not save the answer.
Each generated narrative needs an extra Gemini call, and uncertain inputs may need another, affecting latency and
quota. [Behavior, limits and focused checks](docs/technical-details.md#enforce-the-supported-task).

**The whole design on one page:** [Architecture and design](docs/architecture.md): what Nimbus does, how it's built,
how a question flows through it, why each choice was made, what makes it production grade, and what keeps it safe and
secure.

**In one line:** your browser → Vercel → the FastAPI app: the security headers, the request's id, the router → a page
from a Jinja2 template, JSON, or a question's answer, streamed as server-sent events of HTML that htmx puts into the
page → back to you, with its log lines. Gemini normally writes the answer through LangChain, from evidence collected
by the LangGraph agent and Open-Meteo tools. The optional guarded answer cache can serve a fresh weather answer
before a new model call; a miss or cache outage leaves the normal path available.

## What you'll build

Step by step: a FastAPI app with Nimbus's pages and docs (step 1); a chat that streams its answer with HTMX (2); answers
from Gemini through LangChain (3); a LangGraph agent with four weather tools (4, 5); chat memory kept in the browser (6)
and a weather cache (7); our own MCP server (8) and a lane through it (9); two lanes through Apify, with fallbacks (10);
then security (11), monitoring (12), evals and the release (13), and the Observability pages, read back from Axiom,
with the menu in groups (14). The full roadmap is in [PLAN.md](PLAN.md).

## What you'll learn

How to build an AI agent app the way it's run in production: FastAPI, Jinja2 and HTMX for the pages; LangChain and
LangGraph for the agent; MCP for its tools; Pydantic at every edge; structured logs with a request id; security
headers and an enforced Content Security Policy; tests in memory, in a real browser and for accessibility, with a
mutation check; and CI and deploys to Vercel on every push that changes it.

## Before you start

- **Python 3.13** and **uv** 0.9 or newer (`uv --version`), and Git.
- **For the browser tests:** Edge or Chrome on your computer, or `uv run playwright install chromium`.
- In this folder, `uv sync` makes `.venv/` and installs every package at the version `uv.lock` pins.
- Settings for your computer go in `.env.local` (copy `.env.example`); git never sees it.

## Files

| File or folder | What it holds |
|---|---|
| `main.py` | The entry point: `app = create_app()`, which Vercel and Uvicorn both look for |
| `nimbus/` | The app, one module per job: `app.py`, `config.py`, `constants.py`, `logger.py`, `middleware.py`, `pages.py`, `docs.py`, `health.py`, `chat.py`, `model.py`, `prompts.py`, `agent.py`, `answer.py`, `tools.py`, `open_meteo.py`, `weather.py`, `chips.py`, `cache.py`, `mcp_server.py`, `lanes.py`, `mcp_lane.py`, `auth_lanes.py`, `actor.py`, `apify.py`, `axiom.py`, `sentry.py`, `observability.py`, `axiom_query.py`, `goldens.py`, `errors.py`, `utils.py` |
| `nimbus/semantic_cache/` | Guarded answer reuse: policy, browser/history authentication, typed evidence, Qdrant REST service, chat integration and private inventory page |
| `templates/` | The Jinja2 templates: the shell with the menu in groups, the chat and the HTML of its answer's events, a list of pages, a page, the Observability pages, the 404 page |
| `public/static/` | The stylesheet, the icon, htmx 4 and its stream extension, and our `chat.js`, served by Vercel's CDN |
| `docs/` | The chapters (`step-N.md`), the system design, the issues log, the interview guide, the to-do list, the TypeScript version's pages (`*_deprecated.md`), and their pictures (`images/`) |
| `tests/unit/`, `tests/e2e/`, `tests/fixtures/` | The tests: the app called in memory, and the app in a real browser; Open-Meteo's recorded answers |
| `evals/` | The golden questions (`golden.json`), and their last run, kept (`last-run.json`) |
| `tools/mutation_check.py`, `tools/run_tool.py` | Breaks each of the app's rules on purpose, and checks a test fails; runs one weather tool on its own |
| `pyproject.toml`, `uv.lock`, `.python-version` | The packages, pinned to exact versions; the tools' settings; Python 3.13 |
| `vercel.json` | The CDN's files' security headers; the tests and tools left out of the function Vercel builds |
| `PLAN.md` | The roadmap, the chapter template, the code standards and the rules |
| `README_deprecated.md`, `PLAN_deprecated.md` | The TypeScript version's README and plan, kept |

CI is at the repository's root, in `.github/workflows/weather-chatbot.yml`.

## How it works

Each step's chapter explains it, in order:

| Step | Chapter | Status |
|---|---|---|
| 1 | [The Project, Its Pages and Its First Deploy](docs/step-1.md) | Done |
| 2 | [The Chat Streams Its Answer](docs/step-2.md) | Done |
| 3 | [Gemini Answers, Streamed](docs/step-3.md) | Done |
| 4 | [The Weather Tools, and an Agent That Calls Them](docs/step-4.md) | Done |
| 5 | [The Agent as a Graph of Our Own](docs/step-5.md) | Done |
| 6 | [The Chat Remembers, in the Browser](docs/step-6.md) | Done |
| 7 | [Open-Meteo's Answers, Cached](docs/step-7.md) | Done |
| 8 | [Our Own MCP Server](docs/step-8.md) | Done |
| 9 | [The MCP · No Auth Lane](docs/step-9.md) | Done |
| 10 | [The Lanes With Auth, Through Apify](docs/step-10.md) | Done |
| 11 | [Security: Rate Limits, Prompt Injection, Privacy](docs/step-11.md) | Done |
| 12 | [Monitoring: Axiom, Sentry, the Health Check and the Status Dots](docs/step-12.md) | Done |
| 13 | [Evals and Release: Golden Questions, a Load Test, Rollback](docs/step-13.md) | Done |
| 14 | [Observability: Activity, Performance, Evaluations, Health, and the Menu in Groups](docs/step-14.md) | Done |
| 15 | [Activity by Request, and Rows That Lead to It](docs/step-15.md) | Done |
| 16 | [Park Guidance with Retrieved Sources](docs/step-16.md) | Implemented |
| 17 | [Official Park Notices](docs/step-17.md) | Implemented |
| 18 | [Flights, Hotels and National Park Trips](docs/step-18.md) | Implemented, preview checks pending |
| 19 | [The Evaluation Harness](docs/step-19.md) | Replay, scored live trials and reviewed regressions. Hosted release requires preview evidence |

## Run it

```text
$ uv run uvicorn main:app --reload --no-access-log
INFO:     Will watch for changes in these directories: ['C:\\...\\weather-chatbot']
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [28048] using StatReload
INFO:     Started server process [20832]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

Then open http://127.0.0.1:8000 (the folder's path is shortened above). Each request writes one JSON line, with its id
and never its query string; this one is for `/docs?q=private`:

```json
{"method": "GET", "path": "/docs", "status": 200, "ms": 20, "event": "http.request", "level": "info",
 "ts": "2026-10-31T20:41:38.327075Z", "env": "local", "commit": null, "deploymentId": null,
 "requestId": "68d37b4d321f41f1"}
```

## Test it

Local preference-memory validation on 9 November 2026, against the working tree. These checks are not production
deployment evidence; the hosted settings and release checks are on [Waiting on you](docs/waiting-on-you.md).

```text
$ .venv\Scripts\python.exe -m ruff check .
All checks passed!
$ .venv\Scripts\python.exe -m ruff format --check .
225 files already formatted
$ .venv\Scripts\python.exe -m mypy
Success: no issues found in 181 source files
$ .venv\Scripts\python.exe -m pytest tests/unit -q
1735 passed in 38.88s
$ .venv\Scripts\python.exe -m pytest tests/e2e -q --browser chromium --browser-channel chrome
213 passed in 187.57s (0:03:07)
$ .venv\Scripts\python.exe -m tools.mutation_check --memory
...
11 of 11 caught
```

`uv run pytest` runs the unit tests; `tests/e2e` serves the real app with Uvicorn and drives it in a browser, on all
published pages and in the chat (leave out `--browser-channel chrome` to use Playwright's own Chromium). pytest prints
its platform line and each test's dot, and the mutation check a line per rule (each chapter lists its own).

The offline harness passed 455 cases, including six preference-default regressions. Two independent reviewers
checked the changes and their findings were fixed and rechecked. Live synthetic Mem0 create/read/update/delete and
stale-revision checks passed. Two live Gemini weather checks used saved metric units and then an explicit Fahrenheit
override correctly; both produced weather cards. Temporary Mem0 profiles were deleted and verified absent. These
two model checks are smoke evidence, not a repeated model-quality benchmark or a hosted deployment check.

For the separate weather-answer cache extension, run its unit/browser regressions and then the real hosted embedding
evaluation against synthetic fixtures:

```sh
uv run pytest tests/unit -k semantic_cache
uv run pytest tests/e2e -k semantic_cache --browser-channel chrome
uv run python -m tools.eval_semantic_cache --cases evals/semantic_cache.json
uv run python -m tools.eval_semantic_cache --cases evals/semantic_cache_heldout.json
```

Live reports separate provider failures, false hits and positive recall. Mock-provider tests verify the adapter
and safety rules; they cannot prove the hosted model's similarity quality. The live tool uses an isolated `_eval`
collection and cleans up its own fixtures. The recorded local results include the initial held-out shortfall,
its subsequent regression checks and a real chat hit; they do not imply a hosted deployment check.
[Cache validation evidence](docs/technical-details.md#local-validation-on-9-november-2026).

## When things go wrong

| You see | Why | What to do |
|---|---|---|
| `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.` | Starlette 1.8's test client prefers `httpx2` | `uv sync`: the dev group has `httpx2` (issue 1) |
| `error: Duplicate module named "conftest" (also at "tests\e2e\conftest.py")` | Two test folders without `__init__.py` | Keep the `__init__.py` files in `tests/` (issue 8) |
| `ModuleNotFoundError: No module named 'nimbus'` | A script run from another folder: Python looks in the script's folder, not yours | `PYTHONPATH=.` before the command (issue 6) |
| `Cannot navigate to invalid URL` with `C:/Program Files/Git/...` | Git Bash turned an argument starting with `/` into a Windows path | `MSYS_NO_PATHCONV=1` before the command (issue 6) |
| `The assistant isn't set up on this deployment yet.`, with `503` | No `GOOGLE_API_KEY`, or one Gemini refuses | Put your own key in `.env.local` and restart; on Vercel, set it in the project's settings and redeploy |
| `The chat couldn't read that request.`, with `415` | A question sent as JSON, or without the form's type | Send a form, `application/x-www-form-urlencoded`, as the page does; curl's `-d` does too |
| `ValidationError: 1 validation error for Settings` / `vercel_env` / `Input should be 'production', 'preview' or 'development'` | A setting with a value the app doesn't know, here `VERCEL_ENV=staging` | Fix or remove the value; the error names the setting |

## Things to try

- Add a chapter: a Markdown file in `docs/` and its `DocPage` in `CHAPTERS` (`nimbus/docs.py`); the tests say if
  you forget either. A page outside `/docs/`, in `PAGES`, also needs its route in `nimbus/pages.py`.
- Put `LOG_LEVEL=warning` in `.env.local`, restart, and watch the request lines stop.
- Send a forged id: `curl -i -H "x-vercel-id: not an id" http://127.0.0.1:8000/api/health` gets a new one back.
- Watch an answer stream: `curl -N --data-urlencode "question=Hi" http://127.0.0.1:8000/api/chat` prints each event
  as it comes (with your own `GOOGLE_API_KEY` in `.env.local`; without one, the chat says it isn't set up).
- Ask something off-topic: Gemini says, in one sentence, what it can do.
- Run a weather tool on its own, against Open-Meteo, with no key:
  `uv run python -m tools.run_tool get_air_quality '{"latitude": 28.61, "longitude": 77.21}'` (in bash).

## Documentation

The app explains itself: open **Documentation** in its menu, or read the same pages in [`docs/`](docs/): a chapter per
step ([step 1](docs/step-1.md) to [step 19](docs/step-19.md)), **Architecture and design**
([`docs/architecture.md`](docs/architecture.md)), the whole design on one page, the
**System design** ([`docs/system-design.md`](docs/system-design.md)), **Technical details**
([`docs/technical-details.md`](docs/technical-details.md)), weather and trip requests through the code,
**Issues and fixes**
([`docs/issues.md`](docs/issues.md)), **To do**
([`docs/todo.md`](docs/todo.md)), and **Waiting on you** ([`docs/waiting-on-you.md`](docs/waiting-on-you.md)), every
setting only you can change. Observability includes Activity, Weather cache, Performance, Evaluations and Health.
Under **Project**,
**Health check (JSON)** opens the monitor endpoint. **Weather MCP server** shows the connection address and tools.
The earlier TypeScript documentation is archived in the repository.

## Next

### Weather answer reuse

Keep `QDRANT_URL` and `QDRANT_API_KEY` in ignored `.env.local`, with `SEMANTIC_CACHE_MODE=shadow` for observation.
Run `uv run python -m tools.setup_semantic_cache` to create or verify the dedicated collection, its 384-dimensional
cosine vectors, filter indexes and strict capacity limits. The hosted Free MiniLM model uses Qdrant's key;
this adds no Torch, local model download or new production package.

After reviewing independent live evaluation and the intended preview, `SEMANTIC_CACHE_MODE=on` permits verified
reuse. `off` makes no cache network calls. The default collection is `nimbus_weather_cache`; the default semantic
cutoff is `0.80`, with independent guards always required. A miss is preferable to reusing the wrong city's answer.
[Hosted settings and checks](docs/waiting-on-you.md#qdrant-weather-answer-cache).

In the same browser, ask “Dallas weather,” then “weather in Dallas.” When a fresh match is accepted, the chat
shows a cache badge with a new answer reference. Open Weather cache for its expiry and source age. Switch to
“Vizag weather” in the same chat, then “Visakhapatnam weather”: the approved alias shares its own city entry.
Try a unit override, a park warning or a trip question to verify the normal flow. Unresolved place spelling,
unsupported wording and changed conversation context can deliberately bypass caching.

### Saved travel preferences

Keep `MEM0_API_KEY` and a stable, randomly generated `MEMORY_COOKIE_SECRET` of at least 32 characters in ignored
`.env.local`; set `MEMORY_ENABLED=true` and restart. Leave secrets blank in `.env.example`. Each hosted environment
needs its own configuration and redeploy. [Deployment checklist](docs/waiting-on-you.md#mem0-travel-preferences).

Open **My preferences**, select the values to remember, review the consent text and save. Alternatively, ask
“Remember that I fly from DFW, prefer Celsius and easy hikes” to get an editable preview; that question alone
does not save anything. Ask “Plan a trip to Zion next weekend” to use saved defaults, then “Plan a trip to Zion
next weekend from BOS” to override the origin for this trip. Changes to the trip do not silently update memory.

**Pause** stops preference use without deleting it. **Forget** requests deletion and confirms the result after
checking Mem0; an unconfirmed deletion stays visibly pending and can be retried. A failed read falls back to the
current request. The signed browser link and saved preferences expire after 180 days from saving. Expiry stops
normal use; it does not guarantee physical deletion. Delete preferences before clearing cookies if you want to
retain the ability to confirm their removal. **New chat** clears the conversation, not saved preferences.

### Flights, hotels and park trips

Set `FLIGHTS_ENABLED=true` and/or `HOTELS_ENABLED=true` in ignored `.env.local`, then restart. With park
guidance enabled, open `/parks/trip` or ask chat to plan a trip to Zion, Grand Canyon or Yosemite. Confirm
the dates, party and transport to compare quotes with the forecast, park guidance and current NPS notices.
The planner works without Gemini. Direct flight and hotel questions use the same adapters through chat.
Both providers accepted keyless searches during local verification. [Step 18](docs/step-18.md) covers
setup, limits, privacy, live provider checks and the evaluation procedure.

### Official park notices

The App → Park alerts page checks NPS notices for Zion, Grand Canyon and Yosemite without Gemini. Chat also gets
`get_park_alerts` beside the park knowledge tools. Put `NPS_API_KEY` only in ignored `.env.local`, then restart.
The example file keeps a blank placeholder. Without a key the checker explicitly says it is not configured;
mock tests require no credential. Results show fetch time, source links, cache status and incomplete checks.
Notices are fetched separately from RAG and do not establish that a trail is open or safe. See
[step 17](docs/step-17.md) for bounds, tests, freshness limits and preview validation.

### Park and trail preparation

Nimbus now includes official preparation guidance for Zion, Grand Canyon and Yosemite, with selected trails. The
agent resolves the destination, retrieves applicable source passages and combines them with the existing weather
tools. Source cards identify the documents and their dates. Stored guides do not establish current closures,
warnings, river levels or water availability. [Step 16](docs/step-16.md) explains the implementation and its limits.

One dedicated Qdrant collection, `nimbus_park_guidance_v3`, stores the public passages, provenance, native BM25 text,
384-dimensional MiniLM vectors and 96-dimensional ColBERT token vectors. BM25 statistics and both retrieval branches
use the same destination and season scope. Nimbus combines ranks, then Qdrant ColBERT reranks up to 12 admitted
passages before selecting at most four. Returned text must match a compact release catalog.
There is no SQLite database or local embedding inference in this path.

```bash
uv sync --locked
uv run python -m tools.build_park_index
uv run python -m tools.setup_park_search --reuse-collection nimbus_park_guidance_v2
uv run python -m tools.eval_park_hybrid --recording evals/park-retrieval-recording.json
```

The builder prepares reviewed source text in `data/parks/prepared.json`; its pinned tokenizer checks chunk size
without generating vectors. `data/parks/catalog.json` contains only destination and integrity metadata for runtime
validation. Migration copies verified existing MiniLM vectors and generates only the new ColBERT representation.
For a fresh cluster, omit `--reuse-collection`: setup generates each representation once per missing chunk.
Repeating setup verifies existing points and generates zero new embeddings. BM25 indexes text without embeddings.
Setup never runs at application startup and preserves the previous collection.

Put `QDRANT_URL` and `QDRANT_API_KEY` only in ignored `.env.local`. `PARKS_QDRANT_API_KEY` can supply a separate
credential, and `PARKS_QDRANT_COLLECTION` selects the dedicated park collection; it cannot be the private weather
cache collection. The defaults use Qdrant and hybrid retrieval. `PARKS_RETRIEVAL_MODE=lexical` requests only Qdrant
BM25. `PARKS_RERANK_ENABLED=false` retains hybrid RRF without ColBERT. `PARKS_ENABLED=false` disables park tools and
Playground execution. Gemini remains necessary for chat answers,
not source preparation or retrieval. The adapter sends the tool's search text, without attaching history or
preferences; Gemini may have worded that search using conversation context.

**Knowledge** opens Qdrant source documents, the chunk/vector explorer and the Retrieval Playground. The explorer
projects the actual stored Qdrant vectors. Playground questions use bounded POST bodies, never generated URLs.
Results distinguish native BM25/cosine scores, RRF ranks and ColBERT scores from the final order and selected context.
A dense-only failure can retain BM25; a reranker failure retains RRF. A catalog or BM25 failure is unavailable.
Activity's linked trace shows catalog, BM25, semantic, fusion and ColBERT outcomes without question or passage text.

The current 41-case comparison has zero provider failures and 100% evidence recall@4. Top-1 rose from the prior
78.9% (30/38) to 86.8% with scoped BM25, then 89.5% (34/38) with ColBERT. Some individual first ranks still regress;
this is not a 95% result. Eight separately frozen holdout cases all passed, with top-1 4/7 and recall 7/7.
The refreshed 47-case recorded replay checks routing, fusion, reranking and evidence without credentials; it does
not remeasure the live provider. See
[current retrieval evidence](docs/technical-details.md#scoped-bm25-and-colbert-validation).

Live-answer goldens separately check Gemini's behavior. `uv run python -m tools.eval_park_answers <address>` grades
whole answers for correctness, grounding and abstention, with safety questions as hard failures
([grading details](docs/technical-details.md#grade-park-answers-end-to-end)). Local and provider checks do not prove
Vercel readiness; follow [release verification](docs/waiting-on-you.md#qdrant-hybrid-park-retrieval).

The rebuild is complete: thirteen steps, each live and checked; a fourteenth reads the app's lines back onto its
Observability pages, and a fifteenth tells each request's story there. What's waiting on you is on
[its own page](docs/waiting-on-you.md); what could come next, on [To do](docs/todo.md).
