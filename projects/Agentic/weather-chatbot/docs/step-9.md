# Step 9 · Observability: Axiom, Sentry and the Health Check

**What this step built, so far:** most of step 9's first two parts. Every line our logger writes now also goes to
Axiom, which keeps it long past Vercel's hour, and searches it; every failure logged as an error goes to Sentry, with
its stack trace and nothing private; and `/api/health` says which lanes work, running nothing that costs. Next come
the lane picker's status dots, which read it; then part 3: the dashboards, alerts, traces and an uptime monitor.

## What you see

- **Nothing new on the page.**
- **In Axiom,** in the `weather-chatbot` dataset: each line our logger writes, soon after its request ends (not
  Next.js's own output, nor Vercel's line for each request). One request id finds a question's lines from both
  functions, `/api/chat` and `/api/mcp`:
  `['weather-chatbot'] | where requestId == "…"`. The ref an error's sentence ends with finds them too:
  `| where requestId endswith "7f3a9c01"`.
- **In Sentry,** in the `weather-chatbot` project: each failure logged as an error (a bug, the model failing, a broken
  contract or setting) as an issue, its stack trace pointing at our own code, tagged with its event, request id, ref,
  route, and lane or tool. A ref finds it: `ref:7f3a9c01`.
- **At `/api/health`:** which lanes work, as JSON, for the status dots and an uptime monitor: `200` when every lane
  that's on works, `503` when one doesn't. On a laptop, without Apify's token, it answered:

```json
{
  "status": "ok",
  "checkedAt": "2026-10-30T18:00:06.684Z",
  "checks": {
    "open-meteo": { "status": "ok", "ms": 874 },
    "our-mcp": { "status": "ok", "ms": 238 },
    "apify-rest": { "status": "off" },
    "apify-mcp": { "status": "off" }
  },
  "lanes": { "rest-no-auth": "ok", "mcp-no-auth": "ok", "rest-auth": "off", "mcp-auth": "off" }
}
```

## On the live site

Checked once `047a079` was live (entries 120 and 121): a question's lines, from both functions, in Axiom under its
request id, each at its own `ts`; and the build's source maps in Sentry, under the commit's release. Answers were slow
that hour, though, and the first question after the deploy failed: its connection to a cold `/api/mcp` took longer
than its 3 s budget. Bug story 18 tells how the causes were found: Sentry makes a cold start slower (about 2.4 s on a
laptop), and Gemini's free tier was slow that hour. Connecting to our MCP server now gets 6 s (entry 122): after that
went live (`b427de1`), the first question, both functions cold, connected in 4,164 ms and answered in 9.2 s, within
the new budget and past the old one. A lighter Sentry is on the To do page.

## How it works

### The lines, to Axiom

1. **Kept as they're written.** pino writes each line to stdout, as before, and to `lib/log-shipper.ts`, which keeps
   it.
2. **Sent at the request's end.** The route calls `flushLogs()`, which sends what's kept to Axiom in one request:
   pino's own lines, as NDJSON, with an API token that can only ingest into the dataset, to Axiom's US deployment
   (`us-east-1.aws.edge.axiom.co`), which takes each line's `ts` as its time.
   - **The chat** sends after its last line, its lane closed: `waitUntil` keeps the function alive until the batch has
     gone, even when the page has gone first (issue 101).
   - **The MCP server** sends once it has answered, and the tool's own line is in: it answers with plain JSON, once
     the tool has run, since our tools send nothing before their result (read in the MCP SDK's code, and tested).
3. **Never a failed request.** A batch has 2 s. One that Axiom refuses, or can't be reached for, is said on stderr
   (`axiom.failed`, with the status, never the token), which Vercel's logs keep, and dropped. Axiom's reply is read no
   further than its status, then let go, so its connection is free for the next batch (entry 119). At most 1,000 lines
   wait between batches; past that, lines are dropped and counted (`axiom.dropped`).
4. **Shared, not mixed.** One copy of the function serves many requests at once, so a batch can carry another
   request's lines too; each line keeps its own request id.
5. **No Axiom library.** The plan named `@axiomhq/js`, but it takes objects, so each line pino has just written would
   be parsed back, and it batches on its own timer, in a function Vercel may freeze between requests. One `fetch` of
   the lines as written does the same job (PLAN.md 9.1).

### The errors, to Sentry

1. **Started once.** `instrumentation.ts` starts Sentry when the server starts, with `lib/sentry.ts`'s settings.
   Without `SENTRY_DSN` (a laptop, CI, a preview), Sentry stays off.
2. **Errors only.** `logFailure()` sends Sentry each failure it logs at `error`, tagged as above; a warning (a timeout,
   a fallback) stays in the logs. An error Next.js catches in a request goes too (`onRequestError`).
3. **Nothing private.** Sentry 11 collects a lot unless told not to: IP addresses, cookies, headers, request and
   response bodies, query strings, AI prompts and answers, and a stack frame's variables. The chat's body holds the
   question, which we never log and which goes only to the model, so `lib/sentry.ts` turns each off (entry 114). No
   breadcrumbs either: our lines in Axiom tell what led up to an error. And Sentry's trace headers stay off our calls
   to Gemini, Open-Meteo and Apify (entry 115).
4. **Sent with the lines.** `flushLogs()` gives Sentry the same 2 s, at the same moment.
5. **Not yet:** traces (part 3), and the page's own errors, which would need the Content Security Policy to allow
   Sentry.

### Source maps, when Vercel builds the app

`next.config.ts` wraps the app's settings in Sentry's build step (`withSentryConfig`, from `@sentry/nextjs/config` in
Sentry 11: entry 113). With `SENTRY_AUTH_TOKEN`, which only Production's builds have, it uploads the source maps, so a
stack trace in Sentry points at our own TypeScript, then deletes them from the build; without it, no source maps are
made (entry 116). The release is the commit, which Sentry reads from Vercel.

The build step changes two more things. The build runs Sentry's own step after compiling, for a few seconds. And
Next.js's `clientTraceMetadata` experiment is on: Sentry turns it on for Next.js 15 and later, to put trace ids in the
HTML of a page made at request time, for Sentry in the browser. Our pages are built ahead, so nothing changes; the
build's output lists it.

### The health check, `/api/health`

1. **Four checks, at once, each within 8 s; none costs.**
   - **Open-Meteo:** geocodes London, with the cache skipped, so an outage shows.
   - **Our MCP server:** connects, and checks that it lists our four tools, as the MCP lanes do before an answer.
   - **Apify's REST door:** reads the account behind the token (`GET /v2/users/me`), which runs nothing.
   - **Apify's MCP server:** connects with the token, checks its tool list against our pin, and closes; no Actor runs.
2. **A lane works when every check its answers depend on passes.** `rest-no-auth` needs Open-Meteo; `mcp-no-auth`,
   our MCP server and Open-Meteo; `rest-auth`, Apify's REST door and Open-Meteo, which it geocodes with; `mcp-auth`,
   Apify's MCP server, our MCP server (its geocoding) and Open-Meteo. Without Apify's token, the auth lanes are off.
3. **`200` when every lane that's on works, `503` when one doesn't,** so an uptime monitor needs only the status code;
   the body names a failed check's class.
4. **At most one run a minute, per copy of the function.** A run's result answers every request that reaches that copy
   within a minute of the run's start, waiting for it if it's still going; Vercel may run several copies, each with
   its own. And Vercel's CDN keeps a `200` for a minute, so repeat requests stop at the edge, before any function; a
   `503` is never kept (entry 126). So an answer can be up to two minutes old.
5. **Its lines** go to Axiom like any request's: one `health.check` a check, at its class's level when it fails, and
   one `health.done`. A token Apify refuses is an `AuthError`, logged at error, so Sentry hears of it the first time a
   visitor or the monitor asks, before any user picks an auth lane (PLAN.md 5.5).
6. **Not quite the plan:** PLAN.md 9.5 had `mcp-no-auth` geocode London through our MCP server, with the cache
   skipped. Our server can't skip its cache for one caller without letting any caller skip it, so its check connects
   and reads the tool list, and Open-Meteo's own check stands for the geocoding.

### The settings

| Variable | What it's for | Set as |
|---|---|---|
| `AXIOM_TOKEN` | An Axiom API token that can only ingest into the dataset | Production, Sensitive |
| `AXIOM_DATASET` | The dataset's name: `weather-chatbot` | Production |
| `SENTRY_DSN` | Where Sentry's errors go | Production |
| `SENTRY_AUTH_TOKEN` | Uploads the source maps while Vercel builds the app | Production, Sensitive |
| `SENTRY_ORG`, `SENTRY_PROJECT` | Which Sentry project the source maps belong to | Production |

The lines go to Axiom only when both its token and its dataset are set. The address is Axiom's US deployment, where
this project's organisation is; one in the EU would change `AXIOM_INGEST_HOST` in `lib/constants.ts`.

## Not in this step yet

- **The status dots** in the lane picker, which read `/api/health` (next).
- **Part 3:** dashboards and alerts, in Axiom and Sentry; traces; an outside uptime monitor.
- **A Sentry event from the live site.** Nothing on the live site fails at `error` on demand: the first event comes
  with the first real error, or with step 10's forced `AuthError` (`CHAOS`), which plays out the rest of PLAN.md 5.5.
- **Previews:** the variables are set for Production only, so a preview's lines stay in Vercel's logs.

## The checks this step added

- **The shipper** (`tests/unit/log-shipper.test.ts`): the kept lines go in one batch, to the US ingest, as NDJSON,
  with the token; Axiom's reply is let go once its status is read; a batch Axiom refuses, or can't be reached for, is
  reported, never thrown, and never with the token; past the limit, lines are dropped and counted.
- **The logger** (`tests/unit/logger.test.ts`): a failure logged as an error goes to Sentry, with its tags; a warning
  doesn't; `flushLogs()` asks Sentry to send what it holds, within 2 s.
- **Sentry's settings** (`tests/unit/sentry.test.ts`): the DSN and the environment; nothing private, no breadcrumbs,
  no trace headers on our calls out.
- **The settings** (`tests/unit/config.test.ts`): Axiom only with both its token and its dataset.
- **The routes** (`tests/unit/app/api/chat/route.test.ts`, `tests/unit/app/api/mcp/route.test.ts`): each sends its
  lines once, after its last one: the chat's after the request's ending line, the MCP server's after the tool's.
- **The health check** (`tests/unit/health/check-lanes.test.ts`): every check at once; a lane down when a check it
  depends on fails, and off without Apify's token; a check past its time a timeout, at warn, and a refused token at
  error. Then the four real checks, against stand-ins: Open-Meteo asked itself each time, our MCP server in-process,
  and Apify's real 401 at both its doors.
- **The token checks** (`tests/unit/upstream/apify.test.ts`, `tests/unit/upstream/apify-mcp.test.ts`): `users/me`, the
  token in its header only and the account's details unread; Apify's MCP server connected, its pin checked, closed,
  and no tool called.
- **The health route** (`tests/unit/app/api/health/route.test.ts`): a `200` kept a minute at the CDN, a `503` never;
  one run a minute; and its lines sent once the run is done.
- **Each new test can fail:** 20 changes that break the code a test guards in part 1, and 14 in the health check,
  each caught by it.

## Files in this step

| File | What it does |
|---|---|
| `lib/log-shipper.ts` | Keeps each line, and sends them to Axiom in one batch |
| `lib/logger.ts` | Lines to stdout and to the shipper; errors to Sentry; `flushLogs()` |
| `lib/sentry.ts` | Sentry's settings: errors only, nothing private |
| `instrumentation.ts` | Starts Sentry when the server starts; Next.js's request errors to Sentry |
| `app/api/chat/route.ts`, `app/api/mcp/route.ts` | Each request's lines and errors sent at its end |
| `lib/config.ts`, `lib/constants.ts` | The new settings; Axiom's address, the 2 s and the 1,000 lines; the health check's place, 8 s and minute |
| `lib/health/check-lanes.ts` | The four checks, and each lane's status from the checks it depends on |
| `app/api/health/route.ts` | `GET /api/health`: `200` (kept a minute at the CDN) or `503`; one run a minute per copy |
| `lib/upstream/apify.ts`, `lib/upstream/apify-mcp.ts` | The token checks, which run nothing |
| `next.config.ts` | Sentry's build step: the source maps, with its token |
| `biome.json` | Sentry's `genAI` setting allowed by the naming rule (entry 117) |
| `.env.example` | The new variables' names, empty |
| `package.json` | `@sentry/nextjs` 11.8.0 |

`@sentry/nextjs` is pinned at 11.8.0, the newest release at least two weeks old when it was added: 11.10.0 was two
days old, and a release that young hasn't had time to be caught, if it's bad.

## Check it yourself

From `projects/Agentic/weather-chatbot`:

```bash
npm test
npm run build
```

On the live site, ask a question on `MCP · no auth`. Then, in Axiom's Query tab,
`['weather-chatbot'] | where event == "chat.request" | sort by _time desc | take 1` gives its request id, and
`['weather-chatbot'] | where requestId == "<that id>"` lists its lines from both functions. And
`curl -s https://weather-chatbot-hazel.vercel.app/api/health` says which lanes work.

## What's next

The lane picker's status dots, which read `/api/health`; then part 3: dashboards, alerts, traces and an uptime
monitor.
