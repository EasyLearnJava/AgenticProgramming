# 03 · Run on a button click

A page that calls the server only when you click its button, once per click, which is how most pages work. The
chain and the server are project 02's; only the page is new. No model, no API key.

```text
open the page      ->  Nothing has run yet. Click the button.    (nothing is sent)
click the button   ->  GET /api/hello  ->  Hello World, welcome to LangChain!    Clicks: 1
click it again     ->  GET /api/hello  ->  the same answer                       Clicks: 2
```

## What you'll build

- `index.html`: a page with a **Run the chain** button, an answer line and a click counter. Opening it sends
  nothing. Each click calls `GET /api/hello` once: the page says "Asking the server…" and greys out the button
  while it waits, then shows the answer, or what went wrong.
- `hello.py` and `main.py`, the same as project 02's: the chain `prompt | to_text`, served at `GET /api/hello`.
- `tests/test_hello.py`: project 02's tests for the chain and the server, plus text checks on the new page.

## What you'll learn

- **`addEventListener("click", ...)`**: hands the browser a function to run on every click, so the request moves
  out of page load and into the click.
- **`async` and `await`**: the same request as project 02's `.then()` chain, written top to bottom; `await` pauses
  this function until the answer arrives, not the whole page.
- **`try` / `catch` / `finally`**: `catch` puts any error on the page, and `finally` runs after success and failure
  alike, so the button always comes back.
- **A loading state and a disabled button**: "Asking the server…" while the request is out, and
  `button.disabled = true` so a second click can't start a second request.
- **`cache: "no-store"`**: the browser never answers this request from its cache, so every click reaches the server.

## What's new since project 02

[Project 02 · LangChain basic (Python)](../02-langchain-python/README.md) called the server as soon as its page
opened. Here:

- **The request waits for a click**: `fetch("/api/hello")` moved from the top of the script, where it ran as the
  page loaded, into a click handler on a new button. A click counter shows each click.
- **`async`/`await` with `try`/`catch`/`finally`** replace the `.then()`/`.catch()` chain. While a click's request
  is out, the page shows "Asking the server…" (project 02's starting text, now set by each click) and the button is
  disabled. The `fetch` also passes `cache: "no-store"`.
- **`hello.py` and `main.py` work as before**: the same chain and the same routes. Only their docstrings, the app's
  title (`AgenticProgramming project 3`) and a few comments differ.
- **The tests**: the page test looks for the button instead of `fetch("/api/hello")`, and new checks make sure the
  page's only fetch comes after the click listener and that `finally` turns the button back on.

## Before you start

- Python 3.11 or newer: `python --version` shows yours.
- No API key: nothing here calls a model.
- It helps to have done project 02: its README explains the virtual environment, uvicorn and the Codespaces
  address step by step. This one only repeats the commands.

## Files

| File | What it is |
|---|---|
| `hello.py` | The chain, `prompt \| to_text`, as in project 02. Runs on its own with `python hello.py`; `main.py` imports `chain` from it |
| `main.py` | The FastAPI app, with project 02's routes: `GET /` and `GET /index.html` send the page, `GET /api/hello` runs the chain and returns `{"answer": ...}` |
| `index.html` | The page: a **Run the chain** button, the answer and a click counter. Its only `fetch("/api/hello")` is inside the click handler |
| `tests/test_hello.py` | The tests: the chain, `hello.py` run as a script, the endpoint, and text checks on the page |
| `pytest.ini` | pytest's settings: `pythonpath = .` lets the tests `import hello` and `import main`; `testpaths = tests` makes it look for tests only in `tests/` |
| `requirements.txt` | The app's packages, each pinned to one exact version with `==`: `fastapi`, `uvicorn`, `langchain-core` (the same as project 02's) |
| `requirements-dev.txt` | Everything in `requirements.txt` (its `-r` line) plus the test tools, `pytest` and `httpx` |
| `README.md` | This page |

`.venv/` appears when you set up, and `__pycache__/` and `.pytest_cache/` when you run the server and the tests.
The repo's `.gitignore` keeps all three out of git.

## How it works

The whole trip, from opening the page to seeing the answer:

```text
open the page (GET /)  →  main.py sends index.html; the script gets the button ready and sends nothing
click the button       →  Clicks: 1, the button greys out, "Asking the server…", fetch("/api/hello")
main.py                →  await chain.ainvoke({})   (the chain from hello.py)
JSON back              →  the page shows "Hello World, welcome to LangChain!", and the button comes back
```

### 1. The server starts, as in project 02

```python
from hello import chain

app = FastAPI(title="AgenticProgramming project 3")
```

`uvicorn main:app --reload` imports main.py, which imports hello.py, so the chain is built once, when the server
starts:

```python
# ③ Join them: prompt first, then to_text. `a | b` is Python's a.pipe(b).
chain = prompt | to_text
```

Both files do exactly what they did in project 02, and
[project 02's How it works](../02-langchain-python/README.md#how-it-works) walks through them line by line.
Everything new in this project is in index.html.

### 2. The page opens, and the script only gets ready

```html
  <button id="run">Run the chain</button>
  <p id="answer">Nothing has run yet. Click the button.</p>
  <p id="clicks">Clicks: 0</p>
```

```js
    // On load, nothing is sent: the script only finds the elements and gives the button a click handler.
    // Each click calls the backend (main.py's GET /api/hello) once, which runs hello.py's chain.
    const button = document.getElementById("run");
    const answer = document.getElementById("answer");
    const clicks = document.getElementById("clicks");
    let count = 0;

    button.addEventListener("click", async () => {
      ...
    });
```

The script runs once, as the page loads, just like project 02's. But project 02's script called `fetch` right
there, while this one only finds the three elements by their `id` and hands the button a function.
`addEventListener("click", ...)` stores that function, and the browser calls it each time the button is clicked.
So opening the page sends nothing: the uvicorn terminal logs no `GET /api/hello` until you click. `const` means the
name can't be given a new value later; the element it names can still change (its text, whether it is disabled).
`count` uses `let` because it gets a new value with every click.

### 3. A click: count it, grey out the button, say it's waiting

```js
      count += 1;                           // the answer is the same every time: the counter shows each click
      clicks.textContent = `Clicks: ${count}`;
      button.disabled = true;               // one request at a time: no new click while this one is waiting
      answer.textContent = "Asking the server…";
```

Text between backticks is a template string: `${count}` puts the number into it, like an f-string in Python. A
disabled button greys out and ignores clicks, because the browser doesn't run its click handler. So while a request
is out, another click starts nothing and isn't counted. On your laptop the answer comes back within a few
milliseconds, so the waiting text and the grey button flash by too fast to see; [Things to try](#things-to-try)
slows the network down so you can watch them.

### 4. The request goes out

```js
      try {
        // cache: "no-store" makes every click a real request to the server, never a cached answer.
        const res = await fetch("/api/hello", { cache: "no-store" });
```

This is project 02's request, written another way. Project 02 chained `.then(...)` calls, each one running when the
step before it had finished. Here the click handler is an `async` function, so it can use `await`: the function
pauses on this line until the server answers, then carries on with the next line. It reads top to bottom, like
`answer = await chain.ainvoke({})` in main.py. Only this function waits; the rest of the page keeps working.

`cache: "no-store"` tells the browser never to answer this request from its cache, and not to keep the answer
either. main.py sends no caching headers, so the browser would ask the server again anyway; `no-store` makes that a
rule instead of luck. If a server answered with `Cache-Control: max-age=60` ("keep this for 60 seconds"), a plain
`fetch` would answer the second and third clicks from the browser's cache, without asking the server; with
`no-store`, all three clicks reach it.

### 5. On the server: project 02's route

```python
@app.get("/api/hello")
async def hello():
    """Runs the chain with no input and returns its answer."""
    # ainvoke() is invoke()'s async twin: the server can serve other requests while this one waits.
    answer = await chain.ainvoke({})
    return {"answer": answer}
```

The server can't tell whether a page load or a click sent the request, and doesn't need to: it runs the chain and
returns `{"answer":"Hello World, welcome to LangChain!"}`. Each click adds one `"GET /api/hello HTTP/1.1" 200 OK`
line to the uvicorn terminal.

### 6. The answer comes back

```js
        // fetch only fails by itself when the server can't be reached. A 404 or a 500 still arrives, with res.ok false.
        if (!res.ok) throw new Error(`the server answered HTTP ${res.status}`);
        const data = await res.json();
        answer.textContent = data.answer;
```

The same check as project 02: `res.ok` is true only for statuses 200 to 299, so the page turns an error answer such
as a 500 into an error of its own. `res.json()` reads the body as JSON, and needs its own `await` because the body
can arrive after the status.

After the first click the text on the page stays the same, because the answer is the same every time. The counter
shows that the page saw each click, not that the server answered: it goes up before the request is sent, so it
also counts clicks whose request fails. To see each click reach the server, watch DevTools' **Network** tab or the
uvicorn terminal, as in [What you should see](#what-you-should-see).

### 7. catch and finally: what went wrong, and the button comes back

```js
      } catch (err) {
        answer.textContent = `Something went wrong: ${err.message}`;
      } finally {
        button.disabled = false;            // runs after success and failure alike: the button always comes back
      }
    });
```

Anything that goes wrong inside `try` jumps straight to `catch`, skipping the rest of `try`. The error thrown for a
500 shows `Something went wrong: the server answered HTTP 500`, and a server that can't be reached shows
`Something went wrong: Failed to fetch` (Chrome's wording). `finally` runs last either way, after `try` finished or
after `catch`, so the button always comes back. If `button.disabled = false;` sat at the end of `try` instead, a
failed request would skip it and leave the button grey until a refresh: [Things to try](#things-to-try) 3 shows it.

## Run it

```bash
cd tutorials/03-langchain-button
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell: .venv\Scripts\Activate.ps1
#   Windows Git Bash:   source .venv/Scripts/activate
pip install -r requirements-dev.txt
```

Creating the venv and installing are once only; activate it again in every new terminal. Then:

```bash
python hello.py                      # just the chain: Hello World, welcome to LangChain!
uvicorn main:app --reload            # the server; Ctrl+C stops it
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page (click to call the server) | http://127.0.0.1:8000 (or `/index.html`) | `https://<codespace-name>-8000.app.github.dev` (or `/index.html`) |
| The raw JSON | http://127.0.0.1:8000/api/hello | `https://<codespace-name>-8000.app.github.dev/api/hello` |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

In Codespaces, use the forwarded address from the **Ports** tab; [project 02's Run it](../02-langchain-python/README.md#run-it)
shows where to find it.

Only one server can use port 8000 at a time: stop the previous project's server (Ctrl+C) before starting this one.

The curl example is for bash (macOS, Linux, Codespaces, Git Bash):

```bash
curl http://127.0.0.1:8000/api/hello
# {"answer":"Hello World, welcome to LangChain!"}
```

### What you should see

Open the browser's DevTools (F12), go to the **Network** tab, then load the page:

1. On load: the page itself, and no `hello` request. (The browser may also ask for `favicon.ico`, a tab icon; this
   project has none, so that request gets a harmless 404.)
2. Click once: one `hello` request, and the answer appears.
3. Click twice more: two more `hello` requests, and the counter says `Clicks: 3`.

The uvicorn terminal shows the same: `GET /` and `GET /favicon.ico ... 404 Not Found` when the page opens, then one
`GET /api/hello` line per click.

## Test it

```bash
python -m pytest          # all the tests; the last line says "8 passed"
python -m pytest -v       # the same tests, one line each, with its name
```

There are 8 tests, all plain (8 plain, 0 live): no key, no network and no server to start. They come from 7 test
functions, because `@pytest.mark.parametrize` runs the page test once for `/` and once for `/index.html`.

| Test | What it checks |
|---|---|
| `test_chain_returns_the_message_as_a_string` | `chain.invoke({})` returns exactly the greeting, as a `str` |
| `test_prompt_gives_an_object_and_to_text_turns_it_into_text` | The prompt alone gives a `StringPromptValue`, and `to_text` turns it into the greeting |
| `test_running_hello_py_prints_the_message` | `python hello.py`, run as a separate process, prints the greeting |
| `test_api_returns_the_answer` | `GET /api/hello` answers 200 with `{"answer": "Hello World, welcome to LangChain!"}` |
| `test_page_is_served_with_a_button[/]` and `[/index.html]` | Both addresses send HTML that contains `<button id="run">` |
| `test_page_calls_the_api_only_inside_the_click_handler` | The page has exactly one `fetch("/api/hello"`, and it comes after `addEventListener("click"` |
| `test_page_checks_res_ok_and_always_turns_the_button_back_on` | The page checks `res.ok`, shows `Something went wrong: ...` when something fails, and sets `button.disabled = false` after `} finally {` |

The page tests check index.html's text: no browser runs and nothing gets clicked. They catch the likely slips, such
as a `fetch` back at the top of the script, but the clicking itself you check by hand, with
[What you should see](#what-you-should-see) and [Things to try](#things-to-try).

## When things go wrong

| What happens | What you see | What to do |
|---|---|---|
| Project 02's server is still running | The page has no button, and its tab says "Project 2: LangChain basic (Python)": it is project 02's page. On Windows, with both servers started with `--reload`, neither terminal shows an error; without `--reload`, this one stops with `[Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000): ...` | Stop project 02's server (Ctrl+C in its terminal), start this one again if it stopped, then refresh the page |
| index.html was opened straight from the folder | The page and its button appear, but a click shows `Something went wrong: Failed to fetch` (Chrome's wording) | Open http://127.0.0.1:8000 instead: `/api/hello` exists only on the server, which is why main.py sends the page |
| The server stopped while the page was open | A click shows `Something went wrong: Failed to fetch`, and the button comes back | Start the server again and click: no refresh needed |
| The chain fails, after an edit to hello.py say | The page shows `Something went wrong: the server answered HTTP 500`. The terminal shows `"GET /api/hello HTTP/1.1" 500 Internal Server Error`, then `ERROR:    Exception in ASGI application` and a traceback ending in the real error, such as `KeyError: "Input to PromptTemplate is missing variables {'name'}. ...` | Read the last line of the traceback, then fix or undo the edit; `--reload` restarts the server when you save |
| A 404 you didn't ask for | `"GET /favicon.ico HTTP/1.1" 404 Not Found` in the terminal when the page opens | Nothing: the browser asks every site for a tab icon, and this one has none |

## Things to try

1. **Watch the wait.** In DevTools' **Network** tab, open the throttling menu (it says **No throttling**) and pick a
   slow preset such as **3G**. Click: for a moment the page says "Asking the server…" and the button is greyed out.
   Click again while it's grey: no new `hello` request, and the counter doesn't move. Set the menu back to
   **No throttling** when you're done.
2. **Take the disabled button away.** In index.html, delete the line `button.disabled = true;` (with its comment),
   save, and refresh the page: main.py reads index.html again on every request, so no restart is needed. With the
   slow preset on, click twice quickly: two `hello` requests go out, and the counter says `Clicks: 2`. That's what
   the line prevents. Put it back.
3. **Move the line out of `finally`.** Cut `button.disabled = false;` out of the `finally` block and paste it at the
   end of the `try` block, just after `answer.textContent = data.answer;`. Save and refresh: clicks still work. Now
   pick **Offline** in the throttling menu and click: `Something went wrong: Failed to fetch`, and the button stays
   grey, even after you set the menu back to **No throttling**, until you refresh. The failed `fetch` jumped
   straight to `catch`, past the line. Put it back in `finally`.
4. **Change the greeting while the page is open.** With the server running, change the text in hello.py's
   `from_template(...)`, for example to `"Hello again, welcome to LangChain!"`, and save. The terminal logs
   `StatReload detected changes in 'hello.py'. Reloading...` and the server restarts. Click again without
   refreshing: the new text appears, because every click asks the server. The counter carries on from where it
   was, because the page wasn't reloaded. Put the text back afterwards: the tests check the exact greeting, so
   `python -m pytest` fails until you do.

## Next

**[Project 04 · Pass one input](../04-langchain-input/README.md)**: the chain gets its first input, a name typed
into a box, sent to the server as JSON in a `POST` and checked by Pydantic, with a 422 for a bad name.
