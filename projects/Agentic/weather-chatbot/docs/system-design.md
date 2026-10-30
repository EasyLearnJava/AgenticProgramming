# System Design

How Nimbus is built today, after steps 1 to 7, drawn the way a common reference design for AI assistants draws an
online shop's assistant: in four bands, from the request's path at the top to running it in production at the bottom.
A number on a box is the reference's number for the part it plays (01 for the guardrails, 04 for the orchestrator,
and so on); **+** marks a part only Nimbus has. Below the diagram, each band is described, then each part of the
reference is set against what Nimbus has, or why it doesn't.

<!-- the diagram -->

## The four bands

### A · The online request path

1. **You**, in the chat page (Next.js and AI SDK's `useChat`), pick a lane and ask. The page sends your question, with
   the recent messages, your browser's locale and its time zone, to `POST /api/chat`.
2. **Vercel's edge** serves HTTPS and routes the request to the chat function. Its id for the request, `x-vercel-id`,
   becomes our request id. There's no sign-in: the weather is public.
3. **01 · The input rules** (`lib/chat/chat-request.ts`) check the body before anything runs: at most 20 messages, each
   of yours at most 2,000 characters, the whole history at most 200,000, only the parts the page sends, a lane this
   deployment runs, a real language tag and time zone, a chat id of the kind the page makes. A broken rule gets its own
   sentence, with `400`.
4. **04 · The chat turn** (`app/api/chat/route.ts`, `lib/chat/run-chat.ts`) is the orchestrator. It opens the lane you
   picked and runs AI SDK's `streamText`: the system prompt, the lane's tools (four, or two on the auth lanes), at
   most 5 steps (the last can only write), and time budgets (50 s for the answer, 10 s for the model's first chunk, 8 s
   a tool call, 28 s for the Actor's on REST, 33 s on MCP). Stop cancels it.
   The model chooses the tools; you chose the lane.
5. **Your answer** streams back as it's written, with a chip for each tool call (open one to see its request on the
   wire) and a weather card. A failure shows our own sentence, never the error's text; when it's logged as an error,
   the sentence ends with its ref.

The same edge also serves **the nearby city** (`GET /api/nearby-city`: a city near you, from Vercel's location
headers, for one suggested question) and **the pages** (`/docs`, `/issues`, this one), which are static.

### B · Controlled execution

- **REST · no auth**: the four tools run inside `/api/chat` and call Open-Meteo themselves.
- **MCP · no auth**, the default lane: the chat turn is an MCP client (`@ai-sdk/mcp`). It connects to **our own MCP
  server** at `/api/mcp` within 6 s, sends the request id as `x-request-id`, and calls the tools there. The server
  (`mcp-handler`) takes one JSON-RPC message of at most 8 KB per request, and is public: any MCP client can use it.
- **REST · with auth**: geocoding as on `REST · no auth`, and the Actor's forecast tool, which runs Apify's
  Open-Meteo Weather Forecast Actor through Apify's REST API, with our token in the `Authorization` header. When
  Apify can't answer, the tool asks `REST · no auth` for the same forecast, and its chip says so.
- **MCP · with auth**: geocoding through our MCP server, as on `MCP · no auth`, and the same Actor tool, whose run
  goes through Apify's MCP server, `mcp.apify.com`, with the token. When Apify can't answer, our server's
  `get_forecast` answers instead, and the chip says so.
- **The Apify clients**: for REST (`lib/upstream/apify.ts`), one `POST` to the Actor's run-sync address, with its
  build, 18 s and $0.01 pinned in the URL; for MCP (`lib/upstream/apify-mcp.ts`), two `tools/call` messages, since a
  run's answer holds its ids: `call-actor`, with the same build, 18 s and $0.01, then `get-dataset-items`. Neither
  retries or caches, since a run costs money and the fallback answers anyway. **The Actor** answers with an item a
  day, or an hour, in °C, read by `lib/weather/actor-items.ts`; a run costs $0.005.
- **06 · The four weather tools** (`lib/weather/tools/`): `geocode_location`, `get_current_weather`, `get_forecast`
  and `get_air_quality`, written once, with Zod input schemas, read-only, and run by both doors.
- **The Open-Meteo client** (`lib/upstream/open-meteo.ts`): 3 s a try and one retry, `Retry-After` on a `429`,
  coordinates rounded to about 1 km, and the place's own time zone. Open-Meteo's APIs are free and need no key.
- **07 · The model** (`lib/chat/model.ts`): Gemini 3.5 Flash-Lite through `@ai-sdk/google`, with the key from the
  environment. AI SDK retries a failed call twice; an answer is at most 2,000 tokens. There's one model, so no
  fallback yet.

### C · State and data freshness

- **The conversation** lives in your browser tab, in `useChat`. Each question sends the recent messages; no server
  keeps a chat.
- **Settings and secrets** are Vercel's environment variables, and `lib/config.ts` is the only file that reads them.
  The Gemini key and Apify's token are Secret variables (Vercel's "Sensitive" until lately), which can't be read
  back from the dashboard.
- **Vercel's Runtime Cache** keeps Open-Meteo's answers by their exact request, for 30 days (places), 10 minutes (the
  weather now) and 30 minutes (forecasts and air quality). The no-auth lanes share it, and a chip says when it
  answered. Apify's runs are never cached: each one costs money.
- **The docs** are Markdown in the repository, built into static pages with each deployment.

### D · Production operations

- **Observability**: one JSON line per event (pino), in Vercel's logs and in Axiom, which gets each request's lines
  in one batch at its end. Every line carries the request id, so one search finds a question's lines in `/api/chat`
  and in `/api/mcp` (step 5). Every failure logged as an error also goes to Sentry, tagged with its request id, with
  nothing private; `/api/health` checks each lane's ways out, running nothing that costs, which the lane picker's
  status dots show; and each request is traced in Sentry, through both functions, under its id (step 9).
- **Evaluation**: the golden questions, asked on the live site through each lane (`npm run evals`), the MCP server's
  own check, and the unit, browser and accessibility tests that CI runs on every push.
- **Reliability and scale**: Vercel Functions start as many copies as the traffic needs, each stopping at 60 s; the
  time budgets, the retries and the MCP server's request guard keep one slow part from holding up the rest.
- **Release and recovery**: a push to `main` runs CI and deploys to production, side by side, so a failing CI doesn't
  hold the deployment back; any other branch gets a preview. Vercel can roll back to an earlier deployment.

## Compared with the reference

| The reference | Nimbus today | Why, or when |
|---|---|---|
| Shopper: web or mobile chat | You, in the chat page, on a computer or a phone | |
| 02 · API gateway and identity: WAF, rate limits, sign-in | Vercel's edge: HTTPS, routing, a request id; Deployment Protection on previews | The weather is public, so there's no sign-in. A WAF rate limit and BotID come in step 8 |
| 01 · Input guardrails: injection, PII, scope | The input rules (`lib/chat/chat-request.ts`) | No PII scrubbing: the question is never stored or logged, but it goes to Gemini as typed, as the note under the input box says |
| 03 · Semantic cache: safe answers, by similarity | None for answers | The weather changes by the hour, so a cached answer would go stale. Open-Meteo's answers are cached instead, by their exact request (band C) |
| 04 · Router and orchestrator: intent, step limits, time budgets | The chat turn: AI SDK's `streamText`, at most 5 steps, with time budgets | You choose the lane; the model chooses the tools |
| 01 · Output guardrails: safety, privacy, grounding | In part: the system prompt's rule to answer only from tool results; our own sentences for errors; Markdown without images or raw HTML | Nothing checks an answer before it streams; the golden questions check grounding on the live site |
| Answer: citations or a safe refusal | The answer, streamed, with a chip per tool call and a weather card | The chips are the citations: each opens to its request |
| 05 · Retrieval (RAG) and its index | None | The weather comes live from tools, not from documents |
| 06 · Commerce tools: typed inputs, per-user permissions | The four weather tools, and on `REST · with auth` the Actor's: typed with Zod, read-only | Nothing writes, so nothing needs approving |
| Commerce APIs and databases | Open-Meteo's geocoding, forecast and air-quality APIs; Apify's Actor, which calls Open-Meteo too | Open-Meteo is free, with no key; Apify takes our token and charges per run. They see the places asked about (a pinned location, to about 1 km), never who asked: our servers call them |
| 07 · Model gateway: model choice, budgets, fallback | `lib/chat/model.ts`: Gemini through `@ai-sdk/google`; AI SDK's two retries; 2,000 tokens out | One model; a paid key or Vercel AI Gateway, and a fallback, before launch (step 11) |
| 08 · Human in the loop | None | The bot only reads the weather: nothing is high-risk enough to need a person |
| Knowledge ingestion, change events, index refresh | None | No documents to ingest; cached answers expire by themselves |
| Session store | Your browser tab | No server keeps a chat |
| Secure storage | Vercel's environment variables, the Gemini key and Apify's token Secret ones | Only `lib/config.ts` reads them; nothing secret reaches the browser |
| 09 · Observability: traces, p95 latency, tokens, cost, alerts | Log lines with a request id across both functions, kept in Axiom; levels from the error map, tokens per step; errors in Sentry; a health check per lane, shown as the lane picker's dots; a trace per request | Dashboards and alerts in step 9; cost with the paid model (step 11) |
| 09 · Evaluation: golden set, safety tests, feedback | The golden questions on each lane, live; unit, browser and accessibility tests in CI | Failure tests and a lane-by-lane report in step 10 |
| 09 · Reliability and scale: autoscaling, caps, queues, breakers | Vercel Functions, time budgets, retries, the MCP request guard | Rate limits in step 8, a load test in step 10. No queue: each answer is one request |
| 09 · Release and recovery: load tests, canary, rollback, backups | Each push runs CI and deploys, side by side; Vercel can roll back | CI doesn't gate the deployment, so a failure shows after it's live. A load test in step 10. No backups: Nimbus stores no data |

## What Nimbus has that the reference doesn't

- **Its own MCP server** (**+**): the four tools at `/api/mcp`, for the chat and for any MCP client, behind a guard
  that takes one message of at most 8 KB at a time.
- **Four doors to the same data**: REST or MCP, without or with auth. All four are live; the compare view shows one call
  through all four.
- **The wire view**: each chip opens to the request as it was sent, so you can see which door a call went through.

## One question, end to end

A real answer on the live site, on 29 October 2026, through `MCP · no auth`: "What will the weather be like in Lyon
tomorrow?". Every line it logged carries the same request id, `cle1::jnxr9-1793313250023-c454c392268a`, which is
Vercel's own id for the request. A search for it in Vercel's logs finds them all.

| After | Function | Line | What it says |
|---|---|---|---|
| 0 ms | `/api/chat` | `chat.request` | one message, a question of 47 characters (never its text) |
| 1,108 ms | `/api/chat` | `lane.connect` | connected to our MCP server, and listed its 4 tools, in 1,107 ms |
| 2,259 ms | `/api/mcp` | `upstream.http` | geocoding answered `200` in 435 ms, first try |
| 2,268 ms | `/api/mcp` | `mcp.call` | `geocode_location`, in 470 ms; the cache didn't have it |
| 2,278 ms | `/api/chat` | `tool.call` | `geocode_location`, in 514 ms, seen from the chat |
| 2,282 ms | `/api/chat` | `model.step` | step 0: 1,257 tokens in, 16 out, one tool call |
| 3,247 ms | `/api/mcp` | `upstream.http` | the forecast answered `200` in 394 ms |
| 3,255 ms | `/api/mcp` | `mcp.call` | `get_forecast`, in 406 ms |
| 3,262 ms | `/api/chat` | `tool.call` | `get_forecast`, in 428 ms |
| 3,263 ms | `/api/chat` | `model.step` | step 1: 1,633 tokens in, 46 out, one tool call |
| 3,998 ms | `/api/chat` | `model.step` | step 2: 1,957 tokens in, 47 out, the answer itself |
| 4,001 ms | `/api/chat` | `chat.done` | 3 steps, 2 tool calls, 4,847 tokens in, 109 out |

The two lines for each tool call show the MCP hop: our MCP server took 470 ms for the geocoding, of which Open-Meteo
took 435 ms; the chat saw 514 ms. Connecting took 1.1 s, the first connection after a deployment.

## What comes next

Step 8 added the security headers and a bot check, switched off for now; the firewall's rate limit waits on its rules
(A, 02). Step 9 has begun: the lines go to Axiom, the errors to Sentry, and `/api/health` checks each lane, shown as the
picker's dots, and each request is traced; dashboards and alerts come next (D). Step 10 adds the failure tests, and with
them the cached answer when Open-Meteo is down (C). Step 11 brings a paid model path, with its cost in the logs (B, 07).
The plan, `PLAN.md`, has the details.
