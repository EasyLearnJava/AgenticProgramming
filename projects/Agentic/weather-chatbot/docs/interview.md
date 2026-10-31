# Interview Guide

What to tell an interviewer about Nimbus's rebuild in Python, step by step: each chapter's interview questions, with
short answers, collected here as the steps are built. The TypeScript version's guide is kept as
[Interview guide_deprecated](interview_deprecated.md).

## The pitch

Nimbus is a weather chatbot, rebuilt in Python as a production-grade tutorial, one step at a time: FastAPI and Jinja2
for the pages, LangGraph for the agent (from step 4), and MCP for its tools (from step 8), deployed to Vercel on every
push, with structured logs, security headers, and unit, browser and accessibility tests from the first step.

## Step 1 · The Project, Its Pages and Its First Deploy

**1. Why FastAPI, and not Flask or Django?**
FastAPI is ASGI, so it can stream an answer while it's written (step 2) and wait on the model and the weather APIs
without blocking; it checks every input with Pydantic and type hints; and Vercel runs it as it is. Flask is WSGI: it
can stream from a generator, but each open stream holds a worker thread, and async is an add-on. Django brings an ORM,
an admin and sessions this app doesn't need.

**2. Why render pages on the server with Jinja2 instead of building a React app?**
The whole app stays in Python, the pages work with no JavaScript, and the Content Security Policy can forbid inline
scripts from day one. Where a page must update live, HTMX (step 2) swaps in HTML the server renders. React pays off for
a far more interactive interface.

**3. What is ASGI middleware, and why not Starlette's `BaseHTTPMiddleware`?**
ASGI middleware is a callable that wraps the app: it gets each request's scope and every message the app sends.
`BaseHTTPMiddleware` is easier to write, but wraps the response in a stream of its own, and has had problems with
streamed bodies and with context variables; plain ASGI passes each message through untouched, which streamed answers
need.

**4. How does a request id travel through the app?**
Vercel gives each request an id, `x-vercel-id`. The middleware takes it if it looks like an id, else makes one; binds
it to structlog's context, so every line the request logs carries it; and sends it back as `x-request-id`. One search
then finds everything about one request; later steps pass it on to our MCP server too.

**5. Why check the `x-vercel-id` header before using it?**
A header can hold anything, and this one goes into every log line and back into a response header. Only ASCII letters,
digits and `_:.-` are allowed, at most 128: without `re.ASCII`, Python's `\w` would take any Unicode letter.

**6. How are settings and secrets handled?**
One module, `config.py`, reads the environment with pydantic-settings and checks each value when the app starts;
nothing else reads `os.environ`. Secrets live in Vercel's Sensitive environment variables, or in `.env.local` on a
computer, which git never sees. Tests build their own settings, and remove the shell's, so nothing leaks in.

**7. What does your Content Security Policy do, and why enforce it from the start?**
It lets a page load scripts, styles, pictures and connections only from our own site, and forbids framing, plugins
and forms that post elsewhere. The first version shipped it report-only and never got to enforcing it; with no inline
script from the start, enforcing it costs nothing.

**8. How do you render Markdown safely?**
markdown-it-py with raw HTML off, so HTML in a page shows as text; its link check refuses `javascript:` addresses; and
Jinja2 escapes every value except two marked safe: the renderer's own output, and a menu label with the one `<wbr>` we
add, the label itself escaped first.

**9. How do you make sure a URL can't read any file it names?**
Every documentation page is in a registry, found by its address; the file's name comes from the registry, never from
the URL, so `/docs/../../etc/passwd` simply isn't a page.

**10. How is a Python app deployed on Vercel?**
Vercel's FastAPI preset finds `app` at the top level of `main.py`, installs the packages with uv from `pyproject.toml`
and `uv.lock`, uses Python 3.13 from `.python-version`, and serves `public/` from its CDN without running the function.
`vercel.json` keeps the tests out of the function's bundle, and gives the CDN's files their headers.

**11. How do you choose and pin dependency versions?**
Exact versions, which uv chooses with `exclude-newer` set two weeks back, so a release has had time to settle before
we use it; `uv.lock` pins everything else, CI installs with `--locked`, which fails if the lock is out of date, and uv
itself is pinned in CI to the version that wrote the lock.

**12. How is the app tested?**
Unit tests call the app in memory with `TestClient`: every page, header, log line and setting. Browser tests serve the
real app with Uvicorn and drive it with Playwright on every page: accessibility with axe, no sideways scrolling on a
phone, no console errors. A mutation check breaks each rule on purpose, to prove a test catches it.

**13. What is a mutation check, and what did it find here?**
It changes the code the way a bug would, one change at a time, and runs the tests; a change no test notices points at
a rule nothing tests. Here, removing the guard that keeps the Chat link from being marked on other pages broke
nothing, since no test used an address starting with `//`; a test now does.

**14. Why log the path but never the query string?**
A query string can hold what a user typed, such as a question, and the logs must never hold that. The path says which
page was asked for, which is all the logs need. Uvicorn's own access line would log it, so it's turned off.

**15. Why JSON log lines?**
Each field can be searched and counted (`status`, `ms`, `requestId`) in Vercel's logs and, from step 12, in Axiom,
without parsing text.

**16. Static files skip your middleware: how do they get security headers?**
On Vercel, the CDN serves `public/` before any function runs, so headers the app adds never reach those files.
`vercel.json` gives `/static/*` the same headers, and a unit test fails if the two lists ever differ.

## Step 2 · The Chat Streams Its Answer

**1. Why server-sent events, and not WebSockets?**
The answer flows one way, from the server to the page, and ends when the answer does. Server-sent events are plain
HTTP: one request, one response that keeps coming, through Vercel's edge and any proxy, with no protocol upgrade and
nothing to keep open between questions. WebSockets pay off when both sides talk at once, as in a game or a shared
editor.

**2. Why htmx, and why version 4?**
The server already renders the page, so it renders each event too, and htmx puts it in place: no client-side state
and almost no JavaScript of ours. htmx 2's stream extension can only `GET` (it opens an `EventSource`), which would put
the question in the address; htmx 4 streams the answer to the form's own `POST`, and its `<hx-partial>` lets each
event name its own target.

**3. How does the answer stream through FastAPI?**
The route returns a `StreamingResponse` over an async generator; each `yield` is one event, written as `data:` lines
and a blank line, and Starlette sends it as soon as it's made. The response's type is `text/event-stream` and it's
never cached, and nothing between the app and the browser waits for the end, since the middleware is plain ASGI.

**4. How does Stop work, end to end?**
The page's script triggers `htmx:abort`; htmx aborts its `fetch`, and the browser drops the connection. The server
tells the app with an `http.disconnect` message, and Starlette, listening for it, cancels the stream, so
`asyncio.CancelledError` lands in the generator; it logs `chat.aborted` and stops. On the page, the answer that never
got its end gets "Stopped.". On Vercel, the Python runtime gives the app no such sign, so the function writes the rest
of the answer to no one: Stop there ends it on the page only.

**5. What if the server speaks ASGI 2.4?**
ASGI 2.4 adds a second sign that the browser has gone: a send to a closed connection raises `OSError`. Relying on it,
Starlette stops listening for `http.disconnect`, and the failed send becomes `ClientDisconnect`, which would reach the
middleware and be logged as an error. `EventStream` takes it as the browser leaving, and closes the generator at once,
so the answer's end is logged within its request either way; a test plays each kind of server.

**6. How do you keep streamed HTML safe?**
The server makes all of it, and Jinja2 escapes every value, so a question like `<script>` is text. The page's own
script only ever sets `textContent`. The Content Security Policy runs only our own files, with no inline script and no
`eval`, which also rules out `hx-on` attributes; htmx is served from our own site, checked by hash.

**7. Why does each event carry HTML rather than JSON?**
The server already has the templates and escapes every value; the browser only puts each event in place. With JSON,
the page would need code to build the same HTML, a second copy of the templates, and its own escaping to get right.

**8. How do you show errors without leaking them?**
Each error the app expects has its own sentence; any other gets one fixed sentence, and the error's own text stays out
of the page and the logs, which get its class. A failure's sentence ends with a ref, the last 8 letters and digits of
the request's id, so a visitor can read it out and we can find the request's lines.

**9. How does the page tell our errors from someone else's?**
Our error pages carry `x-nimbus-error: 1`. The script lets into the page only our stream (`text/event-stream`, 200)
or a response with that header; anything else, such as a proxy's 502 page, becomes "The chat couldn't be reached.
Please try again.". A request that fails outright gets the same sentence.

**10. How do you check the request at the edge?**
In order, cheapest first: its type must be the form's (else 415); its declared length at most 32 KiB, refused before
a byte is read, and its body read only that far (413); its fields strict UTF-8, at most 10, each once; then Pydantic:
the question trimmed, 1 to 2,000 characters, and no field we don't know (400). Each broken rule has its own sentence.

**11. How do you test a stream, and a disconnect?**
In memory, `TestClient` reads a whole stream, so the tests check each event's HTML. For a disconnect, a test calls the
app as an ASGI server would, with its own `receive` and `send`: one says the browser has gone after a few events, the
other fails the next send; both must end with `chat.aborted`, before the request's own line, and no error. In the
browser, Playwright presses Stop, blocks the request, and stands in another service's error page.

**12. Why serve htmx from your own site instead of a CDN?**
The policy allows scripts from our own site only, and a third-party CDN would be one more place that can change the
code we run. The two files are npm's, copied unchanged after the package's integrity hash matched the registry's, and
a test fails if a byte of either changes.

## Step 3 · Gemini Answers, Streamed

**1. Why LangChain's chat model rather than Google's SDK directly?**
One interface for any provider: `astream()` for the words, `usage_metadata` for the tokens, and standard exceptions
such as `ModelRateLimitError`. Our mapping from failures to sentences names no provider, the stand-in model in the
tests plugs into the same interface, and the agent in steps 4 and 5 is built on it.

**2. How do you stream a model's answer to the page?**
`model.astream(messages)` yields chunks as the model writes; each one's text goes straight into the same server-sent
events as step 2's fixed answer, as plain text. When the stream ends, the last event swaps in the finished answer, its
Markdown made HTML once, safely.

**3. Why cap tokens and time, and how?**
On Vercel, Stop never reaches the function, so an answer no one reads still runs. `max_output_tokens=1024` caps what
the model writes, its thinking included, which is set to the least there is; one 30-second deadline caps the whole
answer; each call waits 20 s, with two attempts at most, where LangChain's default would make six.

**4. How do you turn a model's failures into messages a user can act on?**
LangChain's standard exceptions: a rate limit becomes "busy, try again in a minute", a timeout "took too long", an
authentication error "isn't set up", anything else "didn't answer". The model's own error is kept as the cause, and
logged by its class only: its message could quote the question.

**5. What goes into the system prompt, and why the visitor's time zone?**
The rules (no weather as fact without tools, weather only, short answers, the units), then the time in UTC and in the
visitor's zone, with their today and tomorrow. Without the zone, "tomorrow" would be the server's tomorrow, which near
midnight is a different day.

**6. How do you check a time zone that comes from the browser?**
It must be one the IANA database names, from `zoneinfo.available_timezones()` with the `tzdata` package: a fixed set,
read once, so no string from the browser ever becomes a path the library opens.

**7. How do you render a model's Markdown safely?**
markdown-it with raw HTML off, so tags show as text; pictures off, so the page never fetches from wherever the model
pointed; `javascript:` addresses are never linked; and each link opens in a new tab with `noopener noreferrer`.

**8. How do you keep questions out of LangSmith?**
The app traces only when LangSmith's variables say to hide both inputs and outputs, and then through a client of its
own, `Client(hide_inputs=True, hide_outputs=True)`, passed in `tracing_context()`: LangSmith's default client would
hide only if each variable held exactly the string `true`.

**9. How do you test code that calls a model?**
With a stand-in: a small `BaseChatModel` that streams a known answer a word at a time, reports tokens, and raises on
cue. The app takes its model from `app.state`, so a test puts the stand-in there; the real model never runs in a test.

**10. Why not put an async generator's whole body inside `asyncio.timeout()`?**
The deadline cancels whichever code is running when it passes. Between two `yield`s, that's the code reading the
generator, the page's sending here, not the generator: the answer would end as if the browser had gone. So one
deadline is set, and only the generator's own waits are timed, with `asyncio.timeout_at()` around each `anext()`.

**11. Why did Vercel's logs show lines your computer never did?**
Python writes another library's info lines nowhere until something sets its logging up, and Vercel's runtime does: on
Vercel, httpx's line for each request it sent, and google-genai's, came out as plain text. So the app sets the root
logger up itself, with its own handler and level: warnings and errors only, each as one of our JSON lines, with any
query string cut off.

## Step 4 · The Weather Tools, and an Agent That Calls Them

**1. What does a model actually do when it "calls a tool"?**
It doesn't run anything: it answers with a request, the tool's name and its input as JSON, fitted to the schema it was
given. The app runs the tool, sends the result back as a tool message, and calls the model again; the loop ends when
the model answers in words.

**2. Why `content_and_artifact`?**
What the model reads and what the app keeps are different things. The model needs the weather; the page needs the
request and its time. The artifact rides along on the tool message but never reaches the model, so it doesn't cost
tokens or confuse the answer.

**3. Why does a failed tool call go back to the model, not fail the answer?**
The model can still answer: say the forecast didn't come, give the weather now, or suggest trying again. The tool
raises a `ToolException` with our sentence, and the agent turns it into a tool message marked as an error; any other
error still fails the answer.

**4. Why is the ambiguity rule in code rather than in the prompt?**
A rule in code decides the same way every time, and a test can hold it to six real names. The prompt only says what to
do with the result: when `is_ambiguous` is true, fetch no weather and ask which place.

**5. Which failures are worth a retry?**
A timeout, a connection that failed, a 5xx: the next try may well succeed. A 429 only when it asks for a short wait,
and never a 4xx or an answer you can't read, which would come back the same. One retry, with a random wait, so many
clients don't retry in step.

**6. How do you stream an agent's progress to the page?**
With LangGraph's stream modes: `messages` gives the model's chunks as it writes, `updates` each node's result as it
ends. The model's update names the tool calls; each tool's update carries its result. Each becomes an event the page
puts in place.

**7. How do you test an agent without a model or the network?**
A stand-in chat model that asks for the tools the test scripts, then streams a known answer; and the HTTP client's
transport swapped for one that plays back recorded answers. Nothing leaves the test, and every run is the same.

**8. Why round coordinates?**
Two decimals is about 1 km, enough for the weather; a more exact point could be someone's address, and it would end up
in requests, chips and traces.

**9. Why build the agent for each answer?**
It takes 1.5 ms, and its tools hold the answer's own HTTP client, open as long as the answer and closed with it. One
agent for the app would share one client across event loops and answers.

**10. What does the prebuilt agent leave to you?**
Its limits: its own step limit is 9,999, and it gives the last call to the model the tools like any other, so an answer
can end on a failure rather than in words. Step 5 builds our own graph for that.

## Step 5 · The Agent as a Graph of Our Own

**1. Why replace a prebuilt agent with your own graph?**
The prebuilt one decides the loop's limits for you: its own step limit is 9,999, and its last call can still ask for a
tool, so a limit ends the answer with a failure. In our own graph, the limits are a few lines of code, tested.

**2. How do you make sure an agent's answer always ends in words?**
Count the calls to the model in the state, and on the last one bind the tools with `tool_choice="none"`: the model
still sees them, but can't call one, so it answers with what it has.

**3. What does `Send` do in a LangGraph graph?**
It starts a node with an input of its own. Sending each tool call to the tools node on its own makes each a task: they
run at once, and each one's result comes as soon as it's done.

**4. Where do you put an agent's time limits?**
On the waits: the first chunk of each call to the model, each tool call, and the whole answer around each wait for the
run's next item. Never around a `yield`, where the deadline could land in someone else's code.

**5. Why keep a recursion limit the graph can't reach?**
It costs nothing, and if a change ever broke the loop, the run would still end.

## Step 6 · The Chat Remembers, in the Browser

**1. How does a chat remember with no database?**
The client keeps the conversation and sends it back with each question; the server keeps nothing. It costs bandwidth
and tokens, which a cap bounds, and it means the server must treat the conversation as untrusted input.

**2. What do you check in a conversation a client sends back?**
Its shape (JSON of messages with a role and a text, nothing else), its roles (the user's and the assistant's only, in
turn), and its sizes (messages, characters). And what it may hold: never a tool's result, which the client could forge.

**3. Why do the tools run again for a follow-up question?**
The earlier answers came back from the browser: their weather is the client's word. Rule 1 says weather facts come
only from tool results, so the model fetches them again, from Open-Meteo.

**4. Why cap the conversation at the newest messages?**
Each question sends it all to the model again: without a cap, tokens and time grow with every question, and so does
the request.
