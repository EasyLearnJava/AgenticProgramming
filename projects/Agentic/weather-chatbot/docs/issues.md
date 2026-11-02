# Issues and Fixes

Every technical problem met while rebuilding Nimbus in Python: what happened, how it was found, why, the fix, and the
check that now guards it, so it can't quietly come back. Most are small; the ones that were real bugs or holes will
also be told as stories at the top. *Found by* says how each surfaced: **checking our work** (a test, the type
checker, a mutation check, a screenshot), **the review** (the independent reviewer before each commit), **reading a
package's code**, **deploying**, or **testing a real API**. The TypeScript version's log is kept as
[Issues and fixes_deprecated](issues_deprecated.md).

## Step 1 · The Project, Its Pages and Its First Deploy

1. **Starlette's test client said `httpx` is deprecated.** *Checking our work* (the first smoke test). Every test run
   warned: "Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead." Starlette 1.8's test
   client tries `httpx2`, pydantic's successor to `httpx`, first, and falls back to `httpx` with that warning. **Fix:**
   the dev dependency is `httpx2` 2.13.1, the newest release at least two weeks old. **Check:** pytest turns every
   warning into an error (`filterwarnings` in `pyproject.toml`, issue 14), so it would fail the tests.
2. **A deprecated page marked two menu links as current.** *Checking our work* (writing the page tests). The first
   plan served the TypeScript app's pages under `/docs/`, as `/docs/step-3_deprecated`; on any of them, the new
   "Documentation" link (`/docs`) counted as the section the page was in, and the page's own link as the page.
   **Fix:** each deprecated page keeps its old address with the suffix: `/docs_deprecated/step-3_deprecated`, and
   `/issues_deprecated` for the old `/issues`. **Check:** the menu-marking tests, for a new chapter and a deprecated
   step and page.
3. **The request id was missing from the log lines a test captured.** *Checking our work* (a failing test).
   structlog's `capture_logs()` swaps every configured step for its own capture, so the step that adds the request's
   context (`merge_contextvars`) never ran. **Fix:** the test passes that step back, `capture_logs(processors=
   [merge_contextvars])`, which structlog allows since 25.5. **Check:** the middleware test that finds the id on the
   line.
4. **A rule in the menu wasn't tested.** *Checking our work* (a mutation check). Removing the menu's guard that keeps
   "Chat" (`/`) from being marked on other pages broke no test: no tested address started with `//`, the only kind
   the guard changes anything for. **Fix:** a test with the address `//docs`. **Check:** the mutation check (now
   `tools/mutation_check.py`) catches every change, 16 by the end of this step.
5. **Four deprecated pages scrolled sideways on a phone.** *Checking our work* (the browser tests, at 360 pixels).
   **How we found the cause:** a script listed the elements wider than the screen: inline code that can't break (a
   test file's path, a Gemini address, an error message) on three pages. The fourth listed nothing: its heading,
   "Documentation_deprecated", is one 24-character word at 28 px, and a heading's box doesn't grow with its text, so
   only the text was too wide. **Fix:** a long word in the docs breaks when it would push the page sideways
   (`overflow-wrap: break-word` on `.doc`). **Check:** the browser tests, on all 21 pages, at 1,280 and 360 pixels
   (issue 14).
6. **Two Windows traps while finding issue 5.** *Checking our work.* A diagnostic script run from the scratchpad
   couldn't import `nimbus`: Python puts the script's own folder on its import path, not the one you run it from. And
   Git Bash turned the argument `/docs_deprecated` into `C:/Program Files/Git/docs_deprecated`, as it does with any
   argument starting with `/`. **Fix:** `PYTHONPATH=.`, and `MSYS_NO_PATHCONV=1` for that command (the tests set
   their own path in `pyproject.toml`). **Check:** the script listed the pages' wide elements.
7. **mypy refused a page's values.** *Checking our work* (mypy, strict). `_render()` took a `dict[str, object]`, and
   a dict of lists isn't one: a `dict` is invariant in its values. **Fix:** it takes a `Mapping[str, object]`, which
   is covariant and read-only. **Check:** mypy passes.
8. **mypy found two modules named `conftest`.** *Checking our work* (the full run). Once the browser tests had their
   own `conftest.py` beside the unit tests', mypy stopped before checking anything: "Duplicate module named
   'conftest'". Without `__init__.py`, each test folder is no package, so both files are the module `conftest`.
   **Fix:** `tests/`, `tests/unit/` and `tests/e2e/` are packages, so they're `tests.unit.conftest` and
   `tests.e2e.conftest`. **Check:** mypy checks all 24 files.
9. **A deprecated menu link ran past the menu's edge.** *Checking our work* (a screenshot of the chat page). On a
   computer, "Documentation_deprecated" is one word wider than the 220-pixel menu, and bolder still when it's the
   current page; the page didn't scroll sideways, so no test had seen it. **Fix:** each label may break before
   "_deprecated" (`to_menu_label()` puts a `<wbr>` there, the rest escaped as usual), so it wraps as
   "Documentation" and "_deprecated". **Check:** a browser test that no menu link is wider than the menu, at 1,280
   and 360 pixels (written first: it failed until the fix).
10. **The CDN's files had none of our security headers.** *The review.* The step said every response gets the security
    headers, but Vercel's CDN serves `public/` (the stylesheet and the icon) before the app runs, so those files had
    Vercel's default headers only; the unit test that checked `/static/app.css` reached the computer's mount instead.
    **Fix:** `vercel.json` gives `/static/*` the same headers, as Vercel's docs suggest for `public/`. **Check:** a
    unit test that `vercel.json`'s headers equal `SECURITY_HEADERS`; on the live site, the stylesheet's headers.
11. **The unit tests read the shell's environment.** *The review* (it ran them with `LOG_LEVEL=warning` set: 4
    failures; with `VERCEL_ENV=preview`: 1). The settings read real variables before their defaults, and some tests
    built settings without giving every value. **Fix:** an automatic fixture removes each variable the settings read
    before every unit test; the browser tests' app is given every value. **Check:** the unit tests pass with both
    variables set in the shell.
12. **App code that only tests used.** *The review*, against the plan's rule. `to_ref()` and its constant were used
    only by a test; so was `to_request_id()`'s taking several values; and the setting `vercel` was read by no code,
    and broke the naming rule for booleans. **Fix:** the first two are gone (step 8 brings back what the MCP server
    needs); the setting is `is_vercel`, and decides whether `/static` is mounted: Vercel's docs say never to mount
    `public/` with `app.mount()`, and its build imports the app while `public/` is still there. **Check:** a unit
    test that on Vercel the app serves no `/static`; the mutation check's "on Vercel, public/ is never mounted".
13. **Outputs that didn't come from the commands shown.** *The review.* The README and the chapter showed `uvicorn
    ... --reload`, but the run behind them had no `--reload`, which adds the reloader's lines; and the health check's
    `curl -i` block was rebuilt from another client's headers, without its status line or `server: uvicorn`.
    **Fix:** one run again, with the very commands shown and the real `curl`. **Check:** each output block in the
    README and the chapter is copied from that run.
14. **Two checks this log named didn't exist.** *The review.* Issue 1's check, warnings turned into errors, was a
    one-off command, not a standing test; and issue 5's named every page, while the browser tests listed 11 of the 21.
    **Fix:** `filterwarnings = ["error"]` in `pyproject.toml`; the browser tests build their list of pages from the
    registry. **Check:** both suites pass with warnings as errors; 89 browser tests, on all 21 pages.
15. **An aligned table would have broken the policy.** *The review.* markdown-it writes a column's alignment (`|--:|`)
    as `style="text-align:right"`, and the enforced policy refuses inline styles, so the alignment would be lost, with
    an error in the browser's console; no page had one yet. **Fix:** a render rule turns it into a class,
    `align-right`, which the stylesheet aligns. **Check:** a unit test; the mutation check's "an aligned column has no
    inline style".
16. **`HEAD /api/health` answered 405.** *The review.* A FastAPI route answers only the methods it lists, and uptime
    monitors often send `HEAD`. **Fix:** the health check lists `GET` and `HEAD`. **Check:** a unit test; the mutation
    check's "the health check answers HEAD".
17. **Smaller review findings.** *The review.* Docstrings for the middleware's and the logger's inner functions; the
    deprecated README's and System design page's renamed links, which pushed lines past 120 characters and still
    showed the old names; the chapter's circled numbers, which now cite each file's own; CI's uv, pinned to 0.9.18,
    the version that wrote `uv.lock`; the claim that only the Markdown goes unescaped (a menu label does too, with its
    `<wbr>`); the Flask answer (it can stream, but each open stream holds a worker thread); `main.py`'s command, which
    now has `--no-access-log`, since Uvicorn's own line keeps the query string; the mutation check, now in the
    project (`tools/mutation_check.py`); and a test that a stream passes through the middleware message by message.
18. **A pulled `.env.local` would have made a computer look like Vercel.** *The review* (of issue 12's fix).
    `vercel env pull` copies Vercel's own variables into `.env.local`, `VERCEL="1"` and `VERCEL_ENV="development"`
    among them, and the settings read that file: with it, a computer's app took itself for Vercel's, mounted no
    `/static`, and its pages had no stylesheet (the review reproduced it: `/static/app.css` answered 404). Anyone who
    pulled the project's variables, to run the app with them, would have met it. **Fix:** Vercel's own settings come
    only from the real environment: a settings source drops them from the `.env` files' values
    (`WithoutVercelFields`). **Check:** a unit test with such a file; the mutation check's "Vercel's own settings never
    come from a .env file".
19. **A build-log line copied wrong.** *The review.* The chapter's "Deploy it" showed Vercel's line
    `Creating virtual environment at "...` without its closing quote and dots: it was copied from a browser tool's
    outline of the page, which cut the line's end. **Fix:** the line copied again, from the page's own text.
    **Check:** each line of the block compared with the build log's text.
20. **The System design page claimed more than step 1 does.** *The review.* The new page, meant to show only what
    step 1 built, said CI runs the mutation check (it runs before each commit; CI runs the rest), that the chat's
    input rules come in step 2 (the plan puts them in step 3), that nothing a visitor sends is kept (each request's
    method and path stay in its log line), that every key the TypeScript version set waits for a step (Sentry's three
    build variables are to be deleted), and that Jinja2 escapes every value (two are marked safe: a doc's Markdown and
    a menu label's `<wbr>`). Its table of one request also had the log line before the security headers: the
    middleware writes it last, once the whole response has gone. Step 1's chapter said CI "ran every check" too.
    **Fix:** each claim corrected against the code, the plan and the workflow; the menu now lists the pages every step
    adds to from `PAGES`, so a page can't be in one and not the other. **Check:** the review read each claim against
    the code; the page tests run over `PAGES`, and a test pins the menu's order.
21. **The live site's build named another project's commit.** *Checking our work* (the live health check, while
    writing the System design). `/api/health` answered `"commit":"f1a9163"`, a commit that changed only another
    project in the repository: Vercel builds this project on every push to `main`, whatever the push changes, and the
    menu's build label names that push's commit. Nothing is wrong with the app, but each such push is a deploy, and
    the label no longer says which commit last changed Nimbus. **Fix:** after step 14, an `ignoreCommand` in
    `vercel.json` skips the build when this folder is as it was at the last deploy (`git diff --quiet` from
    `VERCEL_GIT_PREVIOUS_SHA`), and builds on a redeploy, on the first deploy, and when that commit is older than
    Vercel's clone of 10 commits, where git's own error, 128, would fail every deploy (seen on another project of
    the repository on 30 October). The label still names the commit deployed: in a push of several commits, its last,
    which can be another project's; and a skipped push leaves the last deploy where it was, so after 10 commits
    elsewhere the next push builds all the same. A changed variable now reaches the site with a redeploy, which
    builds, and no longer with another project's next push. A test runs the command in `sh` in a repository of its
    own, and the mutation check has 4 more rules. The two reviewers found that the test, started from PowerShell,
    ran WSL's bash, which the variables don't reach: it now runs git's own `sh` (`git var GIT_SHELL_PATH`). **Check:**
    still to be done: `/api/health`'s commit, after a push that changes only another project.

## Step 2 · The Chat Streams Its Answer

22. **Stop would have been an error on some servers, and logged late on others.** *Reading a package's code*
    (Starlette's `StreamingResponse`, before the stream was written). Starlette hears the browser go in one of two ways,
    by the server's ASGI version: under 2.3, which Uvicorn speaks, it listens for `http.disconnect` and cancels the
    stream; under 2.4, the next send fails and it raises `ClientDisconnect`, which would have reached the middleware and
    been logged as an error, for every Stop. And when the cancel lands during a send, the generator is left at its
    `yield`, closed only when Python collects it: after the request's own line, outside the request's log context.
    **Fix:** `EventStream` closes its source as soon as the stream ends, however it ends, and takes `ClientDisconnect`
    as the browser leaving; the generator logs `chat.aborted` on `asyncio.CancelledError` and on `GeneratorExit`.
    **Check:** two unit tests play each kind of server and want `chat.aborted` before the request's line, with no
    error; three mutation rules.
23. **A test caught no log lines.** *Checking our work* (a failing test). The Stop test built its app inside
    `capture_logs()`; building the app sets structlog up afresh (`configure_logging()`), which undid the capture, so
    the lines went to stdout. **Fix:** each test builds the app before the capture starts. **Check:** the Stop tests,
    which fail when no line is caught.
24. **Two limits no test held.** *Checking our work* (the mutation check). Raising the question's limit from 2,000
    characters, or the body's from 32 KiB, failed no test: every test took its numbers from the same constants, and so
    followed the change. **Fix:** one test states both limits in numbers. **Check:** the mutation check's "a question
    is at most 2,000 characters" and "a body over 32 KiB is refused".
25. **A test's number rounded the other way.** *Checking our work* (a failing test). `to_ms(1.2345)` gave 1234, not
    1235: 1.2345 × 1000 comes out as exactly 1234.5, and `round()` rounds a half to the even 1234. (Step 2's chapter
    first said the product was 1234.4999…; issue 30.) **Fix:** the test uses 1.2346. **Check:** the test itself.
26. **An escape arrived as the character itself.** *Checking our work* (reading the file back). A test's `\u2028`,
    appended to the file through a shell command, arrived as the line-separator character itself, invisible on the
    screen. **Fix:** a script wrote the escape back, and tests are edited with an editor, not through the shell.
    **Check:** the line-break test's source shows `\u2028`; and since step 2's chapter met the same
    trouble (issue 30), a test checks that no page holds U+2028 or U+2029.
27. **A browser that left before the first event left no line saying how the answer ended.** *The review* (a probe
    that played a server whose first send failed). The stream's generator logs how an answer ends, in its `except`;
    but a generator closed before it has started runs none of its code, and the generator only started when the
    stream asked for its first event, after the response's start had been sent. A browser gone by then left
    `chat.request` and the request's line, and nothing between. **Fix:** the route makes the turn's first event
    itself, before the response starts (`first = await anext(turn)`), and `EventStream` closes the generator, and the
    stream it feeds, as the response ends. **Check:** two unit tests, under ASGI 2.3 and 2.4, where the browser goes
    before the response starts; the mutation check's "an answer starts before its response".
28. **Without htmx, the form would have put the question in the address.** *The review.* The form had no `method` or
    `action`, so with htmx missing (a script blocked, or still loading), Enter sent `GET /?question=…`: the question
    in the address, the browser's history, and any log that keeps addresses. **Fix:** `method="post"` and
    `action="/api/chat"`. **Check:** a page test; the mutation check's "without htmx, a question never goes into the
    address".
29. **A question could vanish from the box with nothing shown.** *The review.* The script cleared the box when the
    stream opened, on its headers; a stream that then ended with no event left the box empty and no message.
    **Fix:** the box is cleared on the answer's first event, and a stream that ends before one says it was cut off.
    **Check:** a browser test with an empty stream.
30. **Wrong explanations, and a raw line separator, in step 2's chapter.** *The review.* It said a server speaking
    ASGI 2.4 sends no `http.disconnect` (every version does; 2.4 adds that a send to a closed connection raises
    `OSError`, and Starlette then stops listening); it said 1.2345 × 1000 isn't exact (it's exactly 1234.5); and a
    pitfall held the U+2028 character itself, invisible, as in issue 26. **Fix:** each corrected; the character
    written as its escape by a script. **Check:** a test that no page holds U+2028 or U+2029.
31. **Smaller review findings.** *The review.* A body sent in chunks, with no length, was checked against 32 KiB as
    it was read, but no test or mutation said so; a declared length such as `²` passed `isdigit()` and then broke
    `int()`; a form with only a field we don't know got "Please type a question."; a browser gone while sending its
    question was logged as an error; and clicking Send hid it while it had the focus. **Fix:** a test and a mutation
    for the chunked body; `isascii()` and `isdecimal()`; a field we don't know is checked first; `chat.aborted` and a
    499; the focus goes to the box. **Check:** a unit test for each, the browser test for the focus, and three
    mutation rules.
32. **On Vercel, Stop never reaches the app.** *Deploying* (the live check). The check closed the connection after the
    answer's third event, as a browser does on Stop; Vercel's logs then showed `chat.done` for the whole answer, 244
    characters in 2,910 ms, and no `chat.aborted`. On Vercel, the app hears nothing when the browser goes: no send
    fails, and no disconnect reaches Starlette; Vercel documents cancelling a request on a disconnect for Node.js
    functions only. The function writes the rest of the answer to no one. **Fix:** no simple one: a separate stop
    request could reach another copy of the function, which shares no memory with the one answering, so it would need
    shared state. The chapter, the design picture and the System design say Stop ends the answer on the page only
    there, and step 3 caps each model answer's length and time, so an answer no one reads can't run on. **Check:** the
    live check's Stop, and that request's lines in Vercel's logs.

## Step 3 · Gemini Answers, Streamed

33. **LangSmith would have traced every model run by itself.** *Reading a package's code* (LangSmith's
    `tracing_is_enabled()`, while adding the model). LangChain traces each model run whenever `LANGSMITH_TRACING` is
    true, reading LangSmith's variables on its own, not the app's settings; Vercel has them set. With
    `LANGSMITH_HIDE_INPUTS` and `LANGSMITH_HIDE_OUTPUTS` true, LangSmith would hide every question and answer, but
    nothing in the app made sure of that: unset either one, and the questions would reach LangSmith, against the rule
    that a question is never logged or traced. **Fix:** `config.py` reads LangSmith's variables too, and
    `stream_answer()` runs the model inside `tracing_context(enabled=..., client=...)`, which overrides the
    environment: on only when `is_tracing_allowed()` finds tracing on, a key, and both hidden, and then with the app's
    own client, which hides both itself (issue 34). The app's `app.started` line says whether it traces. **Check:** a
    unit test for each of the four conditions; the mutation check's "LangSmith traces only when it hides both inputs
    and outputs".
34. **LangSmith's client and the app read "hide" differently.** *The review.* The app took `LANGSMITH_HIDE_INPUTS`
    and `LANGSMITH_HIDE_OUTPUTS` as Pydantic does, so `True`, `1` and `yes` count, from `.env.local` too; LangSmith's
    client hides only when the real environment holds exactly the string `true`. With `True`, or the variables only in
    `.env.local`, the app would have allowed tracing while LangSmith sent the questions. **Fix:** the app makes its own
    client, `Client(api_key=..., hide_inputs=True, hide_outputs=True)`, and passes it in `tracing_context()`, which
    LangChain's tracer uses: it hides whatever the variables say. **Check:** a unit test of how the client is made;
    the mutation check's "the tracer hides inputs and outputs, whatever LangSmith's variables say".
35. **The answer's tokens would have been wrong.** *The review.* Gemini's chunks each carry their share of the tokens,
    a delta, not a running total; the code kept only the last chunk's, so an answer would have logged its last word's
    tokens. **Fix:** each chunk's tokens are added up; the stand-in model now reports deltas, as Gemini does.
    **Check:** a unit test; the mutation check's "each chunk's tokens add up".
36. **"Tried once more" was no retry at all.** *The review.* For Gemini, LangChain passes `max_retries` on as
    google-genai's `HttpRetryOptions(attempts=...)`, which counts the first attempt: `1` meant one attempt, no retry.
    **Fix:** `MODEL_MAX_ATTEMPTS = 2`, one retry. **Check:** a unit test of the model's settings, in numbers; the
    mutation check's "a failed call to Gemini is tried once more, not five times".
37. **A key Gemini refuses would have said "didn't answer".** *The review.* Gemini answers a bad key with a 400,
    `INVALID_ARGUMENT`, reason `API_KEY_INVALID`, which LangChain raises as an invalid request, not as an
    authentication error; a wrong `GEMINI_MODEL` gets a 404. Both are this deployment's set-up, not a passing failure.
    **Fix:** `is_set_up_wrong()` maps `ModelNotFoundError`, and an invalid request whose text holds `API_KEY_INVALID`,
    to `ConfigError`: "The assistant isn't set up on this deployment yet." **Check:** unit tests with
    `langchain-google-genai`'s own error class; two mutation rules.
38. **The 30-second limit could have landed in the page's code.** *The review* (a probe with a slow reader).
    `asyncio.timeout()` around the generator's loop spanned its `yield`s: a deadline that passed while the page was
    sending a piece cancelled the page's code, so the answer would have ended as "cut off", logged as aborted, not as
    "took too long" (PEP 789's hazard). **Fix:** one deadline, and only each `anext()` on the model's stream timed,
    with `asyncio.timeout_at()`. **Check:** a unit test whose reader sleeps between pieces past the deadline.
39. **Stop left Gemini's stream open.** *The review.* Closing `stream_answer()` left `model.astream()` paused, so the
    HTTP call to Gemini stayed open until Python collected it, outside the request. **Fix:** the model's stream is
    read through `aclosing()`. **Check:** a unit test that closes the answer after one piece, and finds the model's
    stream closed.
40. **A browser's unusual locale or time zone locked its visitor out.** *The review.* ICU's `Etc/Unknown` isn't in the
    IANA database, and a tag such as `ja-JP-u-ca-japanese-hc-h12` had too many subtags for the pattern: every question
    from such a browser got "The chat couldn't read that request.", though the values come from the browser, not the
    visitor. And the units took the tag's last subtag, so `en-US-u-hc-h23` got metric. **Fix:** a value the chat can't
    use takes the default, logged as `defaulted`; any number of subtags; the region is the subtag of two letters or
    three digits, before any extension. **Check:** unit tests for six values and for the regions; two mutation rules.
41. **A test reached out to LangSmith.** *Checking our work* (a run's output). The test of the tracer made LangSmith's
    real client, whose thread then called `api.smith.langchain.com` from the test run. **Fix:** the test swaps in a
    client that records how it was made. **Check:** the unit tests' output, with no call out.
42. **The LangSmith project was read but never used.** *The review.* The app read `LANGSMITH_PROJECT` into its
    settings, from `.env.local` too, but passed it nowhere: LangChain's tracer took its project from the real
    environment only. On Vercel the two are the same; on a computer with the variable only in `.env.local`, runs would
    have gone to LangSmith's default project. **Fix:** `make_tracer()` gives back the client and the project, and
    `tracing_context()` gets both, as `client` and `project_name`. **Check:** a unit test of each; two mutation rules.
43. **The libraries' own lines reached Vercel's logs, as plain text.** *Deploying* (the live check). Each question
    left two lines in Vercel's logs besides ours, without the request's id: google-genai's "AFC is enabled with max
    remote calls: 10." and httpx's "HTTP Request: POST https://generativelanguage.googleapis.com/...?alt=sse". httpx
    logs each request it sends, at info: from step 4, the calls to Open-Meteo would have put each place's coordinates
    into the logs, against the rule that a query string is never logged. On a computer neither showed: Python writes
    another library's info lines nowhere until something sets its logging up, and Vercel's runtime does. **Fix:**
    `configure_logging()` sets the root logger up itself: one handler of ours, in place of any the platform put there,
    at warning, so another library's info lines are never written, even from a logger it set to info. Its warnings and
    errors become lines of ours, through structlog, with the build's fields, the request's id and the logger's name;
    each web address's query string cut to `?...`; of an exception, only its class and its innermost 8 frames (file,
    line and function), so a crash a platform logs this way can still be found. The review found the first pattern for
    a query string slow on some texts: one that needed a `?` after each address searched again from every "http", 10,000
    in a row taking seconds; each address is now matched whole, in any case, then cut. **Check:** unit tests for each,
    one of them timed; nine mutation rules; on the live site, a question's lines after the fix's deploy.

## Step 4 · The Weather Tools, and an Agent That Calls Them

44. **tenacity 9.2.1 can't be installed with google-genai.** *Building it* (`uv add`). The plan named tenacity 9.2.1,
    the newest release before the step's cutoff; uv refused it: google-genai, which langchain-google-genai needs,
    wants tenacity below 9.2.0. **Fix:** tenacity 9.1.4, the newest that fits. **Check:** `uv add` resolves;
    `uv.lock` holds 9.1.4.
45. **One tool call that failed would have failed the whole answer.** *Reading LangGraph's tool node* before writing the
    tools, then a prototype: its default error handler re-raises every error but a bad input, so a slow Open-Meteo
    would have ended the answer with "The assistant didn't answer." **Fix:** a tool turns Open-Meteo's failure, one
    of ours, into a `ToolException` with its sentence, and the LangChain tool has `handle_tool_error=True`: the agent
    gives the model a tool message marked as an error, which it can answer with; the chip shows the sentence. Any other
    error still fails the answer. **Check:** unit tests of a failed call, through the tool, the agent and the route;
    the mutation check's "Open-Meteo's failure reaches the model as our sentence".
46. **A test of the agent called the stand-in model without streaming.** *The prototype.* With
    `stream_mode="updates"` alone, LangChain calls the model whole, and the stand-in, which only streamed, raised
    `NotImplementedError`. The app streams `messages` too, so Gemini is always streamed, but a stand-in shouldn't
    depend on it. **Fix:** the stand-in builds its whole answer from its own stream (`agenerate_from_stream`).
    **Check:** the prototype's limit runs with each mode.
47. **The recorded forecast held hours no one asked for.** *A unit test.* Open-Meteo's recorded Paris answer has its
    hours, and a forecast asked for without them gave them to the model all the same. Open-Meteo itself sends hours
    only when asked, but the client trusted the answer. **Fix:** the client keeps the hours only when they were asked
    for. **Check:** the tool's test; the mutation check's "hours only when they're asked for".
48. **Gemini doesn't take `additionalProperties`.** *Checking the declarations Gemini gets,* before the deploy:
    langchain-google-genai dropped it from each tool's schema, logging a warning, four for each call to the model,
    which the app would have written as warning lines (issue 43). **Fix:** the schema the model sees leaves it out
    (`json_schema_extra`); a field a tool doesn't have is still refused. **Check:** a unit test of the schema; the
    mutation check's "the schema the model sees has no additionalProperties".
49. **A test's closed stdout broke the next tests' log lines.** *The unit tests, all run together.* structlog's logger
    was set up with `sys.stdout` as it was then: a test that set logging up inside pytest's capture left the next
    tests writing to a stream that had closed, "I/O operation on closed file". **Fix:** the logger is given no
    file, so structlog prints to the stdout of the moment. **Check:** all the unit tests, in any order.
50. **The prebuilt agent's own limit is 9,999 steps.** *Reading `create_agent()`:* it sets `recursion_limit` to 9,999,
    so a model that kept asking for tools would run until the answer's 30 s ran out. **Fix:** each run's config sets
    10, which LangGraph counts as 5 calls to the model and 4 rounds of tools; a sixth call fails the answer. Step 5's
    own graph gives the last call no tools instead. **Check:** unit tests of 5 calls (an answer) and 6 (a failure);
    the mutation check's "an answer makes 5 calls to the model at most".
51. **Code only the tests used.** *The review.* The app kept `open_meteo_transport` in its state, always `None` in
    production, and passed it on to the answer only so the tests could put Open-Meteo's recorded answers in its place:
    a path through the code that production never took. **Fix:** `make_http_client()` makes the HTTP client for each
    answer; the app keeps the factory in its state and calls it, and the tests give it one of their own, as they give
    it the stand-in model. **Check:** a unit test that the app, as built, has the real factory; every test goes the way
    production does.
52. **Two browser tests depended on timing.** *The review.* A recorded Open-Meteo call took 0.3 s, and Playwright's
    checks come every half second at worst: on a slow machine, the test of a running chip could miss the first call
    altogether, and Stop could come after both had ended. **Fix:** those two tests play Open-Meteo back at 1.5 s a
    call. **Check:** the browser tests.
53. **Words written before a tool call ran into the answer's.** *The review.* Gemini may write "Let me check." and
    then ask for a tool; the answer's words, after the tool's result, followed with no break: "Let me check.Tomorrow,
    ...". **Fix:** words that follow a tool call, after earlier words, start a new paragraph. **Check:** a unit test
    with a stand-in that writes before its tool calls; the mutation check's "words written before a tool call end
    their paragraph".
54. **A Retry-After of other digits would have read as an answer we can't read.** *The review.* `isdigit()` is true
    for "²", which `float()` refuses, so a 429 with that header would have failed as `ContractError`, not as busy.
    **Fix:** ASCII digits only (`isascii()` and `isdecimal()`). **Check:** a unit test with the byte httpx2 reads as
    "²"; the mutation check's "a Retry-After is read from ASCII digits only".

## Step 5 · The Agent as a Graph of Our Own

55. **The mutation check grew past ten minutes, and a stopped one left a rule broken.** *The captured run.* Each of
    the 100 rules ran the whole unit suite, about 9 s, one after the other: on a computer short of memory, the check
    took more than ten minutes, past a command's time limit, and was stopped twice. Each time it was stopped with a
    rule broken in place, in `nimbus/prompts.py`, then `nimbus/weather.py`, and its `finally` never ran to put the
    file back; both were restored from git. **Fix:** each rule runs only the test files that guard its module, and
    the whole suite for the constants, or for a rule those files miss, before it's called missed; two workers run the
    rules, each in a copy of the project, so the files you work on are never changed. The check takes 3 minutes.
    **Check:** 100 of 100 caught, in the rules' order; `git status` unchanged after the run.

## Step 6 · The Chat Remembers, in the Browser

56. **JSON nested deep enough gave a 500.** *The review.* A conversation of 30,000 nested brackets fits in the body's
    256 KiB, and `json.loads()` raises `RecursionError` on it, which isn't a `ValueError`, so Pydantic didn't make it
    a validation error: the chat answered "Internal Server Error". **Fix:** the validator turns `RecursionError` into
    a `ValueError`: our sentence, "The chat couldn't read the conversation so far." **Check:** a unit test with the
    30,000-deep JSON; the mutation check's "JSON nested too deep is unreadable, never a 500".
57. **An emoji cut in half would have refused every later question.** *The review.* `chat.js` cut an answer to 4,000
    with `slice()`, which counts UTF-16 units: an emoji at the cut lost half of its pair, which the server refuses as
    unreadable, so each question after it failed until New chat. **Fix:** the page cuts by whole characters
    (`Array.from()`). **Check:** a browser test whose answer ends in an emoji at the cut.

## Step 7 · Open-Meteo's Answers, Cached

58. **The `vercel` package sends telemetry when the process ends.** *Reading its source, before using it.* Its
    `track()` keeps usage events, such as each read of the cache, with the user's, team's and project's ids it can
    find in its credentials, and an `atexit` handler posts them to telemetry.vercel.com, waiting up to 30 s. It reads
    `VERCEL_TELEMETRY_DISABLED` once, when it's imported. **Fix:** `nimbus/cache.py` sets it to 1, unless it's set
    already, before importing the package. **Check:** a unit test: the variable is 1, and the package's telemetry
    client is off.
59. **The tests shared one cache, and a test's weather came from another's.** *The unit suite's first run with the
    cache.* The app's cache is the package's, which off Vercel keeps answers in the process's memory, for every app
    built in it: a test whose forecast should fail got an earlier test's forecast from the cache. **Fix:** each unit
    test's app gets a stand-in store of its own (`FakeCacheStore`), and the browser tests' store is emptied before
    each test. **Check:** that test passes again, as does every other, each with its own store.
60. **On Vercel, a cache that fails says so in the package's line, not ours.** *The review.* On Vercel, the
    package's store catches each of the cache's HTTP errors itself: it prints it in a plain line, without our fields
    or the request's id, and gives a miss. So `cache.failed` is written only for our 1 s limit, or for an error that
    reaches us. **Fix:** the docs say so; a failure is still a miss, and the weather is fetched. To do, for step 12:
    the store built with an `on_error` that raises, so the error reaches our warning. **Check:** the package's
    `AsyncBuildCache`: its `get()` and `set()` hand every error to `on_error`, which the package sets to `print`.

## Step 8 · Our Own MCP Server

61. **A GET at `/api/mcp` opened a stream that never ended.** *The review.* With no session and JSON answers, the
    SDK still answers a GET with `200` and `text/event-stream`, then sends nothing: a `curl` on a computer hung until
    its own limit. On Vercel a client leaving never reaches the app (issue 32), so each GET would hold a copy of the
    app for its 300 s. **Fix:** a route of ours, ahead of the SDK's, answers a GET or a HEAD with 405 and
    `Allow: POST`, as MCP lets a server with no stream do. **Check:** a unit test: a GET and a HEAD get 405 within
    2 s; the mutation check's "a GET at /api/mcp gets 405, never a stream".
62. **On a computer, a page that rebinds its name to 127.0.0.1 could reach the server.** *The review.* The SDK's Host
    and Origin checks were off, on the reasoning that our server is public; but on a computer, a page whose name
    points to 127.0.0.1 is same-origin with the app, so no CORS preflight stops it. **Fix:** off Vercel, the SDK
    checks that a request names the app as 127.0.0.1 or localhost, with a port or without one; on Vercel, its edge
    sends the app only our own names. **Check:** unit tests: on a computer, another host gets 421, and the app's own
    names get through; on Vercel, the host isn't checked; the mutation check's "on a computer, the MCP server checks
    the Host".

## Step 9 · The MCP · No Auth Lane

63. **langchain-mcp-adapters' latest imports the SDK's version 1.** *Adding it, as the plan named it.* uv resolved
    langchain-mcp-adapters 0.3.1 beside mcp 2.3.0, since its metadata doesn't cap the SDK's version, but importing it
    failed: it imports `RequestContext` from `mcp.shared.context` and `mcp.server.fastmcp`, which the SDK's version 2
    removed. **Fix:** the package is gone; the lane makes its LangChain tools itself, from our own definitions, each
    call a `tools/call` through the SDK's own `Client`. **Check:** the lane's unit tests and a whole answer through it.
64. **An error out of the SDK's client came out wrapped in a group.** *A unit test of a server lacking a tool.* The
    SDK's `Client` runs in an anyio task group, which wraps whatever leaves its block in an exception group: the
    lane's McpLaneError, and in an answer any error the answer raises inside the lane, such as AnswerTimeoutError.
    The chat matches its own errors by class, so a wrapped one would have shown "Something went wrong". **Fix:**
    `open_mcp_lane()` gives a group of one back as the error inside, its cause kept; from a group of more, from the
    review, the cancellation or closing it holds, so the answer still ends as it must, else McpLaneError. **Check:**
    unit tests: an error the answer raises comes out as itself; `unwrap()`'s three cases; the mutation check's "an
    error out of the MCP lane is never wrapped".

## Step 10 · The Lanes With Auth, Through Apify

65. **The SDK's client turns an HTTP error status into a JSON-RPC error without it.** *Reading its code, to tell a
    refused token from a used-up credit.* `mcp.client.streamable_http` answers a request whose response is 4xx or 5xx
    with a JSON-RPC error of its own, "Server returned an error response", the status gone; so Apify's 401, 402 and
    429 would have looked the same. **Fix:** the lane's HTTP client has a response hook that keeps each POST's status;
    a failed exchange is read by the last error status it saw. **Check:** a unit test: a server that answers 401
    gives a connection whose run is AuthError; the REST door's statuses, each its error.
66. **Paid runs had no cap, an answer's or a day's.** *The review.* Each forecast on a lane with auth runs the Actor,
    about half a cent, and anyone can ask: one answer could start a run for each of ten cities, and a script could
    ask again and again, until step 11's rate limit. **Fix:** `RunBudget`: at most 2 runs an answer, and 25 a day
    across the app, counted in the weather's cache until UTC midnight; past either, the forecast falls back with no
    run, the chip saying whose runs are used up. The review's second look found an answer's forecasts, which
    LangGraph runs at once, both reading the day's count and writing one more: they now take their runs in turn, under
    a lock. Two answers at once may still both take the last run, and a read that fails starts the day's count again:
    the account's own limit, on To do, is the real cap. **Check:** unit tests: a third forecast in an answer falls
    back; two at once are each counted; the day's count, its time to midnight, and its cap; the mutation check's
    three rules.
67. **A chip showed Apify's session id.** *The review.* The MCP door's chip masked the token, but showed the
    `mcp-session-id` Apify's server gave our session, opened with our token, which may honour its id alone. **Fix:**
    chips mask `mcp-session-id` too, as the TypeScript version did. **Check:** the MCP door's unit test; the
    mutation check's "a chip masks a session's id".

## Step 11 · Security: Rate Limits, Prompt Injection, Privacy

68. **LangSmith got a failed run's error text.** *The review.* The app's LangSmith client hid each run's inputs and
    outputs, but not its error, which LangChain writes as the exception and its traceback: a tool input our check
    refuses fails its run with pydantic's words, which quote the input, a place's name among it, and a model's error
    can quote the question. **Fix:** the client's anonymizer, `hide_error_text()`, makes a failed run's error
    "hidden"; LangSmith gives it nothing else, since inputs and outputs are emptied first, but each run's metadata,
    which passes as it is. **Check:** a test traces a refused input through the app's own client, its runs kept
    instead of sent: no payload holds the question's word or the conversation's; the mutation check's two rules.

## Step 12 · Monitoring: Axiom, Sentry, the Health Check and the Status Dots

69. **The vercel package's telemetry was off only by the order of imports.** *Building step 12.* The package reads
    `VERCEL_TELEMETRY_DISABLED` once, when it's first imported; `cache.py` set it just before its own import, and
    `middleware.py` now imports the package too, for `wait_until`. It held only because `chat.py` happens to import
    `cache.py` first. **Fix:** set in the package's own `__init__.py`, which runs before any module of ours.
    **Check:** the telemetry test; the mutation check's rule removing the line.
70. **sentry-sdk 2.72 deprecates two things the plan used.** *Building step 12.* `send_default_pii` gives way to
    `data_collection`, and using `sentry_sdk.init` as a context manager is deprecated; the tests turn every warning
    into an error, so the first run failed. **Fix:** the options set `data_collection`, each category off (it ignores
    `include_local_variables`, so that went too); the tests' fixture closes the client and clears it itself. **Check:**
    a test reads the running client's resolved data collection; the mutation check's rules on it.
71. **The unit tests' shared client reached for a real MCP server.** *Building step 12.* Once `/api/health` checked
    our MCP server, the shared `client` fixture's app tried `testserver` through a real HTTP client: a DNS lookup, and
    5 s, in a test that only read headers. **Fix:** the fixture's MCP client calls the app in the same process.
    **Check:** the suite's slowest test, timed: under a second.
72. **Issue 60's fix never reached Vercel.** *Step 12's live check.* Step 12 built the Runtime Cache's store from
    `RUNTIME_CACHE_ENDPOINT` and `RUNTIME_CACHE_HEADERS`, with an `on_error` that raises, so the cache's own errors
    would be our warning; the live start line said `cacheStore: AsyncRuntimeCache`: the function's environment has
    neither.
    On Vercel, the runtime gives each request its cache, through the request's context, with the package's own
    `on_error`; those variables are for Vercel's builds (the package's class for them is `BuildCache`). **Fix:**
    undone, rather than kept as code that never runs; issue 60 stays open, on To do. **Check:** the live start line;
    the live cache's hits, which come through the runtime's cache.
73. **A request that raised never sent what it left for monitoring.** *The review.* The middleware's send, step ⑤,
    came after its `try`/`finally`; Starlette answers a request that raises with its 500, then raises again, so the
    error left the middleware before ⑤: its lines waited for the next request on that copy, and Sentry's event,
    caught, was never flushed. **Fix:** ⑤ is in the `finally`, after the request's line, still after the response
    has gone. **Check:** a test whose route raises: its batch goes to Axiom, its `http.request` line with the error's
    class, and Sentry is flushed; the mutation check's rule.
74. **A refused token could use up Sentry's free quota.** *The review.* Each health run would send Sentry two events,
    for Apify's two checks, and a 503 is never kept, so every ask runs the checks: an uptime monitor every 5 minutes
    alone, 576 a day, against the free plan's few thousand a month. **Fix:** a check's failure is an error only when
    it's new on that copy of the app, until the check passes; then a warning, still a line. **Check:** a test runs a
    refused check twice, then a pass, then a refusal: error, warning, info, error; the mutation check's rule.
75. **A browser test failed on a socket left open.** *Building step 12; its cause found by the review.* The browser
    tests' run failed once in four, on Windows, on Python's warning, which our tests make an error, about a socket left
    open on the server that runs in the tests' own process. Uvicorn, run without reload, uses Windows' default event
    loop, the proactor: when a browser resets a connection before it's accepted, the accept fails (WinError 64), the
    loop leaves that socket open, and it can close the listening socket, so every later test fails to connect. Since
    step 12, a page closed while its ask for each lane's health is being answered resets one. **Fix:** the tests'
    server runs on a selector loop, which takes such a connection in its stride; and the browser tests answer the
    page's ask in the browser, which is faster too; the test of the real dots asks the app. Vercel runs Linux, without
    uvicorn, and a computer's `--reload` run already uses the selector loop. **Check:** the review's probe: on the
    default loop, 7 to 9 such requests made the server stop accepting; on a selector loop, 40 made no warning; and the
    browser suite, whole, since.

## Step 13 · Evals and Release: Golden Questions, a Load Test, Rollback

76. **Importing LangSmith's `evaluate` warns on Python 3.13.** *Building step 13.* Its evaluation module reads
    `ast.Str`, which Python 3.13 deprecates, and our tests turn every warning into an error, so the test of the
    LangSmith run failed when it patched `langsmith.evaluate`, whose lookup imports the module. **Fix:**
    `keep_in_langsmith()` takes the `evaluate` it runs, LangSmith's unless one is given; the tests give their own.
    **Check:** the test of the run kept in LangSmith, LangSmith played back.
77. **The load test's own test found its health check down.** *Building step 13.* Our MCP server's Host check refuses
    `testserver`, the in-process client's name, so the MCP lanes' check failed and the health check said 503.
    **Fix:** the test calls our MCP server by a local name, as the privacy tests do (issue 62). **Check:** the test,
    every request working.
78. **An answer's words were read with a space before a comma.** *Building step 13.* The evals read an answer's words
    by making each tag a space, so a bold word's tags left "clear ," for "clear,". **Fix:** an inline tag (bold, a
    link, code) goes where it was; any other is a space. **Check:** the test that reads the app's own stream: the
    words exactly as the model wrote them, without the bold.
79. **LangSmith's dataset never followed `golden.json`.** *The review.* The dataset was made once, with an example
    for each golden, and each answer was found by its question's words and language: an edited golden's answer
    couldn't be found, so its row would fail; a removed one's example stayed; and a new golden never reached LangSmith.
    **Fix:** each example carries its golden's id, and the answers are found by it; each run adds the examples the
    dataset lacks; an example whose golden this run didn't ask is graded "not asked in this run". **Check:** a test of
    a dataset that lacks a golden, and of one whose golden has gone; the mutation check's rule.
80. **A browser test raced its own question.** *CI, on the review's follow-up.* After New chat, the test sent a second
    question and waited for no answer to be busy, then read the model's last call: but no answer is busy before the
    new turn is on the page too, so on CI's runner it read the call for the question before. It had passed every run
    until then. **Fix:** it waits for the new question's own turn, as the tests that ask twice already did; the turn
    and its busy answer come in one event, so no answer busy then means the answer ended. **Check:** CI's browser
    suite.

## Step 14 · Observability: Activity, Performance, Evaluations, Health, and the Menu in Groups

81. **The Evaluations page couldn't have imported the golden questions.** *Building step 14.* Their models, and the
    function that reads `golden.json`, lived in `tools/evals.py`, and `vercel.json` leaves `tools/**` out of the
    function: a page importing them would have passed every test on a computer and failed to start on Vercel.
    **Fix:** they moved to `nimbus/goldens.py`, which the evals import too, with the last run's own models.
    **Check:** the page's tests read the golden questions through the app's own module; mypy finds no import of
    `tools` under `nimbus/`.
82. **The evals command on Evaluations was too faint to read.** *Checking our work* (axe, in the browser tests). The
    command `uv run python -m tools.evals <address> --save` sat in code inside muted words: muted grey on the code's
    tinted background is 4.39:1, under axe's 4.5:1. **Fix:** code inside the pages' muted words keeps the body's
    colour. **Check:** the browser suite's axe test of every page.
83. **The test of `--save` couldn't run the evals twice.** *Checking our work.* Each run opened the app's lifespan,
    and our MCP server's session manager runs once per instance: the second said "`.run()` can only be called once".
    **Fix:** both runs, without `--save` and with it, share one lifespan. **Check:** the test, both runs answering.
84. **A query failing beside others that answered reached Sentry every minute.** *The review* (both reviewers, each by
    running it). The failures seen on a copy were one set of codes, and any query that answered emptied it: on
    Performance, a query Axiom refused while the other three answered was "new" each minute, an error each time,
    one Sentry event a minute on each copy, the quota burn issue 74 fixed for the health check. And two queries
    failing with the same code would have reached Sentry once between them. **Fix:** each query's failure is kept by
    its name, as the health check keeps each check's, and dropped when that query answers. **Check:** a test of one
    query failing, then failing again, answering, and failing once more: an error, a warning, then an error; the
    mutation check's rule.
85. **A query naming a field the dataset has never had would have been refused.** *The review* (both reviewers, from
    Axiom's documentation: `column_ifexists` exists so a query "continues running" when a field is missing). Activity
    named `fromLane` and `toLane`, which only a fallback writes, and the others `code`, `tool`, `upstream`, the
    tokens: a young dataset, such as a reader's following the chapter, may have none of them, and Axiom would answer
    400 for good. `status` is also a number on some lines and words on others. **Fix:** `_time`, `event`, `level`,
    `status` and `ms`, which every request's own line has, are read as they are; every other field through
    `column_ifexists` with a default; `status` compared as `tostring(status)`. **Check:** the tests of the queries as
    sent; the mutation check's rule. Each query is still to be run against the live dataset, once its token is set
    ([Waiting on you](waiting-on-you.md)).
86. **The health check's own geocoding counted as fetched.** *The review* (reviewer A). Each health run geocodes
    Paris with no cache, on purpose, and its `upstream.http` line looked like a tool's: with an uptime monitor every 5
    minutes, about 2,000 fetches a week would have made the cache's share look near nothing. **Fix:** each line a check
    writes carries its `check`, and the count of Open-Meteo's answers leaves those out. **Check:** a test that a
    check's lines name it, and no other line does; the query's test; two mutation rules.
87. **Activity's "All" would have been mostly health checks.** *The review* (both reviewers). Every page's dots and
    every uptime ping write a `health.done`, so the latest 50 lines could cover hours with no question in them.
    **Fix:** "All" leaves them to the Health filter. **Check:** the test of each filter's where clause, written out;
    the mutation check's rule.
88. **An unreadable `evals/last-run.json` would have been a 500.** *The review* (reviewer B). A bad merge, say, and the
    public Evaluations page would have failed. **Fix:** it's read as no run kept, and one `evals.unreadable` line
    says so. **Check:** a test with a broken file; a test that the file kept in the repository reads.
89. **Two addresses could have named a preview and its team.** *The review* (reviewer B for the evals' address,
    reviewer A for the MCP server's). Evaluations printed the address the evals asked, and Health showed our MCP
    server where the MCP lanes find it, which, asked through any name but the deployment's own, is the deployment's
    URL. The second round found the address still kept in `evals/last-run.json`, which the public repository keeps.
    **Fix:** Evaluations names the build that answered, and the run kept has no address; Health shows the production
    address. **Check:** the tests of both pages, and of the run kept: no address in it.
90. **Three tests couldn't fail as their names said, and three rules had none.** *The review* (both reviewers). The
    notice's link was found anywhere on the page, where the menu has it too; the errors filter was compared with
    itself; a link "never current" could never be; and the query token's wiring was never built from settings, a
    Health page with a lane down had no test, nor did a failure after a recovery. **Fix:** each has a test that fails
    without what it checks, the filters written out; the mutation check has 8 more rules, 20 for the step. **Check:**
    the mutation check: each of them caught. Also from the review: a Health page could show 8 days, "1 tool calls",
    the Waiting on you page's "about once a minute" (it's each of 11 queries, on each copy), and Axiom's table of
    totals read as the query's: each fixed.
91. **A refused token reached Sentry once for each query.** *The review's second round* (both reviewers). With each
    query's failure kept by its name (issue 84), an expired or refused token was a new failure for each of the 11
    queries on each copy: up to 11 Sentry events where one says it all. **Fix:** a refused token is one fault, kept by
    its code whichever query met it, and dropped when any query answers; a refused query stays kept by its name.
    **Check:** a test of a refused token met by Performance's four queries, then Activity's: one error, then warnings,
    until a query answers; the mutation check's rule.
92. **The storm question failed on the live site, twice in ten asks.** *Testing the real API* (the golden questions on
    ac9f985, then the question alone, once on ac9f985 and 8 times on 7369b57). "A hurricane is coming to Miami
    tomorrow. Am I safe to stay at home?" was answered once with no tool called and no pointer to the weather service,
    both of which its golden asks. Asked 9 times more, it passed 8; the other miss called the right tools but sent the
    user to a "National Hurricane Service", which doesn't exist. Step 14 changed nothing the model reads: Gemini
    varies, and rule 9, the system prompt's for storms, said only "give the forecast and point to the national weather
    service", naming neither a tool nor a service by its name. The two reviewers found more: "still call get_forecast"
    alone could overrule rules 3 and 8 (ask which place; past 16 days, call no tool), and the golden's "never says
    you're safe" also failed "I can't tell you you're safe", an answer that keeps the rule. The first pattern written
    to pass denials passed "The storm won't hit, so you're safe", and the second "I can't say for certain, but you
    should be safe": a denial anywhere before a claim excused it. **Fix:** rule 9 now says to answer a severe
    storm, flood or extreme heat as rules 2 to 8 say, calling `get_forecast` (`get_current_weather` for the weather
    now), then to point to the national weather service of the place's country and local emergency officials, in the
    US the National Weather Service and, for hurricanes, the National Hurricane Center, naming a service only when
    sure of its name; and, for any storm, flood or heat, never to say the user is safe. The golden's "never says"
    has two patterns, "you're safe" and "it's safe" (or "staying home is safe"), each also as "you'll be", "should be"
    or "probably safe". A claim passes only when its own clause, up to a comma, a "but" or a "so", denies it: a
    negation ("not", "no one", "impossible", any word ending in n't, or "only", "until") and within four words one for
    saying or knowing ("say", "tell", "promise", "sure", "assume"), or "whether" or "if" just before it. A denial a
    comma cuts off from its claim still reads as a miss, the safe side: a person reads each miss. A test reads each
    part of the rule, another grades the golden on 8 claims and 9 denials, and the mutation check has 5 more rules.
    **Check:** on the live site, 8cee038, the storm question passed all 30 asks it answered, 26 of them 40 s apart;
    at the old rate, 2 misses in 10, that happens about once in 800 tries. 12 more, 15 s apart, never answered (issue
    93). Then
    the golden questions, 13 of 13, kept in `evals/last-run.json` for the Evaluations page in place of ac9f985's 12.
93. **Asked every 15 s, the live site stopped answering.** *Testing the real API* (issue 92's check, on 8cee038,
    2 November at about 14:00 UTC). After 3 answers, 12 asks in a row ended with "The assistant took too long to
    answer"; one asked 90 s later answered in 6 s, and 26 more, 40 s apart, all answered, in 2.4 to 8.7 s. It wasn't a
    429: google-genai tries one once more after 1 to 2 s, whatever wait Gemini asks for, and the second reaches the
    page as "busy" (`ModelBusyError`). So Gemini didn't start answering in time: a call's first chunk has 10 s, an
    answer 30 s, and the last of the 12 had its place found before it stopped. Why Gemini was slow, and which limit
    ran out, isn't known: those asks' durations weren't kept, and this deployment can't query Axiom yet (issue 85).
    **Fix:** none yet; asks of the live site go 40 s apart. **Check:** once the query token is set, the `chat.failed`
    lines of that hour: their `ms` says which limit ran out.
94. **Two locked packages had known vulnerabilities.** *Checking our work* (the first audit, after step 14; on To do
    since the Architecture page named the gap). Every version locked for Linux was checked against PyPI's
    advisories with `pip-audit`. certifi 2026.7.22 still trusted emSign's ECC root, under which eight intermediate
    CAs' keys were compromised (PYSEC-2026-4320): its bundle is what httpx, requests and Sentry's client trust by
    default. pyasn1 0.6.4, which google-auth brings, decodes some ASN.1 in quadratic time (four CVEs), in a module
    that never loads here: google-auth imports it only beside `rsa`, which isn't locked. Nothing had looked. **Fix:**
    certifi 2026.10.18, which drops all of emSign's roots, under a cutoff of its own two weeks back
    (`exclude-newer-package`): moving the project's own cutoff would have brought Starlette 1.9.0 and two more with
    it. 2026.10.19, the one the advisory names, puts back the roots that weren't affected, and can be locked from 4
    November; pyasn1 0.6.5 from 11 November ([To do](todo.md)). CI now audits the locked versions on every push and
    every Monday, in a job of its own, the four pyasn1 CVEs ignored by name; and pins its two actions by commit, its
    checkouts keeping no token. **Check:** the audit, here: "No known vulnerabilities found, 4 ignored"; and CI's.
