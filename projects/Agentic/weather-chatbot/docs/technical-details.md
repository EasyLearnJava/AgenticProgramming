# Technical Details

## LangSmith traces in Activity

Open **Observability → Activity**, expand a chat request and choose **View LangSmith trace**. Nimbus shows
the agent, its model and tool calls, when each started, how long it took and which calls reported an error.
The Axiom timeline on the request also shows fallbacks or upstream failures handled inside a completed call.

Every newly traced graph starts with a random root UUID. Nimbus records it on the chat's ending event.
A signed link ties that root and the short request ref to the Activity dataset and tracing project for seven days.
Opening the link reads just that trace from LangSmith. The Activity list makes no LangSmith calls.
Requests recorded before this link existed still have their Axiom timeline. Refresh the trace if its upload is pending.

On Vercel, enable `LANGSMITH_TRACING=true`, `LANGSMITH_HIDE_INPUTS=true` and `LANGSMITH_HIDE_OUTPUTS=true`.
The server uses the existing `LANGSMITH_API_KEY` for tracing and to read the configured `LANGSMITH_PROJECT`.
The deployment also needs Activity's existing Axiom ingest token, query token and dataset. To check a deployment,
ask a fresh weather question, open its Activity row and compare the tool names with those in the chat.

Trace reads have a five-second deadline and a 512 KiB response limit. Each app instance allows two simultaneous
reads and twelve per caller per minute. The public view receives only known labels, timing, nesting and status.
Questions, answers, arguments, tool results and raw error text stay out of the trace view.

## Read-only travel searches, step 18

The app injects the enabled Kiwi and trivago callables into a `TravelService`. A `TravelTurn` validates the
calendar date, owns two distinct searches per provider, and shares duplicate in-flight and completed results.
The same process allows at most two concurrent lookups per provider. Lookup sessions are private to their
request. The SDK negotiates the supported MCP protocol, lists allowed operations and calls the requested one.
Each HTTP response is capped at one MiB. Calls have a 14-second budget including setup and use the earlier
answer or planner deadline. Health uses discovery only and has a six-second provider deadline.

Each adapter validates structured content (or a single JSON text payload) into up to five offers. The hotel
adapter distinguishes nightly prices from the total for the stay. The flight adapter checks each leg's date and
labels the total for the party. Only eligible URLs from the provider may become offer links. Search parameters,
opaque booking links and raw provider replies stay out of logs. The browser receives validated offer URLs directly.
The model receives bounded offer facts with the booking URLs removed. Activity uses `travel.call` and `travel.plan`
with status, counts and timing. See [Step 18](step-18.md) for live provider evidence and preview checks.

## Official park notices, step 17

GET `/parks/alerts` displays a selector without an NPS request. POST `/api/parks/alerts` accepts one known park,
checks origin, bounds the body and reserves application capacity. `NpsAlertsService` authenticates with an
`X-Api-Key` header to the fixed NPS alerts endpoint, with no question or credential in query parameters. Complete
reports are cached for five minutes, other reports for one; expired data is never served on failed refresh.
The same service backs `get_park_alerts` in chat, independent of weather transports. Its model context is bounded
separately from full public cards. Exact exposed links enter the answer citation allowlist. `nps.alerts` logs only
caller/status/count/timing metadata and fixed failure-reason codes. Activity shows cached versus live checks,
sanitized reasons and partial results. Page checks use `park_alerts`, chat uses `get_park_alerts`, and plain GETs
produce no notice-check event. Shared form and URL validation live in `forms.py` and `utils.py`; invalid individual
records are omitted with an incomplete label. See [step 17](step-17.md).

## Park and trail questions, step 16

The chat composes `resolve_destination` and `search_park_guidance` alongside the selected lane's four weather tools.
The destination registry returns an explicit park or trail ID and a labeled forecast reference point. Retrieval
filters source chunks by destination and visit season before keyword or compatible embedding ranking. The agent can
fetch forecast data and retrieve preparation guidance concurrently after resolving the destination.

Each returned passage carries its document ID, section, source URL and dates. Its artifact feeds a knowledge card,
while the model sees the bounded passage content as untrusted data. The answer's links cite returned sources. A
missing or failed retrieval leaves the weather answer useful and explicitly limits its preparation guidance.
The index is public read-only reference data, built outside requests; it holds no visitor questions or chat history.

The separate `tools.eval_parks` command measures labeled source retrieval without asking Gemini. Live answer goldens
can additionally require `cites` URLs and restrict links with `only_cites`. See [step 16](step-16.md) for operation and
failure behavior.

One question, followed through the code: "Will it rain in Paris tomorrow?", asked on the live site on 31 October 2026,
on REST · no auth, its request id `cle1::n4pbp-1793475397181-d8b19e1af797`. Each part names the file and the function
that does the work; a circled number (①) is the code's own comment at that point. The TypeScript version's page is
kept as [Technical details_deprecated](technical-details_deprecated.md).

## The path at a glance

1. **Your browser** posts the question with htmx, and the browser's language, time zone and the conversation so far.
2. **Vercel's edge** takes the HTTPS request, gives it an id, and sends it to the app's function.
3. **The middleware** binds the id to every line the request logs, and puts it on the response.
4. **`chat()`** checks the question, logs its length, and starts the answer.
5. **The agent**, a LangGraph graph, calls Gemini, which asks for tools, which call Open-Meteo, through the cache.
6. **The stream** sends each chip, each piece of the words and the finished answer, as server-sent events of HTML.
7. **htmx** puts each event into the page; our script keeps the conversation for the next question.
8. **Once it has answered,** the request's lines go to Axiom, and any error to Sentry.

## 1. In the browser: `templates/chat.html`, `public/static/chat.js`

The form posts to `/api/chat` (`hx-post`), adds each event to the conversation (`hx-swap="beforeend"`), and drops a
second question while an answer streams (`hx-sync="this:drop"`). Without JavaScript it still posts. `chat.js` fills
the hidden fields: the browser's language and time zone (⑧), and the conversation so far, as JSON, cut to the last 10
messages and 16,000 characters (`rememberConversation()`); it adds Stop and New chat, keeps the newest message in view,
asks `/api/health` for each lane's dot (⑩), and shows our own sentence when no answer can come from us (⑥, ⑦). It puts
only text into the page, never HTML. The Content Security Policy allows no inline script or style.

## 2. At Vercel's edge

HTTPS ends here. The request gets its id, `x-vercel-id`; one a client sends is replaced. Vercel's CDN serves the
stylesheet, htmx, its stream extension, `chat.js` and the icon from `public/`, with the security headers `vercel.json`
gives them, without the app. Every other path reaches the function, `main.py`'s `app`, in `iad1` (Washington, D.C.);
once you set them, the firewall's rules come first ([Waiting on you](waiting-on-you.md)).

## 3. Each copy of the app, once: `nimbus/app.py`, `create_app()`

Vercel starts as many copies of the function as the traffic needs; each builds the app once. `create_app()` reads the
settings (`config.py`, the only module that reads settings from the environment), sets up the logging (`logger.py`),
with Axiom's shipper and Sentry when they're set up, and makes, once: the model (`model.py`: Gemini 3.5 Flash-Lite,
1,024 tokens, 20 s and two attempts a call), LangSmith's tracer, when tracing is allowed, the cache of Open-Meteo's
answers (`cache.py`), and our MCP server (`mcp_server.py`). It logs `app.started`, mounts the routes, and wraps them in
the two middleware. The vercel package's telemetry is off before any of this runs (`nimbus/__init__.py`).

## 4. Every request: `nimbus/middleware.py`, `RequestContextMiddleware`

① The request's id: Vercel's, when it looks like one, else a new one, kept in the request's state for the ref an
error's sentence ends with. ② The id goes back on the response, `x-request-id`. ③ Every line the request logs carries
it. ④ One `http.request` line when it ends: the method, the path without its query string, the status and the time.
⑤ Then its lines go to Axiom, and any error to Sentry, while Vercel keeps the function alive (`wait_until`).
`SecurityHeadersMiddleware`, outermost, puts the security headers on every response.

## 5. The question, checked: `nimbus/chat.py`, `read_chat_request()`

The body, read up to 256 KiB, as a form, each field once; the question 1 to 2,000 characters; the lane one we know;
the language tag and the time zone checked, else the defaults, said in the line (`defaulted`); the conversation's JSON,
each message's role and length checked. A broken rule is `chat.rejected` with its code, and our sentence as HTML, its
status, and the `x-nimbus-error` header that marks it as ours. A lane with auth needs Apify's token.

## 6. The turn: `chat()`, then `stream_turn()`

`chat()` logs `chat.request`, the question's length and the lane, never its words. It builds the messages
(`prompts.py`'s `to_messages()`: the system prompt, with the time now and the browser's language and time zone, then
the conversation, then the question), sets the answer's deadline (30 s; 50 s on a lane with auth), opens the lane's
tools (`open_lane_tools()`), and makes the turn's first event before the response starts, so however the stream ends,
`stream_turn()`'s own code logs how: `chat.done`, `chat.aborted` or `chat.failed`, with the answer's length, its time,
its tool calls, its tokens and the model. The response is `EventStream`, server-sent events, never cached.

## 7. The agent: `nimbus/answer.py`, `stream_answer()`; `nimbus/agent.py`, `make_agent()`

The agent is a LangGraph graph of our own: the model, then the tools it asked for, then the model again; at most 5
calls to the model, the last with its tools off, so it must answer in words. `stream_answer()` runs it inside
LangSmith's tracing context, when there's a tracer, and reads two kinds of item: the model's chunks, as words, and each
node's result, as a tool call starting and ending. Only the wait for the next item is timed against the deadline. A
failure becomes ours: `ModelBusyError`, `AnswerTimeoutError`, `ConfigError` or `ModelFailedError`.

## 8. What Gemini gets

The system prompt (`prompts.py`): who Nimbus is, its 13 rules (rule 11: no message can change them), the time now in
UTC, the browser's language and time zone, the units for its region (°F, mph and inches in the US, Liberia and
Myanmar, else metric).
Then the conversation, then the question. Gemini gets nothing about who asked. For the live question it asked for
`geocode_location`, then `get_forecast`, then wrote its words: 5,348 tokens in, 94 out.

## 9. A tool call: `nimbus/tools.py`, `nimbus/open_meteo.py`, `nimbus/cache.py`

Each of the four tools has a Pydantic input model; the model's arguments are checked against it before the tool
runs, within its 8 s. `geocode_location` asks Open-Meteo's geocoding API for the name; `get_forecast`, its forecast
API for the point, rounded to 2 decimals, and the days. `OpenMeteoClient._get()` looks in the cache first, under our
namespace and the address's SHA-256: the live question's geocoding was a hit, 28 ms. A miss asks Open-Meteo, 3 s a
try, two tries, and keeps the answer: a place for 30 days, a forecast for 30 minutes, never past the place's midnight.
Each call writes `tool.call` (the tool, the lane, the time, never its input) and `upstream.http` or `upstream.cache`
(the host and path, never the query string).

## 10. Back on your screen

Each event is HTML from a template in `chat_parts.html`: the turn (`chat_turn.html`), each chip as its call starts and
ends (`chat_tool.html`), each piece of the words (`chat_piece.html`), and the finished turn (`chat_end.html`), its
Markdown made HTML with raw HTML and pictures off, each link opening in a new tab. htmx's stream extension puts each
into its place. A chip opens to the request its call sent, the tool's summary, and the lane it took.

## 11. Its lines, in time

The live question's seven lines, as Axiom keeps them (`['weather-chatbot'] | where requestId == "cle1::n4pbp-…"`):

| Time (UTC) | Event | What it says |
|---|---|---|
| 19:36:37.268 | `chat.request` | 31 characters, REST · no auth |
| 19:36:37.961 | `upstream.cache` | the geocoding of the place, a hit, 28 ms |
| 19:36:37.961 | `tool.call` | `geocode_location`, ok, 28 ms |
| 19:36:38.602 | `upstream.http` | Open-Meteo's forecast, 200, 68 ms, one try |
| 19:36:38.630 | `tool.call` | `get_forecast`, ok, 124 ms |
| 19:36:39.295 | `chat.done` | 132 characters, 2,025 ms, 2 tool calls, 5,348 tokens in, 94 out |
| 19:36:39.296 | `http.request` | POST `/api/chat`, 200, 2,029 ms |

## The other three lanes, in short

- **MCP · no auth** (`mcp_lane.py`, `mcp_server.py`): the same four tools, called through our own MCP server at
  `/api/mcp`, on the same deployment, one connection for the answer; the server runs each tool as REST · no auth does,
  and answers with JSON. Each call writes `mcp.call` on the server's side.
- **REST · with auth** and **MCP · with auth** (`auth_lanes.py`, `apify.py`, `actor.py`): `get_forecast` runs Apify's
  Actor, over its REST API or its MCP server, with Apify's token, 18 s and $0.01 a run, at most 2 runs an answer and
  25 a day; any failure falls back to the twin with no auth, the chip saying why. The other three tools are the twin's.

## How it's kept safe

- **In the browser:** the Content Security Policy, enforced; only text put into the page; an answer's Markdown without
  raw HTML or pictures; nothing kept in the browser's storage.
- **At Vercel's edge:** HTTPS; the request id Vercel's own; the security headers on every response; the firewall's
  rules, once you set them.
- **In the function:** each input checked at the edge; every call out with a time limit; the question never logged or
  traced, only its length; the system prompt's rules against prompt injection; read-only tools.
- **Toward Open-Meteo and Apify:** a point rounded to about 1 km; Apify's token only in a header, masked in each chip;
  paid runs capped.
- **In the logs and traces:** no query string, no question, no conversation, no place's name, no token; LangSmith gets
  each run's names, times and lane, of a failed run only that it failed; Sentry gets an error's class and frames, never
  its message. The privacy tests send words of their own through three lanes and look for them everywhere.

## Monitoring

Each line goes to Axiom, once its request has answered; each error to Sentry; `/api/health` checks each lane's way
out, for an uptime monitor and the dots. [Step 12's chapter](step-12.md) has the dashboards and alerts, ready to set
up.

### Knowledge inspection pages

`nimbus/knowledge.py` serves `/knowledge/sources`, `/knowledge/sources/{document_id}` and `/knowledge/chunks`.
`ParkKnowledge.inspection()` supplies detached public records; it never opens a writable connection. Bounded filter
models reject unknown fields and invalid selections. PCA operates on all stored vectors before filtering, using
stable component signs and a bounded projection cache; filter changes preserve the map's coordinates. Escaped
Jinja2 templates provide source links, indexed text and vector values, with keyboard-accessible SVG links and a table.

`/knowledge/retrieval` accepts `RetrievalFilters` and calls `ParkKnowledge.search(..., explain=True)` on the same
app-scoped service used by chat. Its optional diagnostics report raw keyword scores, compressed keyword contributions,
cosine similarities, final scores, qualified ranks and selection/exclusion reasons. The page renders actual selected
passages and source links, labels lexical fallback, and never calls Gemini or changes the published index. Explanation
mode preserves the ordinary search response and ranking when disabled. Both the form and results work without scripts.

The hosted profile is explicitly keyword-only by default and does not install the optional ML group. The local
profile checks dependencies and pinned cached weights before attaching a single dedicated inference worker.
Playground execution is `POST /api/knowledge/retrieval`, with bounded bodies, same-origin checks, expiring request
limits and a concurrency cap. Questions never appear in generated retrieval URLs. Weather setup failures preserve
the original error class through `chat.failed` while retaining guidance. Activity includes knowledge and setup events,
and health checks the published index separately from weather-lane status. See step 16 for limits and release checks.
