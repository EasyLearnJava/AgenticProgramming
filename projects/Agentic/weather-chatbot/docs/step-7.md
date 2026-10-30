# Step 7 · MCP · With Auth, Through Apify's MCP Server

**What this step built:** the fourth lane, `MCP · with auth`. Its forecasts come from the same Apify Actor as
`REST · with auth`, with the same token, but through Apify's MCP server, `mcp.apify.com`, so the chat route is an MCP
client of a server that isn't ours. Finding the place is our MCP server's geocoding, as on `MCP · no auth`. When Apify
can't answer, the lane asks `MCP · no auth` for the same forecast, and the chip says so. All four lanes are now built.

## What you see

- **In the picker,** `MCP · with auth` is live on a deployment that has Apify's token, and says "needs an Apify
  token", switched off, on one that doesn't, like `REST · with auth`. The compare view says the same.
- **Its forecast chip** is the same Actor tool as `REST · with auth`, `gochujang--open-meteo-weather-forecast`.
  Opened, it shows a JSON-RPC `tools/call` of Apify's `call-actor`, to
  `https://mcp.apify.com/?tools=call-actor,gochujang/open-meteo-weather-forecast`, with
  `authorization: Bearer <APIFY_TOKEN>` and `mcp-session-id: <session id>`: both masked.
- **Its geocoding chip** says `MCP · with auth` and our own host: geocoding goes through our MCP server.
- **When Apify can't answer,** the forecast chip's line says why, as on `REST · with auth`, and its lane says
  `MCP · no auth`: the forecast came through our MCP server instead.

## How it works

### One call, the fourth way

The lane's code marks the six points every lane has (PLAN.md 4.3):

1. **Where:** Apify's MCP server, `https://mcp.apify.com/?tools=call-actor,gochujang/open-meteo-weather-forecast`,
   which lists only `call-actor`, the Actor's own tool and four helpers; and our own MCP server, `/api/mcp`, for
   geocoding and the fallback.
2. **Auth:** `Authorization: Bearer` with `APIFY_TOKEN` on every request to Apify's server; none to ours.
3. **Tools:** our geocoding, through our server, and the same Actor tool as `REST · with auth`: the auth pair shares
   it, so the model is asked the same thing on both (rule 9).
4. **The call:** two `tools/call` messages to Apify's server (below): `call-actor`, which runs the Actor with the REST
   door's build, 18 s and $0.01, and waits up to 18 s for it; then `get-dataset-items`, which reads the run's items, up
   to 100 in one read.
5. **The result:** the same items as the REST door's, read by the same `lib/weather/actor-items.ts`.
6. **Clean-up:** both connections are closed however the answer ends; Apify's only if a run opened it, waiting at most
   1 s for it, since its session's `DELETE` has no time limit of AI SDK's (entry 93). The Actor's tool gets 33 s: the
   run's 20, as on `REST · with auth`, and 5 for the first forecast's handshake, then the fallback's 8.

### Two messages, because a run's answer holds ids

Apify's MCP server answers a run with the run's status and its storages' ids, not its data, whichever tool runs it.
Its own source shows it: the answer `call-actor` gives, its `RunResponse` (`src/tools/actors/actor_run_response.ts` in
`apify/apify-mcp-server`), has the run's status and storages and no items. So a forecast takes a second message,
`get-dataset-items` with the run's dataset id, whose answer holds the items; the lane asks for up to 100, more than an
hourly forecast's 72, and refuses a dataset that holds more than one read gives (issues log, entry 89).

### The handshake, once, on the first forecast

Apify's server speaks MCP's 2025 version, with sessions: its `401` exposes `Mcp-Session-Id`. So the lane skips the
2026 version's discovery, which AI SDK's client would otherwise try first, and opens with `initialize` and
`tools/list` (entry 91). It does that on the first forecast, not when the lane opens: a question that needs no
forecast never pays for it, and a second forecast in the same answer reuses it. The tool list is checked once, our pin
(PLAN.md 7.4): `call-actor` must be there, taking the Actor, its input, `waitSecs` and the three limits inside
`callOptions`, since Apify's server drops a key it doesn't know without a word (entry 94); the Actor's own tool,
taking `locations`, `forecastDays` and `mode`; and `get-dataset-items`. Nothing is retried: a retried run would be a
second, paid one. Connecting may take 5 s, so on this lane the Actor's call has 25 s, the run's 20 and those 5, where
`REST · with auth` has 20 (entry 92). Apify's server can also wait up to 5 s after a run succeeds, for the run's
dataset to show its items (entry 98). At the live check's speeds, an 18-second run and that wait would take about 24
to 25 of those 25 s: they only just fit, and a slower start or handshake makes such a run fall back.

### The same limits as the REST door, through `call-actor`

The REST door pins the Actor's build, 18 s and $0.01 in the URL. The Actor's own tool on Apify's server takes none of
them, only `waitSecs`, how long the server waits for the run: a run through it would use the Actor's default build,
with no cap on its charge. Apify's `call-actor` takes all three in its `callOptions` and starts the run with them, so
the lane runs the Actor through it: `build: "1.0.9"`, `timeout: 18` and `maxTotalChargeUsd: 0.01`, from the same
constants as the REST URL, with `waitSecs: 18`. A test holds the twin doors to it: the compare view's two auth
requests must carry the same three values (entry 90, and bug story 14).

One difference stays. Before it runs build 1.0.9, `call-actor` checks our input against the Actor's input schema as
its default build has it, and our pin reads that same schema, from the Actor's own tool. So a new default build that
changes the Actor's input would make this lane fall back, saying so, while `REST · with auth` keeps running 1.0.9.

### Falling back

The same as on `REST · with auth`, from one shared function, `toActorTool()` in `lib/lanes/lane.ts`: only the Apify
client and the twin differ. A failure is logged once, as `lane.fallback`, and the twin, our server's `get_forecast`,
answers in the tool's last 8 s; Stop and the answer's own budget end both, and with under 12 s of the answer left,
nothing falls back (step 6's bug story 10, and issue 82).

| What happened | Class | The chip says |
|---|---|---|
| Apify doesn't accept the token: `401` (a `WWW-Authenticate` header, here) or `403` | `AuthError` | "Apify didn't accept our token" |
| `402`, or an error result that says the account can't pay | `BudgetExceededError` | "Apify's credit for this month is used up" |
| The run still going after 18 s, or past the call's 25 s | `UpstreamTimeoutError` | "Apify took too long" |
| The run failed, a `5xx`, or no answer | `UpstreamUnavailableError` | "Apify can't be reached" |
| A tool list without our pin, another answer shape, or another error result | `ContractError` | "Apify answered in a way we didn't expect" |

An error result's text isn't kept, since it can quote the input; which words mean "can't pay" is our reading, as
Apify's MCP server doesn't document them (entry 90).

### The lines a forecast writes

`lane.connect`, with `host: "mcp.apify.com"`, the first time; then one `upstream.mcp` line for each message, with its
tool, status and time; and, when it falls back, `lane.fallback`. No line holds the token.

## Not in this step

- **The daily contract check** of Apify's tool list against our pin comes with the failure tests (step 10); until
  then, a changed list falls back, saying so.
- **The failure case of PLAN.md 5.5 on a preview**, with a broken token, needs the `CHAOS` setting (step 10): previews
  have no token, and the token is yours to change. The tests play it with Apify MCP's real `401`.
- **The alert and the lanes' status dots** come with observability (step 9); **OAuth**, a user's own Apify account,
  with step 12.

## The checks this step added

- **The Apify MCP client** (`tests/unit/upstream/apify-mcp.test.ts`): a run as two messages, `call-actor` with the
  Actor's input, `waitSecs` and the REST door's limits, then every item; the request recorded with the token and the
  session's id masked; one connection for two runs; Apify MCP's real `401`, through AI SDK's own client, as
  `AuthError`, met again without reconnecting; the pin, for each of its tools and the limits inside `callOptions`; a
  run still going, failed, or in another shape; error results; too many items; past the budget; Stop; closing, within
  its 1 s even when Apify never answers.
- **The twin doors** (`tests/unit/chat/lane-examples.test.ts`): the auth pair's requests carry the same tool, Actor
  input and limits, in the REST URL and in `call-actor`'s `callOptions`; and, since the live check, both MCP doors'
  requests carry the `user-agent` that AI SDK's real client sends, with the deployment's Node version (entry 97).
- **The lane** (`tests/unit/lanes/mcp-auth.test.ts`): its two tools and 33 s; geocoding through our server, as this
  lane's call, with Apify not asked; a forecast through Apify's server; the fallback to our server's `get_forecast`
  when Apify rejects the token, with the chip's sentence and one `lane.fallback` line.
- **The helpers** now shared by both MCP lanes (`tests/unit/utils.test.ts`): a request as the wire view shows it, an
  MCP call's request, a result's text, an error's HTTP status, a check's field names.
- **In the browser** (`tests/e2e/chat-page.spec.ts`): both auth lanes live with the token, or waiting for one; the
  compare view's `MCP · with auth` cell, the request to Apify's server with the token masked.

## Files in this step

| File | What it does |
|---|---|
| `lib/upstream/apify-mcp.ts` | The Actor through Apify's MCP server: the connection, the pin, the two messages, each failure as our class |
| `lib/lanes/mcp-auth.ts` | `MCP · with auth`: our server for geocoding and the fallback, Apify's for the Actor |
| `lib/lanes/lane.ts` | `toActorTool()`: the auth lanes' Actor tool and its fallback, shared by both doors |
| `lib/lanes/mcp-no-auth.ts`, `lib/lanes/rest-auth.ts`, `lib/lanes/open-lane.ts` | Our server's connection and tool calls, exported; the REST lane on the shared tool; the fourth opener |
| `lib/utils.ts`, `lib/types.ts`, `lib/constants.ts` | The shared request and result helpers; `McpClient` and the fourth lane; Apify's MCP address and limits |
| `lib/chat/lane-examples.ts`, `lib/chat/chat-request.ts` | The compare view's real request to Apify's server; the rule's sentence for an unknown lane |
| `tests/stubs/apify-stand-ins.ts`, `tests/fixtures/apify/mcp-401-no-token.json` | A stand-in for Apify's MCP server; its real `401` |

## Check it yourself

From `projects/Agentic/weather-chatbot`:

```bash
npm test
npm run build
npm run e2e
```

With `APIFY_TOKEN` set (step 6's page says how), ask on `MCP · with auth` about a city's weather in the coming days,
and open the forecast chip: its lane says `MCP · with auth`, and its wire view shows the `tools/call` to
`mcp.apify.com`.

## Checked on the live site

On 30 October 2026, once this step was live as `f32d6c3` (its CI run had passed), asked in Dallas's time zone:

- **The same numbers through both auth doors.** "What's the weather in Dallas for the next 3 days?" on
  `MCP · with auth`: the forecast chip said `MCP · with auth` and "3 days · 66 to 81 °F · rain up to 22%", with no
  fallback. On `REST · with auth`, right after, the same line; and the answers gave the same highs and lows, one
  rounded to whole degrees: 75 and 68 °F on Friday, 77 and 66 on Saturday, 81 and 66 on Sunday.
- **Apify ran it with our limits.** Apify Console showed the MCP run's origin as MCP, with an 18-second timeout, where
  the Actor's own default is 300 s, and $0.01 at most: `call-actor`'s `callOptions` reached the run. Its build was
  1.0.9 and its cost $0.005; the REST run showed the same, with the origin API. Build 1.0.9 is also the Actor's latest,
  so the build pin itself will only show on a run once a newer build is tagged latest; the tests check that it's sent
  (bug story 14).
- **The request, as sent.** The chip's wire view showed `call-actor`'s `tools/call` to `mcp.apify.com`, the token and
  the session's id masked: the Actor, Dallas rounded to about 1 km, `waitSecs: 18`, and `callOptions` with build
  1.0.9, 18 s and $0.01. It matched the compare view's cell but for one header, `user-agent`
  (`ai-sdk/2.0.86 node.js/22`), which AI SDK's client adds and the `MCP · no auth` cell had left out since step 4.
  Both MCP cells show it now (entry 97).
- **The log lines.** Vercel's logs for the request held `lane.connect` to our server (1,366 ms, 4 tools); the
  geocoding through it (590 ms, seen from the chat); `lane.connect` with `host: "mcp.apify.com"` (670 ms, 6 tools:
  `call-actor`, the Actor's own tool and four helpers); one `upstream.mcp` line for `call-actor` (9,724 ms) and one
  for `get-dataset-items` (68 ms); the tool call, 10,473 ms; and `chat.done`, after 16,363 ms. No line held the token.
- **The MCP door is slower, by Apify's own wait.** The forecast took 10.5 s here and 3.6 s on `REST · with auth`, for
  runs of 4 s and 3 s. Connecting and reading the items took 0.7 s; `call-actor` answered about 5 s after its run had
  ended. Apify's MCP server waits on purpose: when a run has succeeded but its dataset's count still reads 0, which
  can lag by up to about 5 s, it reads the dataset again after 1, 3 and 5 s before it answers (its
  `src/tools/actors/actor_run_response.ts`). Entry 98 says what that does to our 25 s.
- **No step went backwards.** The browser tests passed against the live site, 48 of 48, with the token set: the
  picker and the compare view showed both auth lanes as live.

## What's next

**Step 8:** protection: BotID, the rate limit, and the security headers. Before it, two fixes: the lane closes once the
answer's stream has ended (the issues log, entries 96 and 100, bug story 15), and Stop reaches the function on Vercel
too (entry 101).
