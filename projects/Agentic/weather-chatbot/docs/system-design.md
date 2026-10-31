# System Design

How Nimbus is built after step 3, drawn the way the TypeScript version's
[System design_deprecated](system-design_deprecated.md) was: as a common reference design for AI assistants draws an
online shop's assistant, in four bands, from the request's path at the top to running it in production at the bottom.
A number on a box is the reference's number for the part it plays (02 for the gateway, 09 for production operations);
**+** marks a part only Nimbus has. Step 1 laid the ground the assistant will stand on: the pages, the documentation
and the health check. Step 2 made the chat answer, streamed a word at a time. Step 3 put Gemini in place of step 2's
fixed answer, through LangChain; there's no tool yet, so this page shows only those. Each step adds its parts to it.
Below the diagram, each band is described, then each part of the reference is set against what Nimbus has so far.

![How Nimbus is built after step 3](images/system-design.svg)

## The four bands

### A · The online request path

1. **You**, in a browser, on a computer or a phone, open a page: the chat, the documentation, or this one; or ask the
   chat a question, whose answer, Gemini's, streams back a word at a time. There's no sign-in.
2. **Vercel's edge** (02) serves HTTPS and routes the request. It gives the request an id, `x-vercel-id`, which a
   client can't forge: sent with a request, it's replaced by Vercel's own (checked on the live site). Five files never
   reach the app: **Vercel's CDN** serves the stylesheet, the icon, htmx, its stream extension and our `chat.js` from
   `public/` itself, with the security headers `vercel.json` gives them.
3. **The app**, one Vercel Function (`/fastapi`, Python 3.13, in `iad1`, Washington, D.C.), runs `main.py`'s FastAPI
   app, which `create_app()` builds when the function starts. Band B follows a request through it.
4. **Your page** comes back as HTML from a Jinja2 template, as JSON from the health check, or, for a question, as the
   answer's stream: server-sent events of HTML, which htmx puts into the page. Each carries the security headers and
   the request's id in `x-request-id`.

### B · Controlled execution

Every request takes the same path through the app: the two middleware classes, outermost first, then FastAPI's
router. The only work done for a visitor is the chat's answer: one call to the model, with no tool yet.

- **The security headers** (`SecurityHeadersMiddleware`, outermost): on every response the app makes, an enforced
  Content Security Policy that allows only our own files; `nosniff`; `X-Frame-Options: DENY`; a referrer policy; and a
  permissions policy.
- **The request's context** (`RequestContextMiddleware`): the request id, Vercel's when it looks like one, else a new
  one, on every log line, on the response and in the request's state; and one line per request when it ends: the
  method, the path (never the query string), the status and the time.
- **The router** sends the request to one of five:
  - **the chat** (`chat.py`): `POST /api/chat`. First the form's checks: the type, at most 32 KiB, each field once,
    the question 1 to 2,000 characters, no field we don't know; a broken rule gets our own sentence and its status;
    and the browser's locale and time zone, which take the defaults when the chat can't use them. Then the answer, as
    server-sent events (`stream_turn()`, in an `EventStream`): your question and the answer, empty; each word as **the
    model** (07, below) writes it; then the finished answer, its Markdown made HTML. Stop ends it on the page; on
    Vercel the function writes the rest to no one, since Vercel's Python runtime never says the browser has gone; a
    failure shows the answer so far, our own sentence and its ref;
  - **the pages** (`pages.py`): the chat's page, the lists of pages and the 404 page, each a Jinja2 template, which
    escapes every value but two marked safe: a doc's Markdown, rendered with raw HTML off, and a menu label, escaped
    first, with the one `<wbr>` we add;
  - **the docs** (`docs.py`, **+**): Markdown rendered with raw HTML off, each page found by its address in a
    registry, never by a file path taken from the address;
  - **the health check** (`health.py`): `GET` and `HEAD /api/health`, the build and the time, never cached;
  - **the docs' pictures**, from `docs/images/`.

  A missing page gets the app's own 404 page; a missing API address gets JSON.
- **The model** (07): Gemini 3.5 Flash-Lite, through LangChain's `ChatGoogleGenerativeAI` (`model.py`), made once when
  the app starts, told its rules by the system prompt (`prompts.py`): no weather as fact without tools, weather only,
  short answers, the units for the visitor's locale, and their own today and tomorrow. Each answer is capped at 1,024
  tokens and 30 seconds; each call waits 20 s and is tried once more. Its failures, which LangChain raises as standard
  exceptions, become our own sentences: busy, too slow, not set up, or no answer.

### C · State and data freshness

- **No database and no sessions:** the app keeps nothing a visitor sends beyond its log lines, which hold a request's
  method and path (never the query string) and a question's length (never its text); it sets no cookie. The
  conversation is only on the page, and leaves with it.
- **Settings and secrets** are Vercel's environment variables, or `.env.local` on a computer, which git never sees;
  `config.py` is the only module that reads them, checked when the app starts. Vercel's own (the environment, the
  commit, the deployment) come from the real environment only. The app reads `LOG_LEVEL`, the Gemini key (a Sensitive
  variable) and model's name, and LangSmith's variables. The other keys set in Vercel for the TypeScript version
  (Apify's, Axiom's, Sentry's) wait for the steps that use them, all but Sentry's three build variables, which are to
  be deleted ([To do](todo.md)).
- **The docs** are Markdown in `docs/`, deployed with the function, each page read once by each copy of it.
- **The static files**, `public/static/`, are on Vercel's CDN, never in the function.

### D · Production operations

- **Observability** (09): JSON lines (structlog), on stdout, which Vercel's logs keep: one per request, and for each
  question, `chat.request` (its length) and how its answer ended, `chat.done`, `chat.aborted` or `chat.failed`, or
  `chat.rejected` with the broken rule's code; an answer's end holds its tokens and the model. Every line carries the
  request id, the environment, the commit and the deployment, so one search for an id finds a request's lines. The
  field names are the TypeScript version's (`requestId`, `deploymentId`), so the queries written for it still match.
  LangSmith traces each model run, with its timing and tokens, its inputs and outputs hidden.
- **Evaluation** (09): Ruff, mypy in strict mode, unit tests, and browser tests on every page and of the chat, with
  axe's accessibility checks, which CI runs on every push that touches the project; and a mutation check, which breaks
  each rule on purpose to show a test catches it, run before each commit.
- **Reliability and scale** (09): Vercel Functions start as many copies of the app as the traffic needs, each request,
  an answer's stream included, stopping at 300 s at most, Vercel's default (`vercel.json` sets no limit); the static
  files don't need the app at all.
- **Release and recovery** (09): every push to `main` deploys to production, side by side with CI, so a failing CI
  doesn't hold the deployment back. Any push means any: one that changes only another project in the repository
  deploys Nimbus again too, and the menu's build label then names that commit. Each step is tagged (`py-step-01`,
  `py-step-02`), Vercel can roll back to an earlier deployment, and the TypeScript version's code is kept in the tag
  `weather-chatbot-typescript-backup`.

## Compared with the reference

| The reference | Nimbus after step 2 | Why, or when |
|---|---|---|
| Shopper: web or mobile chat | You, in a browser, on a computer or a phone: Gemini answers, but can't check the weather yet | The weather tools come in step 4 |
| 02 · API gateway and identity: WAF, rate limits, sign-in | Vercel's edge: HTTPS, routing, and a request id it sets itself; the security headers on every response, the CDN's files included | The weather is public, so there's no sign-in. Rate limits come with the firewall's rules (step 11) |
| 01 · Input guardrails: injection, PII, scope | In part: the form's checks: its type, at most 32 KiB, each field once, the question 1 to 2,000 characters, a language tag and a known time zone, no field we don't know | Rules against prompt injection come in step 11 |
| 03 · Semantic cache: safe answers, by similarity | None | The weather changes by the hour, so a cached answer would go stale; step 7 caches the weather's data instead |
| 04 · Router and orchestrator: intent, step limits, time budgets | FastAPI's router; the chat's turn: one model call, streamed, capped at 1,024 tokens and 30 s, which Stop ends on the page (on Vercel, the function writes it to the end) | The agent comes in steps 4 and 5 |
| 01 · Output guardrails: safety, privacy, grounding | In part: Jinja2 escapes every value but the two marked safe; an answer's Markdown renders with no raw HTML and no pictures, its links in a new tab; the system prompt's rules; the page puts in only our own HTML, and our script only text; the policy runs only our own files | Grounding in the tools' results comes in step 4 |
| Answer: citations or a safe refusal | Gemini's answer, a word at a time; a polite refusal off the weather; our own sentence for each thing that can go wrong, a failure's with its ref | Citations come with the tools (step 4) |
| 05 · Retrieval (RAG) and its index | None | The weather will come live from tools, not from documents |
| 06 · Commerce tools: typed inputs, per-user permissions | None | The four weather tools come in step 4 |
| Commerce APIs and databases | None | |
| 07 · Model gateway: model choice, budgets, fallback | Gemini 3.5 Flash-Lite through LangChain (`model.py`): 1,024 tokens and 30 s an answer, 20 s and one retry a call; LangChain's standard exceptions mapped to our sentences | One model, no fallback yet |
| 08 · Human in the loop | None | |
| Knowledge ingestion, change events, index refresh | None | |
| Session store | None: the conversation is only on the page | From step 6, the browser sends it back with each question |
| Secure storage | Vercel's environment variables, read only by `config.py`; the Gemini key a Sensitive one, a `SecretStr` in the app, never logged | |
| 09 · Observability: traces, p95 latency, tokens, cost, alerts | JSON lines with the request's id and its build, in Vercel's logs: one per request, and how each answer ended, with its tokens; LangSmith's trace of each model run, its inputs and outputs hidden | Axiom, Sentry and the dashboards come in step 12 |
| 09 · Evaluation: golden set, safety tests, feedback | Unit, browser and accessibility tests in CI; a mutation check before each commit | |
| 09 · Reliability and scale: autoscaling, caps, queues, breakers | Vercel Functions, as many copies as the traffic needs; the CDN for the files; the chat's size limits | |
| 09 · Release and recovery: load tests, canary, rollback, backups | Every push to `main` deploys, side by side with CI; a tag per step; Vercel can roll back | CI doesn't gate the deployment, so a failure shows after it's live. No backups: Nimbus stores no data |

## What Nimbus has that the reference doesn't

- **Its documentation, inside the app** (**+**): a chapter for each step, this page, the issues log, the interview
  guide and the to-do list, written as the steps are built, from the same Markdown GitHub shows.
- **The TypeScript version's pages, kept:** at their old addresses with `_deprecated` added, under "Deprecated" in the
  menu.

## One request, end to end

A real question on the live site, on 31 October 2026 (commit d55f1ed): "Will it rain in Paris tomorrow?", posted
to `/api/chat` as the page's form posts it.

| Where | What happened |
|---|---|
| Vercel's edge, `cle1` (Cleveland) | Took the HTTPS request, gave it the id `cle1::lzdsv-1793423643867-12f0ae2ae59c`, and sent it to the function in `iad1` |
| `SecurityHeadersMiddleware`, `RequestContextMiddleware` | Wrapped the response's `send`, and took Vercel's id as the request's id, in the log context and the request's state |
| `chat.py`, `chat()` and `read_chat_request()` | Checked the form: its type, its length, its one field, the question's 31 characters; logged `chat.request` |
| `chat()`, then `EventStream` | Made the turn's first event, then sent it and the rest as they came: 50 events, the first 0.13 s after the question was sent, the last after 3.04 s |
| `stream_turn()` | Logged `chat.done`: the answer's 244 characters, in 2,917 ms |
| `RequestContextMiddleware` | Once the whole response had gone, wrote the request's line: `200`, in 2,919 ms |
| Vercel's edge | Passed each event on as it came, with the security headers and the request's id |

Searched for the id, Vercel's logs found its three lines, the question's text in none of them:

```json
{"questionChars": 31, "event": "chat.request", "level": "info", "ts": "2026-10-31T05:14:03.897637Z",
 "env": "production", "commit": "d55f1ed", "deploymentId": "dpl_8prm5Ay6L4X1SGizLAPNvnX6Fyod",
 "requestId": "cle1::lzdsv-1793423643867-12f0ae2ae59c"}
{"answerChars": 244, "ms": 2917, "event": "chat.done", "level": "info", "ts": "2026-10-31T05:14:06.814874Z",
 "env": "production", "commit": "d55f1ed", "deploymentId": "dpl_8prm5Ay6L4X1SGizLAPNvnX6Fyod",
 "requestId": "cle1::lzdsv-1793423643867-12f0ae2ae59c"}
{"method": "POST", "path": "/api/chat", "status": 200, "ms": 2919, "event": "http.request", "level": "info",
 "ts": "2026-10-31T05:14:06.815432Z", "env": "production", "commit": "d55f1ed",
 "deploymentId": "dpl_8prm5Ay6L4X1SGizLAPNvnX6Fyod", "requestId": "cle1::lzdsv-1793423643867-12f0ae2ae59c"}
```

[Step 1's chapter](step-1.md) explains each of these parts in its code, and [step 2's](step-2.md) the chat's.

## What comes next

Step 4 gives the model four weather tools, through a prebuilt LangGraph agent: the REST · no auth lane, which calls
Open-Meteo directly, adding the tools (06) and the weather's APIs to band B, and a chip for each tool call to the
answer. Each step after it adds its parts to this page and its diagram; the plan, `PLAN.md`, has them all.
