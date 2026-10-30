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
