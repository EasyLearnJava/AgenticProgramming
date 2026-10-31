# Plan: Nimbus, Rebuilt in Python

Nimbus is a weather chatbot: ask about the weather anywhere, and see each tool call behind the answer and the lane it
took. Its first version was built in TypeScript (Next.js and AI SDK); this plan rebuilds it in Python, as a
production-grade app and a tutorial at once: thirteen steps, each one adding one idea, each ending deployed and
working, and each with a chapter written while it's built. The first version's plan is kept as
[PLAN_deprecated.md](PLAN_deprecated.md).

## 1. The stack

| Layer | Choice |
|---|---|
| Language | Python 3.13, async throughout |
| Packages | uv: `pyproject.toml` and `uv.lock`, exact versions |
| Web framework | FastAPI; Uvicorn on a computer |
| Pages | Jinja2 templates; HTMX with its server-sent-events extension (from step 2); plain CSS |
| Markdown | markdown-it-py, raw HTML off: the answers and the docs |
| Agent | LangGraph (from step 4) |
| Model | Gemini, through `langchain-google-genai` (from step 3) |
| Tools | LangChain tools with Pydantic inputs; `httpx2` for the calls out, `tenacity` for retries |
| MCP | The official `mcp` SDK (FastMCP) for our server; `langchain-mcp-adapters` for the MCP lanes |
| Settings | pydantic-settings: one module reads the environment |
| State between requests | No database: each chat stays in the browser, sent back with every question (step 6); Open-Meteo's answers in Vercel's Runtime Cache, through the `vercel` package (step 7) |
| Logs | structlog, JSON lines with a request id; Axiom (from step 12) |
| Errors, traces | Sentry; LangSmith for the agent's runs (from step 4) |
| Tests | pytest; Playwright for Python with axe; mutation checks |
| Lint, types | Ruff; mypy in strict mode |
| CI, hosting | GitHub Actions with uv; Vercel's Python runtime |

Why no database: Vercel runs many copies of the app, which share no memory, so whatever must last from one request to
the next lives outside them. The conversation lives in the visitor's browser, so nothing a visitor types is ever
stored on our side; the weather lives in Vercel's Runtime Cache. A database would pay off with accounts, or with runs
that pause for a person's approval (LangGraph's checkpoints); neither is planned.

## 2. The roadmap

| Step | What it builds | What you do |
|---|---|---|
| 1 | The project: uv, FastAPI, Ruff, mypy, pytest, CI, the first deploy; the page shell in Jinja2; the docs, the deprecated ones included, and the System design page; security headers; JSON logs with a request id | Switch the Framework Preset to FastAPI (done); delete the three `SENTRY_AUTH_TOKEN`/`ORG`/`PROJECT` variables |
| 2 | The chat streams a fixed answer over server-sent events with HTMX; Stop; our own error sentences | |
| 3 | Gemini through LangChain, streamed; the system prompt; the input rules | |
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
| A boolean | `is_...` or `has_...` | `is_deprecated` |
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

Its pages are kept, each renamed `*_deprecated` and served at its old address with the suffix
(`/docs_deprecated/step-3_deprecated`, `/issues_deprecated`), until you say to remove them. Its code is in the git tag
`weather-chatbot-typescript-backup`, deleted once the rebuild is complete; the code stays in the repository's history.
