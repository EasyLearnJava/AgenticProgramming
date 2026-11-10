# Issues and Fixes

Every technical problem met while rebuilding Nimbus in Python: what happened, how it was found, why, the fix, and the
check that now guards it, so it can't quietly come back. Most are small; the ones that were real bugs or holes will
also be told as stories at the top. *Found by* says how each surfaced: **checking our work** (a test, the type
checker, a mutation check, a screenshot), **the review** (the independent reviewer before each commit), **reading a
package's code**, **deploying**, or **testing a real API**.

## Step 1 Â· The Project, Its Pages and Its First Deploy

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
    078915f changed only CI's workflow, outside this folder: Vercel's status for Nimbus read "Canceled by Ignored
    Build Step", and `/api/health` still named 17045bf; 1de58df and 17045bf, which changed the folder, each built.

## Step 2 Â· The Chat Streams Its Answer

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
    1235: 1.2345 Ã— 1000 comes out as exactly 1234.5, and `round()` rounds a half to the even 1234. (Step 2's chapter
    first said the product was 1234.4999â€¦; issue 30.) **Fix:** the test uses 1.2346. **Check:** the test itself.
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
    `action`, so with htmx missing (a script blocked, or still loading), Enter sent `GET /?question=â€¦`: the question
    in the address, the browser's history, and any log that keeps addresses. **Fix:** `method="post"` and
    `action="/api/chat"`. **Check:** a page test; the mutation check's "without htmx, a question never goes into the
    address".
29. **A question could vanish from the box with nothing shown.** *The review.* The script cleared the box when the
    stream opened, on its headers; a stream that then ended with no event left the box empty and no message.
    **Fix:** the box is cleared on the answer's first event, and a stream that ends before one says it was cut off.
    **Check:** a browser test with an empty stream.
30. **Wrong explanations, and a raw line separator, in step 2's chapter.** *The review.* It said a server speaking
    ASGI 2.4 sends no `http.disconnect` (every version does; 2.4 adds that a send to a closed connection raises
    `OSError`, and Starlette then stops listening); it said 1.2345 Ã— 1000 isn't exact (it's exactly 1234.5); and a
    pitfall held the U+2028 character itself, invisible, as in issue 26. **Fix:** each corrected; the character
    written as its escape by a script. **Check:** a test that no page holds U+2028 or U+2029.
31. **Smaller review findings.** *The review.* A body sent in chunks, with no length, was checked against 32 KiB as
    it was read, but no test or mutation said so; a declared length such as `Â²` passed `isdigit()` and then broke
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

## Step 3 Â· Gemini Answers, Streamed

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

## Step 4 Â· The Weather Tools, and an Agent That Calls Them

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
    for "Â²", which `float()` refuses, so a 429 with that header would have failed as `ContractError`, not as busy.
    **Fix:** ASCII digits only (`isascii()` and `isdecimal()`). **Check:** a unit test with the byte httpx2 reads as
    "Â²"; the mutation check's "a Retry-After is read from ASCII digits only".

## Step 5 Â· The Agent as a Graph of Our Own

55. **The mutation check grew past ten minutes, and a stopped one left a rule broken.** *The captured run.* Each of
    the 100 rules ran the whole unit suite, about 9 s, one after the other: on a computer short of memory, the check
    took more than ten minutes, past a command's time limit, and was stopped twice. Each time it was stopped with a
    rule broken in place, in `nimbus/prompts.py`, then `nimbus/weather.py`, and its `finally` never ran to put the
    file back; both were restored from git. **Fix:** each rule runs only the test files that guard its module, and
    the whole suite for the constants, or for a rule those files miss, before it's called missed; two workers run the
    rules, each in a copy of the project, so the files you work on are never changed. The check takes 3 minutes.
    **Check:** 100 of 100 caught, in the rules' order; `git status` unchanged after the run.

## Step 6 Â· The Chat Remembers, in the Browser

56. **JSON nested deep enough gave a 500.** *The review.* A conversation of 30,000 nested brackets fits in the body's
    256 KiB, and `json.loads()` raises `RecursionError` on it, which isn't a `ValueError`, so Pydantic didn't make it
    a validation error: the chat answered "Internal Server Error". **Fix:** the validator turns `RecursionError` into
    a `ValueError`: our sentence, "The chat couldn't read the conversation so far." **Check:** a unit test with the
    30,000-deep JSON; the mutation check's "JSON nested too deep is unreadable, never a 500".
57. **An emoji cut in half would have refused every later question.** *The review.* `chat.js` cut an answer to 4,000
    with `slice()`, which counts UTF-16 units: an emoji at the cut lost half of its pair, which the server refuses as
    unreadable, so each question after it failed until New chat. **Fix:** the page cuts by whole characters
    (`Array.from()`). **Check:** a browser test whose answer ends in an emoji at the cut.

## Step 7 Â· Open-Meteo's Answers, Cached

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

## Step 8 Â· Our Own MCP Server

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

## Step 9 Â· The MCP Â· No Auth Lane

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

## Step 10 Â· The Lanes With Auth, Through Apify

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

## Step 11 Â· Security: Rate Limits, Prompt Injection, Privacy

68. **LangSmith got a failed run's error text.** *The review.* The app's LangSmith client hid each run's inputs and
    outputs, but not its error, which LangChain writes as the exception and its traceback: a tool input our check
    refuses fails its run with pydantic's words, which quote the input, a place's name among it, and a model's error
    can quote the question. **Fix:** the client's anonymizer, `hide_error_text()`, makes a failed run's error
    "hidden"; LangSmith gives it nothing else, since inputs and outputs are emptied first, but each run's metadata,
    which passes as it is. **Check:** a test traces a refused input through the app's own client, its runs kept
    instead of sent: no payload holds the question's word or the conversation's; the mutation check's two rules.

## Step 12 Â· Monitoring: Axiom, Sentry, the Health Check and the Status Dots

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
73. **A request that raised never sent what it left for monitoring.** *The review.* The middleware's send, step â‘¤,
    came after its `try`/`finally`; Starlette answers a request that raises with its 500, then raises again, so the
    error left the middleware before â‘¤: its lines waited for the next request on that copy, and Sentry's event,
    caught, was never flushed. **Fix:** â‘¤ is in the `finally`, after the request's line, still after the response
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

## Step 13 Â· Evals and Release: Golden Questions, a Load Test, Rollback

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

## Step 14 Â· Observability: Activity, Performance, Evaluations, Health, and the Menu in Groups

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
    sent; the mutation check's rule. On 2 November, with the token set, all 11 ran against the live dataset and
    each page showed its rows ([step 14](step-14.md)'s Deploy it).
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
    ran out, wasn't known then: the live check's own record didn't keep the asks' durations, and the deployment
    couldn't query Axiom yet. **Fix:** none yet; asks of the live site go 40 s apart. **Check:** with the query token
    set (2 November), Activity's errors filter shows the 12 `chat.failed` lines, 14:00:37 to 14:05:24 UTC: 11 ended
    after 10.0 to 10.1 s, the first chunk's limit, and the last after 19.6 s, its place found first, so most likely
    the next call's first chunk. So Gemini took more than 10 s to start answering 11 times for certain, most likely
    12; why it was slow isn't known.
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
    checkouts keeping no token. **Check:** the audit, here: "No known vulnerabilities found, 4 ignored"; CI's first,
    on 078915f, passed, its checks beside it; and on 17045bf, live with the new certifi, a question was answered
    through Gemini, whose client trusts certifi's bundle by default. The health check's four calls out came back ok
    too, though none uses certifi: httpx2 trusts the system's certificates.
95. **One health run in three failed, and no page says which check.** *Testing the real API* (the first look at the
    Observability pages with the query token, 2 November at 18:38 UTC). Health's last 7 days: 30 of 39 runs passed
    on 2 November, 0 of 2 on the 1st, 12 of 21 on 31 October, and 21 of 32 on the 30th. The 30th's are the
    TypeScript app's: their times stop at milliseconds, and they begin at 16:55 UTC, 2 minutes after its logs to
    Axiom (047a079), while this app's begin at 19:33 UTC on the 31st, a minute after step 12. This app's own: 42 of
    62 passed, its 20 failures "not answering" after 423 to 893 ms. On 2 November each of the 9 failures came within
    15 s of another run, two of them in the same second; on the 31st and the 1st, some came 2 to 13 minutes from any
    other. One failed at 18:37:34, between two asked by hand that found all four checks working, at 18:37:19 and
    18:38:55: a run answers its own address on its copy for a minute, so that one ran on another copy or through
    another address. Each `health.done` line keeps its `lanes`, and each failed check writes a `health.check` line
    with its `check` and `errorClass` (a warning, or an error the first time a copy meets one that needs a look), but
    Activity showed neither. The TypeScript app's lines leave the 7 days by 7 November. **Fix:** step 15: each health
    run is a row on Activity naming the checks that weren't answering, with their errors, and opens onto each check's
    line. **Check:** on step 15's live site, 2 November: all 23 of this app's failed runs in Errors named "Our MCP
    server (McpLaneError)"; the two opened failed that check after 139 and 344 ms, the other three working. Why our
    MCP server's check fails one run in three is still open ([To do](todo.md)).

## Step 15 Â· Activity by Request, and Rows That Lead to It

96. **A health check's line read the same as the call it made.** *Looking at the page* (a screenshot of a health
    run's timeline, opened). "Open-Meteo working in 420 ms", the check, sat under "Open-Meteo fetched in 400 ms", the
    geocoding it asked for, and nothing told them apart. **Fix:** a check's line names itself a check: "Open-Meteo
    check working in 420 ms"; the run's row still names the check alone. **Check:** the test of a health run's
    timeline, which finds the fetch before the check, each in its words.
97. **The minute's memo would have grown without end.** *Building step 15.* Step 14 keeps each query's run on the
    app's state, keyed by its APL, and a run older than a minute was only replaced when the same query came again.
    Activity's second query names its requests, so each minute brings new words, and the old ones would have stayed
    for as long as the copy lived. **Fix:** `ask()` lets go of every run past its minute before it keeps a new one.
    **Check:** a test that a minute after Activity, Performance's visit leaves only its own runs; the mutation check's
    rule.
98. **A link's reason could be any word.** *The review* (both reviewers). `?reason=` took any word of
    `[A-Za-z][A-Za-z0-9_]{0,63}`: it couldn't leave the query's quotes, but it reached the query and the page ("fallen
    back for CallUsAt5551234"), and each new word was a query of its own, past the CDN and the minute's memo, which
    the firewall's limit on `/api/*` doesn't cover: a loop of made-up words could spend the query token's cost caps,
    and every Observability page would say Axiom didn't answer. **Fix:** a link's values are ours only: the refusal
    codes the app writes, a list a test reads from each `InputError` in the code, and the classes of our errors.
    **Check:** a well-made code we don't write is a 404 with nothing asked; the test of the list; the mutation
    check's rules.
99. **A row's link brought in more than its row counted.** *The review* (both reviewers). A reason's link took
    refusals, failures and fallbacks with the same name, so "Why answers failed: UpstreamTimeoutError 1" opened
    fallbacks too; a lane's took the questions asked on it and those whose tools ran there, and on a lane with auth
    the three tools other than the forecast always run on the twin. **Fix:** `?refused=`, `?failed=` and
    `?fellback=`, each by its own event; `?asked=` for the questions asked on a lane, `?lane=` for those whose tools
    ran on it. **Check:** each link's where clause and words, written out in a test.
100. **A row could hide what went wrong.** *The review* (both reviewers). A question that fell back, or had a tool
     call fail, and still answered was a green "Answered" in Errors, with nothing to say why it was there; a call to
     our MCP server whose fetch failed was a green "Request 200". **Fix:** a row whose end went well, though a line
     on the way didn't, says how many didn't and is a warning; a call to our MCP server is a row by its tool, its
     `mcp.call` line in the timeline. **Check:** the fixture's fallback is "2 lines went wrong"; a test of a call to
     our server; the mutation check's rule.
101. **At the cap, a request could start halfway.** *The review* (both reviewers). The timeline's query takes 2,000
     lines; when that's reached, the oldest request kept may have lost its first lines, its row its lane, its "+0
     ms" a tool call, and the page said nothing. **Fix:** at the cap, the oldest request found is left out, and the
     page says older ones aren't shown; it says so too when 50 were found. **Check:** a test with the cap at the
     fixture's 27 lines; the mutation check's rule.
102. **A Health day's link buried its failures.** *The review* (both reviewers). Every page's dots and every uptime
     ping add a health run, so a day's runs pass the 50 shown, and its link opened them all, passed and failed
     alike. **Fix:** a day with failures links to its errors. **Check:** the test of Health's links.
103. **A forecast that couldn't fall back read "Fell back".** *The review* (reviewer A). `auth_lanes.py` writes its
     `lane.fallback` line before it knows there's time for the twin, with `fellBack` false when there isn't, and
     then the forecast fails. **Fix:** the timeline reads `fellBack`; false is "Couldn't fall back", with too little
     time left. **Check:** a test of the line; the mutation check's rule.
104. **On the MCP lanes, a question's timeline lacks its fetches.** *The review* (both reviewers). A tool on MCP Â· no
     auth, or a twin's on MCP Â· with auth, runs in our MCP server's own request, with an id of its own, so the
     question's timeline shows the tool call and not what it asked of Open-Meteo. **Fix:** none yet: the server's
     request is a row of its own (issue 100), and joining the two is on To do: the lane could send the question's
     id, which the server would log only from our own calls. **Check:** none yet.

## Step 16: Park guidance

105. **Weather chips assumed every tool had a wire request.** The park integration exposed that assumption.
     **Fix:** knowledge calls have their own artifact and escaped source links, revision dates and retrieval mode.
     **Check:** source-card tests and the browser accessibility and phone-width check.
106. **MiniLM would truncate the earlier long chunks.** Its input budget includes the document title and heading.
     **Fix:** use the actual tokenizer before encoding, split oversized text and reject over-limit inputs.
     **Check:** bounded-input and sentence-context tests, plus an actual CPU index build with 384-dimensional vectors.
107. **A guide-only question could depend on a working weather lane.** MCP setup originally preceded model routing.
     **Fix:** open weather lazily in a dedicated task that also closes its SDK context; retrieval remains available.
     **Check:** lane setup failure, cancellation, and composition tests on all four lanes.
108. **Initial source selection omitted Zion winter guidance.** The labeled evaluation found no supporting passage.
     **Fix:** add the official seasonal page and review its winter preparation text, excluding operating schedules.
     **Check:** all 30 labeled retrieval cases pass for keyword and CPU-assisted semantic retrieval.
109. **The new browser check opened a source card while its stream could still replace it.** A zero busy-count
     assertion could succeed before the answer began. **Fix:** wait for final answer text before opening the card.
     **Check:** the park card opens by keyboard, passes axe, and fits the phone viewport.
110. **The initial embedding dependency pins had known advisories.** The repository's dependency audit found them.
     **Fix:** pin patched SentenceTransformers, Transformers and CPU PyTorch releases; take narrow security-fix
     exceptions for filelock and setuptools. **Check:** the audit reports no known vulnerabilities beyond the four
     existing pyasn1 exceptions, and unit, browser and real CPU retrieval checks pass with the patched packages.
111. **The hosted ML dependency set was unnecessarily large and lacked weights.** Review found that a clean
     deployment could import ML and always fall back. **Fix:** separate an optional `ml` group and default Vercel to
     explicit keyword retrieval. **Check:** a clean production-only installation serves retrieval without ML.
112. **Lazy MCP setup failures ended as successful answers.** **Fix:** retain the original failure class in per-turn
     state, preserve any guidance, and finish through `chat.failed`; include setup events in Activity. **Check:** a
     real-schema fake MCP setup failure retains guidance and logs `McpLaneError`, with no `chat.done`.
113. **Nevada Fall was mistaken for a season.** Four safety passages were excluded in spring and summer. **Fix:**
     use reviewed section-season metadata and regenerate the index with four corrected records. **Check:** dated
     safety cases and a direct waterfall-name regression.
114. **Playground questions entered request URLs.** **Fix:** bounded POST bodies under `/api/`, same-origin checks,
     an expiring request limit and a concurrency cap. **Check:** question-free URLs, private-log markers, duplicate
     and oversized bodies, foreign origins, rate expiry and browser form submission.
115. **Longer place names matched familiar aliases.** **Fix:** reject unknown geographic qualifiers rather than
     stripping them. **Check:** Yellowstone's Grand Canyon, Kanarra Creek narrows and the unsupported North Rim.
116. **Generated park links depended on prompt instructions.** **Fix:** permit retrieved park URLs and reviewed
     weather-authority links before rendering. **Check:** invented and foreign citations lose their link targets;
     three new park goldens require citations, with two more covering unsupported and ambiguous destinations.
117. **Embedding deadlines left unbounded default-executor work.** **Fix:** one dedicated inference worker with no
     request queue; isolate offline embedding work in a process that is killed and reaped on its overall deadline.
     **Check:** cancellation, busy requests, released worker state and child termination tests.
118. **Two integration assertions did not prove their names.** A swallowed assertion and invalid forecast input
     concealed lane-opening behavior. **Fix:** observe opening attempts and use valid tool schemas; add rank-sensitive
     grading, paraphrases and hardening mutations. **Check:** focused regressions and the expanded 41-case benchmark.

## Step 17

119. **An NPS credential was placed in the tracked example file.** **Fix:** move it into ignored `.env.local` and
     restore a blank `NPS_API_KEY=` template. Never copy the credential into test recordings, artifacts or docs.
     **Check:** verify the example contains no value, the local file is ignored, and mock outputs exclude secrets.
120. **Step 17's deployment action was missing from Waiting on you.** **Fix:** list `NPS_API_KEY` for the intended
     Preview and Production environments, with redeploy and verification instructions; link from To do. Remove
     session-specific authorization statements from served docs. **Check:** inspect the rendered action page.
121. **Inspection forms and NPS link checks had copied logic.** **Fix:** share bounded form reading in `forms.py`
     and pure validation in `utils.py`; canonicalize allowed links as Markdown does. **Check:** existing retrieval
     defenses, invalid/duplicate form inputs and Unicode/default-port citation regressions.
122. **Page views looked like chat tool calls and rate limits showed JSON.** **Fix:** inspect configuration silently
     on GET, label explicit page checks separately, and render HTML errors with status and Retry-After intact.
     **Check:** event attribution, HTTP 429 selection retention, phone layout and axe in Edge.
123. **Partial-result and short-cache promises lacked direct regressions.** **Fix:** retain valid same-park notices
     after later-page failure or invalid individual records; label incomplete results and expire them at 60 seconds.
     **Check:** page-two failure, mixed valid/invalid records, cache hits at 59 seconds and refetch at 60 seconds.
124. **NPS diagnostics obscured cause, cache state and partial results.** **Fix:** log fixed reason codes, classify
     network errors separately, and show partial/cache/reason details on Activity while retaining guidance tones.
     **Check:** secret-free authentication/network logs, Activity rows and partial-result Errors selection. Remove
     the redundant prompt flag; notice instructions follow the production park-tools setting.
125. **Production's forecast-horizon golden called a tool.** On 4 November 2026, `too-far-ahead` called
     `geocode_location` despite requiring no tools. **Status: open.** The observed deployment was
     `dpl_HXVLKC8omqqMG4giJheCaFCosfcE`, source `5de2c5c`. The completed failure was retained and not retried away;
     completion tags were withheld. No runtime change was made during release validation.
126. **Production's ambiguous-park golden retrieved guidance before clarification.** On the same run,
     `park-ambiguous-destination` resolved both parks separately and called `search_park_guidance` twice instead
     of asking which park applied. **Status: open.** The case failed its no-guidance and clarification requirements.
     The full release evidence records this separately from the three model timeouts, all of which passed one
     identical technical recheck. Security changes and the new trip-measurement suite were not started.
127. **The travel MCP services needed the initialization handshake.** The SDK's negotiated legacy mode supported
     both. Synthetic local searches returned normalized flights and lodging. [Step 18](step-18.md#test-it)
128. **Trivago returned instructions alongside accommodation data.** Select explicit hotel and deal fields,
     constrain URLs to reviewed hosts, and test the discarded text with a hostile fixture. [Step 18](step-18.md)
129. **Park intake could select South Rim for a North Rim request or reverse a declined travel preference.**
     Reuse the park resolver, test negation through chat, and require a choice when the destination is unclear.
130. **Kiwi could label a fare for one traveler as the total for two.** Compare every returned age band with
     the requested party. Tests cover contradictory counts, missing counts and budgeted trips.
131. **The travel evaluation accepted a different trip and a nightly rate quoted as a stay total.** Grade the
     arguments in each chip and check money and inventory claims against the relevant provider evidence.
132. **Flights-only plans required room counts and logged a disabled hotel search.** Build queries only for
     enabled providers. Test both entry forms, stale room fields and the completed plan’s telemetry.
133. **Live travel evaluation found an unnecessary geocoding call for a hotel stay beyond the forecast horizon.**
     Give Gemini the inclusive last forecast date in the visitor’s time zone and check it before resolving a city.
     For undecided park alternatives, resolve the alternatives together before retrieving guidance.
134. **The chat page lost step 11's privacy line.** Removing the lane picker (592a73f) also removed "Your questions
     go to Google's Gemini... share nothing personal", its test and its mutation rule, just as step 18 invited
     airports and children's ages into the chat. **Fix:** restore the line, its style, its test and its rule.
     **Check:** `test_the_chat_page_says_where_questions_go`; mutation "the page says where questions go".
135. **The public trace page told any visitor how Nimbus is configured.** Messages named `LANGSMITH_WORKSPACE_ID`,
     the deployment key and the server's log. **Fix:** each message speaks to a visitor; its enum name stays the
     diagnostic code that `langsmith.read_failed` logs. **Check:** no message names a setting, a key or the log;
     every message is distinct.
136. **`LANGSMITH_WORKSPACE_ID` was undocumented.** A key that reaches several workspaces needs it to read traces,
     and a value that isn't a UUID stops the app at start. **Fix:** `.env.example`, Waiting on you part 3, and
     the technical details say so.
137. **A slow travel search could cost the whole answer.** A search may take 14 s and stopped only at the answer's
     own deadline, leaving the model no time to write; the forecast that did come back was lost. **Fix:** a chat's
     travel searches end `TRAVEL_ANSWER_RESERVE_SECONDS` (12 s) before the answer's deadline, the same margin the
     Apify lanes keep (`FALLBACK_MIN_LEFT_SECONDS`). **Check:** the turn's deadline is the answer's less the reserve.
138. **With travel on, rule 11 lost its polite refusal.** "Do I need a visa for Canada?" could get an answer from
     the model's memory. **Fix:** the travel version keeps "For anything else, say in one polite sentence what you
     can do." **Check:** both park settings, with a travel tool.
139. **Kiwi rejected every offer for most city codes.** Only NYC, LON and WAS were known, so CHI's ORD and MDW
     flights read as "a different airport than requested". **Fix:** IATA's common metropolitan codes that name no
     airport of their own, and a tool description asking for an airport code or the city's name. **Check:** CHI,
     TYO and PAR keep their airports; ORD still rejects MDW. Step 18's chapter names the list.
140. **"Plan a trip to Yellowstone National Park" got a form for three other parks, unexplained.** **Fix:** a form
     without a resolved park asks the visitor to choose from the list, the parks the planner covers, and for a
     place not on it to ask here about its weather and only the enabled searches. The wording also suits a listed
     park the resolver missed ("Plan a trip to Zion next weekend"). **Check:** Yellowstone and two-park requests;
     flights only names no hotels.
141. **The planner's forecast was always °F, and chat searched in dollars.** **Fix:** the plan's units follow the
     browser's first language (Accept-Language), as chat's rule 13 does. A chat search that names no currency
     takes the locale's (GBP, CAD or EUR where its region uses them, else USD), the prompt says to search in it,
     and the chat's trip form preselects it. The locale helpers live in `nimbus/utils.py`, shared by chat, prompts
     and the planner. **Check:** en-GB gets metric and GBP; no language, imperial; a currency the model names
     stays. A language without a region ("de") still searches in USD.
142. **"We plan to visit Yosemite this weekend. Will it snow?" got the trip form, not a forecast.** The trip words
     matched "plan ... visit". **Fix:** a question that asks about the weather (rain, snow, forecast, what to wear
     or pack) gets the chat, unless an explicit request opens the form beside it: "plan" starting a sentence,
     "can you (help me) plan", "help me plan", "please plan", an itinerary or a trip planner. **Check:** "we plan a
     trip to Zion next week, will it rain?" and five more reach the chat; "help me plan to visit Zion" and "Plan a
     trip to Zion National Park; will it rain?" still open the form.
143. **Code the lane picker left behind.** `to_call_actor_example` had no caller; comments and a test still named the
     compare view. **Fix:** remove the helper, rename the comments and test, note the removal at the top of steps
     9, 10 and 12, and in the docs index's summaries; `chat.js` no longer adds status dots.
144. **The privacy tables didn't name the travel providers.** **Fix:** step 11's table and the architecture's "what
     is kept, where" list what Kiwi and trivago receive, and what the trace view shows of LangSmith's runs.
145. **The mutation check stopped on stale rules.** Rules whose text had moved (the request's path in
     `middleware.py`, Activity's ref in `observability.py`, and the locale helpers now in `utils.py`) matched
     nothing, so the full run raised before its summary. **Fix:** each rule names the code as it is now; the review
     fixes' rules run with `--travel` too, and `chat_trip.html` and `planner_page.py` map to `test_planner.py`.
     **Check:** all 349 rules match their text exactly once; each review rule was run and caught.
146. **A travel fault and a provider outage looked the same.** Every exception became "unavailable" with nothing
     logged. **Fix:** `travel.error`, `travel.mcp_error` and `travel.section_error` log the class only (no
     arguments, places or provider text).
147. **Trace links lasted 7 days.** **Fix:** a link expires an hour after Activity shows it, never past Activity's
     window; the HMAC message already names its purpose (`nimbus/activity-trace/v1`), so the key is domain-separated.
148. **A partial travel result counted as a failed plan section, and a switched-off provider as an error.**
     **Fix:** partial is a warning (Activity's tone, Errors as for NPS), not a failed section; `disabled` leaves Errors.
149. **A repeated identical search showed its offer cards twice.** **Fix:** one set of cards for each distinct report.
150. **The chat's trip form replaced the chat page.** The conversation lives in the page. The chat form now shows
     the plan or validation error inside the turn that requested it. It carries the chat's locale for forecast units.
151. **A travel answer could keep invented links when the question said "stay", "room" or "airport".** **Fix:** the
     words that restrict an answer's links to returned evidence include airline, airport, ticket, motel, lodge,
     resort, room and stay.
152. **Trip-form turns pulled Performance's answer times down.** **Fix:** `chat.done` carries `tripForm=true` for
     them, and the answer times leave them out.
153. **No limit on a trip's dates or length.** A 2099 arrival or a 3,000-night stay still searched. **Fix:** travel
     a search more than 365 days after the visitor's today is refused, as a past date is; a plan's check-in within the next year; a stay at most 30 nights. The year limit sits in the search, not the models, so tests may still build far synthetic dates (CI failed on that once).
154. **A browser reporting only "de" or "fr" searched in dollars.** **Fix:** a language most of whose speakers use
     the euro searches in EUR; "en" and others stay USD.
155. **"Plan a trip to Zion next weekend" opened the form with no park chosen.** The resolver read the trip's details
     as part of the place. **Fix:** when and with whom ("next weekend", "in December", "for my kids aged 5 and 8")
     are removed before resolving; places such as "Zion, Illinois" still reach it whole.
156. **Two tests passed for the wrong reason.** One found the flight link in the offer card, not the answer; one never
     restricted links. **Fix:** the first reads the answer itself; the second also asks with a travel word.
157. **The privacy line named only Gemini with travel on.** **Fix:** it adds which searches go to Kiwi.com and
     trivago, and what they get: places, dates and party, never the question.
158. **The architecture's time limits named only 8 s for a tool.** **Fix:** they name 14 s for a travel search, ending
     12 s before the answer's deadline. Round 3 (146 to 158) was committed without running the test suite, at the
     user's request; CI runs it.
159. **Common trip requests lost their park or dates.** Polite requests, a city origin, weekend and holiday phrasing,
     and contextual park choices now reach the conditions check. A single stated date remains editable.
160. **A return deadline could become a Sunday evening flight.** The named return day and clock now reach both the
     quote form and Kiwi. Local-date and time checks cover previous-night flights and airports outside the original list.
161. **Undecided travelers had to enter airports to search hotels.** The quote editor supports hotels alone and
     editable flight windows. A late Friday departure retains the origin date while lodging uses the park’s local date.
162. **A bulletin expiry could conceal a warning with an unknown end.** The briefing marks uncertain hazard timing.
     NWS outcomes appear in Activity, and completed conditions checks count toward chat latency.
163. **A preview alias can change while a live suite runs.** The harness checks the deployment identity before,
     during and after the trial series. A mismatched response fails its attempt.
164. **A reviewed case could gain unintended assertions when saved.** Promotion serializes only the expected fields
     the reviewer supplied. An isolated mutation inserts the defaults again and the regression test catches it.
165. **Mem0 returned a different schema type from the initial fixtures.** A live synthetic save showed metadata
     version `"1"` as text. The adapter accepts exactly integer `1` or text `"1"`, rejects other values, and verifies
     readback. Offline wire-format tests and a live create/read/update/delete check cover the fix.
166. **Refreshing after saving preferences resubmitted an old form.** Chrome testing caught a token mismatch after
     first save. Confirmed save, resume and deletion now redirect to a GET. Browser tests reload and reopen profiles.
167. **A stale Pause form could clear deletion-pending state.** Independent review found that a failed Forget could
     then be resumed from another tab. Pause now preserves pending deletion; a regression and mutation guard it.
168. **Rate-limited preference forms could claim a profile was active before a write or read.** Initial Save now
     mints its identity only after the gate permits work. Resume activates only after verified readback. Rejected
     forms retain the correct state and a usable retry token.
169. **Saved defaults were uneven across trip entry points.** Review found city intake ignored saved airports and
     dated quote forms hid units, currency and activity. City calendars now use eligible saved or explicit origins;
     shared editable controls carry trip-specific overrides to the providers without changing stored preferences.
170. **Negated preference requests could propose the opposite default.** Curly apostrophes and `no`, `avoid` or
     `without` were not recognized. The preview now normalizes punctuation and declines to guess those clauses.
     Consent is still required; expiry, isolation, malformed tokens and private-log regressions run alongside it.
171. **The trace table made nested tool spans look like duplicate requests.** The explorer preserves declared
     parent relationships, including hidden graph wrappers, and keeps parallel branches separate. Summary counts
     describe spans; the agent duration is not a sum of overlapping calls. Collapse, filters and exact call details
     clarify the display without requesting more LangSmith fields. Privacy, hierarchy and timing tests guard it.
172. **Standalone memory traces could use a different project from the trace reader.** Both independent reviewers
     found that forcing `default` when the app's project was unset bypassed LangSmith's legacy and hosted project
     settings. Mem0 now passes the optional project through to the SDK, like the existing tracing path. Actual SDK
     serialization tests cover both fallback settings, and a mutation restores the bug to prove those tests catch it.
173. **Similarity alone did not prove that a weather answer was reusable.** The initial independent set at a frozen
     `0.80` cutoff recalled only 3 of 5 positive examples. General politeness and approved `wether` normalization
     improved the same set to 10/10 overall; its first report is preserved, and the rerun is labelled regression
     evidence. **Fix:** independent browser, authenticated-history, prompt-build, location, date and unit guards
     constrain reuse. Both reviewers also required original source-age limits, complete forecast coverage,
     cross-version expiry cleanup and provider errors counted separately from retrieval misses. A mutation exposed
     a missing evidence-expiry assertion, now covered. **Check:** the final real embedding set passed 18 cases with
     no false hits or provider errors. A real Dallas paraphrase reused its answer with zero tool calls or Gemini
     calls; 226 Chrome tests and 455 offline harness replay cases passed. Hosted activation remains pending.
174. **Activity didn't say which steps call Mem0.** *You, 9 November.* A chat's "Read preferences" row looked like
     any other step, and a deletion's row said "Forget preferences" while its trace link said "Delete preferences".
     **Why:** the labels were written twice, in the row and in the link. **Fix:** one list names the three
     operations that call Mem0, "Read Preferences (mem0)", "Save Preferences (mem0)" and "Delete Preferences
     (mem0)", for both; pause and resume change only the browser's setting, so they keep their names. A chat
     question still only reads Mem0; only My preferences or a confirmed save preview writes. **Check:** the memory
     Activity tests expect the new labels.
175. **A chat's Mem0 read wasn't in its LangSmith trace.** *You, 9 November.* "View LangSmith trace" opened the
     agent's trace, with no Mem0 in it; the read was a trace of its own, behind a second link. A cached answer, a
     trip form or a preference preview had no trace at all. **Why:** the read runs before the agent, whose trace
     LangGraph starts, so there was no parent to put it in. **Fix:** each chat request begins its own root,
     `nimbus.chat` (nimbus/request_trace.py), before its first step. The Mem0 read, the weather answer cache lookup
     and store, and the agent's graph nest under it, all with no inputs or outputs. The root ends once, however
     the response ends, failed only when the answer failed, and is sent once after the response. Its ID is on every
     chat ending, so Activity shows one link. The trace page names the steps and keeps "one Mem0 operation" for a
     Mem0 trace of its own (saves and deletes on My preferences). **Check:** with the real LangSmith SDK, offline,
     the graph, the read and the cache steps are children of the root in its dotted order. The root is sent
     exactly twice (start, end), and a trip form, a reused answer and an answer each flush once on Vercel. Eleven
     mutation rules are caught, and the activity-trace and preferences browser tests pass.
176. **Three mutation rules no longer matched their code.** *The check for issue 175.* The rules for an
     Open-Meteo cache hit, a guidance lookup's Activity tone and the trip plan's forecast units each replaced
     text that later commits rewrote: freshness timestamps in the cache's return, a grey tone for a cancelled
     lookup, a saved unit preference before the browser's. The check refuses a rule whose text isn't there exactly
     once, so a full run stopped with an error. **Fix:** the three rules match the current lines, and two new rules
     cover what was added without one: a cancelled lookup stays grey, and saved units win over the browser's,
     each with its test. **Check:** all 444 rules match their text once; the five rules are caught.
177. **Qdrant traces hid cache decisions and caught provider failures.** *You, 9 November.* Lookup and store
     spans only timed the wrapper, so a miss, a rejected write or a caught outage could all look Completed.
     **Fix:** both steps carry fixed outcomes, returned errors mark the step Failed, and provider calls nest
     beneath them with separate timings. The root records a fixed reason when lookup is bypassed. The similarity
     span records a bounded threshold and, only when a candidate is returned, its valid numeric score. The Nimbus
     explorer reads these fields through an allowlist; questions, answers, vectors, scopes, guards, preferences,
     keys and raw provider errors remain excluded. A cache error still permits the normal answer. **Check:**
     offline real-SDK tests cover outcomes, nesting, timeouts, cancellation, numeric bounds and private-value
     exclusion. Focused unit checks and five Chrome cases passed, including mobile layout and accessibility.
     All 16 affected mutation rules were caught by assertion failures, and both independent reviews found no
     blocking issues. Validation was local and offline; the full suite and hosted delivery were not run.

