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
    the label no longer says which commit last changed Nimbus. **Fix:** the System design says so; skipping those
    deploys (an `ignoreCommand` in `vercel.json` that ends the build when this folder hasn't changed) is on To do.
    **Check:** `/api/health`'s commit, after a push that changes only another project.

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
