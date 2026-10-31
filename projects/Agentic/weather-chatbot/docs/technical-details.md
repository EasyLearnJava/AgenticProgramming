# Technical Details

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
settings (`config.py`, the only module that reads the environment), sets up the logging (`logger.py`), with Axiom's
shipper and Sentry when they're set up, and makes, once: the model (`model.py`: Gemini 3.5 Flash-Lite, 1,024 tokens, 20
s and two attempts a call), LangSmith's tracer, when tracing is allowed, the cache of Open-Meteo's answers
(`cache.py`), and our MCP server (`mcp_server.py`). It logs `app.started`, mounts the routes, and wraps them in the two
middleware. The vercel package's telemetry is off before any of this runs (`nimbus/__init__.py`).

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
