# Step 9 · Observability: Axiom, Sentry and the Health Check

**What this step built, so far:** step 9's first two parts, and the traces of the third. Every line our logger writes
now also goes to Axiom, which keeps it long past Vercel's hour, and searches it; every failure logged as an error
goes to Sentry, with its stack trace and nothing private; `/api/health` says which lanes work, running nothing that
costs, and the lane picker shows it, a dot beside each lane; and every request is traced in Sentry, through both
functions, under its request id. The rest of part 3: the dashboards, the alerts and an uptime monitor.

## What you see

- **On the page,** each lane the deployment runs shows its health in the lane picker, a dot and words: *working*
  (green), *not answering* (red), and *checking…* or *status unknown* (grey).
- **In Axiom,** in the `weather-chatbot` dataset: each line our logger writes, soon after its request ends (not
  Next.js's own output, nor Vercel's line for each request). One request id finds a question's lines from both
  functions, `/api/chat` and `/api/mcp`:
  `['weather-chatbot'] | where requestId == "…"`. The ref an error's sentence ends with finds them too:
  `| where requestId endswith "7f3a9c01"`.
- **In Sentry,** in the `weather-chatbot` project: each failure logged as an error (a bug, the model failing, a broken
  contract or setting) as an issue, its stack trace pointing at our own code, tagged with its event, request id, ref,
  route, and lane or tool. A ref finds it: `ref:7f3a9c01`. And each request's trace: the route, each model step and
  tool call, and each call out, through `/api/mcp` too, its root span marked with the request id and ref.
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

Once `/api/health` was live (`41a54a6`), with Apify's token, all four checks passed; our MCP server's took 3,968 ms,
cold, as in bug story 18. A second request came from Vercel's CDN in 0.37 s (`x-vercel-cache: HIT`), and Vercel kept
`s-maxage` for itself, so a browser sees `public, max-age=0` (entry 127). Once the dots were live (`7cceecf`), the live
page, nothing mocked, showed all four lanes *working*, about 5 s after it opened, its `/api/health` answered afresh
after the deploy (entry 129).

Once the traces were live (`2ae5466`), a cold question's trace was found in Sentry by its ref, through both functions:
AI SDK's spans for the model's three steps and the two tool calls, and every call out with its address cut at the query;
no span held a `url.query`. The cold connection to our MCP server took 3,355 ms, within the 6 s (entry 134). Axiom's
lines from those deploys showed a bug: a health check run through a new deployment's own, protected address said the MCP
lanes were down, and its result could answer the live site's requests for a minute (bug story 19).

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
5. **Not yet:** the page's own errors, which would need the Content Security Policy to allow Sentry.

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
4. **At most one run a minute, per copy of the function and per address.** A run's result answers every request to
   the same address that reaches that copy within a minute of the run's start, waiting for it if it's still going;
   one address's result never answers for another's (bug story 19). Vercel may run several copies, each with its own.
   And Vercel's CDN keeps a `200` for a minute, so repeat requests stop at the edge, before any function; a `503` is
   never kept (entry 126). So an answer can be up to two minutes old.
5. **Its lines** go to Axiom like any request's, each naming the address its checks went through (`origin`): one
   `health.check`
   a check, at its class's level when it fails, and one `health.done`. A token Apify refuses is an `AuthError`, logged
   at error, so Sentry hears of it the first time a visitor or the monitor asks, before any user picks an auth lane
   (PLAN.md 5.5).
6. **Not quite the plan:** PLAN.md 9.5 had `mcp-no-auth` geocode London through our MCP server, with the cache
   skipped. Our server can't skip its cache for one caller without letting any caller skip it, so its check connects
   and reads the tool list, and Open-Meteo's own check stands for the geocoding.

### The traces, in Sentry

1. **Every request is traced,** while the traffic is this small (`tracesSampleRate: 1`): its route, AI SDK's span
   for each model step and tool call, and each call out, to Gemini, Open-Meteo, Apify and our MCP server.
2. **One trace through both functions.** Sentry's trace headers go to our own `/api/mcp` only, so the MCP server's
   spans join the chat's trace; Gemini, Open-Meteo and Apify still get none (entry 115).
3. **Found by the request id.** Each route marks its trace's root span with the request's id and ref (`markTrace()`
   in `lib/sentry.ts`), so one id finds the lines in Axiom, the trace and any error in Sentry: PLAN.md's "done when"
   for this step, but for its alert.
4. **Nothing private, in a span either.** AI SDK records neither the question, nor a tool's input or output, nor the
   answer (`CHAT_TELEMETRY`). And before a span is sent, every query string is cut from its name and attributes, and
   `url.query` dropped: Next.js's request span keeps the request's whole address, and a span's name can carry one,
   while Open-Meteo's geocoding address holds the place the user typed (entries 130 and 131). The cut runs in Sentry's
   `stream` lifecycle only, so that's pinned (entry 133).
5. **Why Sentry, not `@vercel/otel`:** the plan named `@vercel/otel`, whose default export goes to Vercel's own trace
   collector, which the Hobby plan doesn't have; Sentry, already in the app, takes the spans as they are.

### The status dots

1. **Asked when the page opens,** then every 5 minutes while it's open (`hooks/use-lane-status.ts`). A `503` carries
   the same answer, saying which lane is down. Until the first answer, each lane says *checking…*; an answer the page
   can't read leaves each *status unknown*.
2. **A dot and words** beside each lane the deployment runs: green and *working*, red and *not answering*, grey
   otherwise. The words say it, not the colour alone, and screen readers skip the dot.
3. **A lane not answering can still be picked:** its answer may fall back to its twin, or it may be back already.
4. **It can keep our MCP server warm, too:** when the page's ask makes `/api/health` run its checks (rather than the
   CDN answer), its connection to our MCP server wakes it, so a first question pays less of a cold start (bug story
   18). The chat's own function still starts cold.

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

## Dashboards and alerts, ready to set up

They live in your Axiom and Sentry accounts, so they're written out here, ready to paste. The Axiom queries run against
the lines this step ships; the answer-time, cache and health ones were run on the live lines on 30 October.

### An Axiom dashboard, `Nimbus`

**Answers per lane:**

```text
['weather-chatbot']
| where event == 'chat.done'
| summarize count() by bin_auto(_time), lane
```

**Answer time, p50 and p95, per lane** (PLAN.md 9.6's target: no-auth lanes under 6 s at p95):

```text
['weather-chatbot']
| where event == 'chat.done'
| summarize p50 = percentile(ms, 50), p95 = percentile(ms, 95) by bin_auto(_time), lane
```

**How answers end** (an answer can write `chat.failed` more than once, so this counts requests):

```text
['weather-chatbot']
| where event in ('chat.done', 'chat.failed', 'chat.aborted', 'budget.exceeded')
| summarize answers = dcount(requestId) by bin_auto(_time), event
```

**Tool calls by status, and the fallbacks:**

```text
['weather-chatbot']
| where event == 'tool.call' or event == 'lane.fallback'
| summarize count() by bin_auto(_time), event, status
```

**The cache's hit rate, per lane:**

```text
['weather-chatbot']
| where event == 'tool.call' and isnotempty(cache)
| summarize calls = count(), hits = countif(cache == 'hit') by lane
| extend hitRate = 100.0 * hits / calls
```

**Open-Meteo calls a day** (each try counts; its free limit is 10,000), **Apify runs a day, per door** ($0.005
each), and **tokens a day** (every step's, whether its answer finished or not):

```text
['weather-chatbot']
| where event == 'upstream.http' and upstream == 'open-meteo'
| summarize calls = sum(attempts) by bin(_time, 1d)
```

```text
['weather-chatbot']
| where route == '/api/chat'
| where (event == 'upstream.http' and upstream == 'apify') or (event == 'upstream.mcp' and tool == 'call-actor')
| summarize runs = count() by bin(_time, 1d), lane
```

```text
['weather-chatbot']
| where event == 'model.step'
| summarize sum(inputTokens), sum(outputTokens) by bin(_time, 1d)
```

**The live site's health,** by address, so a protected deployment's runs don't count (bug story 19):

```text
['weather-chatbot']
| where event == 'health.done'
| summarize runs = count(), down = countif(status == 'down') by origin
```

### Alerts, by email

| Where | Alert | When |
|---|---|---|
| Axiom monitor | The live site down | `['weather-chatbot'] \| where event == 'health.done' and status == 'down' and origin == 'https://weather-chatbot-hazel.vercel.app' \| summarize count()` above 0, checked every 5 minutes; it needs the uptime monitor, or visitors, to call `/api/health` |
| Axiom monitor | Answers slow | `['weather-chatbot'] \| where event == 'chat.done' and lane in ('rest-no-auth', 'mcp-no-auth') \| summarize answers = count(), p95 = percentile(ms, 95) \| where answers >= 5 \| summarize p95 = max(p95)` above 15,000 over 15 minutes, so one slow answer doesn't fire it: the target is 6 s, but Gemini's free tier has slow hours (bug story 18), so 6 s waits for the paid model (step 11) |
| Axiom monitor | Open-Meteo near its limit | `['weather-chatbot'] \| where event == 'upstream.http' and upstream == 'open-meteo' \| summarize sum(attempts)` above 7,000 over a day, 70% of its free 10,000 |
| Axiom monitor | Rate-limited | `['weather-chatbot'] \| where errorClass == 'UpstreamRateLimitedError' \| summarize count()` above 0 over 15 minutes: Open-Meteo limits by IP address too, and Vercel's are shared, so a `429` can come well before our own count says so |
| Axiom monitor | Apify's credit gone | `['weather-chatbot'] \| where errorClass == 'BudgetExceededError' \| summarize count()` above 0 over 15 minutes: Apify answered `402` to our token, and the auth lanes fall back |
| Axiom monitor | Fallbacks | `['weather-chatbot'] \| where event == 'lane.fallback' \| summarize count()` above 5 over 15 minutes |
| Sentry | High-priority issues | Already chosen when the project was made: Sentry's default alert emails each high-priority issue. Sentry starts an error-level event high on the free plan; on a Business or trial plan it also weighs whether the error was handled, and ours all are, so add a rule that ignores priority there: "A new issue is created" or "A resolved issue regresses", then email. Check the rule is listed under Alerts |
| Sentry | `Apify: AuthError` | A new issue alert: when "an event or issue activity is captured" whose `exception.type` equals `AuthError`, email (PLAN.md 5.5), at most once a day for an issue: each health run that meets a refused token sends two, one from each Apify check |
| Uptime monitor | `/api/health` | UptimeRobot or Better Stack, on a free plan: `https://weather-chatbot-hazel.vercel.app/api/health` every 5 minutes, alerting on anything but `200` |

## Not in this step yet

- **The rest of part 3, set up:** the dashboards and alerts above, and an outside uptime monitor, which need your
  accounts (the To do page).
- **Alerts that wait for real traffic to set their thresholds:** `UpstreamTimeoutError` over 5% of calls in 10
  minutes, `UpstreamUnavailableError` lasting 5 minutes (the live site's health alert covers most of it), and
  `BotBlockedError` spikes (BotID is off).
- **Not measured yet:** the time to the first token (PLAN.md 9.6's target is 2.5 s, but nothing logs it); Apify's
  credit at 80% (about 800 runs a month, of its $5); and the model's spend at 80%, which waits for the paid model
  (step 11).
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
  one run a minute, for each address; and its lines sent once the run is done.
- **The dots** (`tests/unit/utils.test.ts`, `tests/e2e/chat-page.spec.ts`): `toLaneHealths` reads each lane's
  health from the answer, a `503`'s too, and says unknown for anything it can't read; in the browser, a working lane's
  green dot and words, a lane not answering in red and still enabled, and an answer the page can't read leaving each
  unknown. The browser tests answer `/api/health` themselves, so none calls Open-Meteo or Apify.
- **The traces** (`tests/unit/sentry.test.ts`, `tests/unit/utils.test.ts`, `tests/unit/constants.test.ts`): every
  request traced; trace headers to our own `/api/mcp` and to nothing else we call; a span's query strings cut and
  `url.query` dropped, a question mark that starts no query left, the lifecycle that runs the cut pinned; the trace
  marked with the id and ref; and the chat's telemetry recording no input or output.
- **Each new test can fail:** 20 changes that break the code a test guards in part 1, 17 in the health check, 5 in the
  dots and 9 in the traces, each caught by it.

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
| `app/api/health/route.ts` | `GET /api/health`: `200` (kept a minute at the CDN) or `503`; one run a minute per copy and address |
| `lib/upstream/apify.ts`, `lib/upstream/apify-mcp.ts` | The token checks, which run nothing |
| `hooks/use-lane-status.ts` | Asks `/api/health` for the dots: when the page opens, then every 5 minutes |
| `components/lane-picker.tsx`, `components/chat-window.tsx` | Each lane's dot and words |
| `lib/utils.ts`, `lib/types.ts` | `toLaneHealths()`, and `LaneHealth` |
| `app/globals.css` | The dots: green, red, grey |
| `lib/sentry.ts`, `lib/utils.ts` | Traces: every request, headers to our MCP server only, query strings cut; `markTrace()` |
| `lib/chat/run-chat.ts`, `lib/constants.ts` | AI SDK's spans, recording no input or output (`CHAT_TELEMETRY`) |
| `app/api/chat/route.ts`, `app/api/mcp/route.ts`, `app/api/health/route.ts` | Each marks its trace with the request id |
| `biome.json` | Sentry's own span fields, in snake_case, allowed in `lib/sentry.ts` and its test |
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
`curl -s https://weather-chatbot-hazel.vercel.app/api/health` says which lanes work, and the live page shows the same
beside each lane.

## What's next

Setting up the dashboards, the alerts and the uptime monitor, above, in your accounts; then step 10: the evals, the
failure tests and the load test.
