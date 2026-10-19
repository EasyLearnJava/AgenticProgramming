# 02 · LangChain basic (Python)

Project 01's chain, a `PromptTemplate` piped into a `RunnableLambda`, rewritten in Python and served by FastAPI, a
Python web framework, to a web page that asks for the answer as soon as it opens. No model, no API key.

```text
page opens  ->  GET /api/hello  ->  chain.ainvoke({})  ->  {"answer":"Hello World, welcome to LangChain!"}
```

## What you'll build

- `hello.py`: project 01's chain in Python. `python hello.py` prints the greeting in the terminal.
- `main.py`: a FastAPI server. `GET /api/hello` runs the chain and returns `{"answer": ...}`; `GET /` and
  `GET /index.html` send the page.
- `index.html`: a page that says "Asking the server…", calls `/api/hello` as soon as it opens, and shows the answer.
- `tests/test_hello.py`: the repo's first tests, which check all of the above with no server running.
- `requirements.txt` and `requirements-dev.txt`: the packages, each pinned with `==`. `pytest.ini`: where pytest
  finds the code and the tests.
- What you see: `python hello.py` prints `Hello World, welcome to LangChain!`. With `uvicorn main:app --reload`
  running, http://127.0.0.1:8000 shows it on the page, and the terminal logs each request.

## What you'll learn

- **The same chain in Python**: `PromptTemplate.from_template(...)`, `RunnableLambda(...)` and `prompt | to_text`,
  Python's way of writing `prompt.pipe(to_text)`.
- **`if __name__ == "__main__":`**: one file that runs as a script, and that `main.py` can import to get the chain:
  the import builds the chain and skips ④.
- **FastAPI and uvicorn**: `@app.get(...)` ties an address to a function, the dict the function returns goes out as
  JSON, and `uvicorn main:app` serves it all.
- **`ainvoke()`**: the async twin of `invoke()`, awaited inside an `async def` function.
- **`fetch()` and `res.ok`**: the page asks its own server for the answer, and turns an error answer into a message
  it can show.
- **A virtual environment and pip**: `python -m venv .venv`, activating it, and
  `pip install -r requirements-dev.txt`.
- **pytest and FastAPI's `TestClient`**: testing the app without starting a server.

## What's new since project 01

[Project 01 · LangChain basic](../01-langchain-basic/README.md) ran the chain once, in JavaScript, in the terminal.
Here:

- **Python instead of JavaScript**: the same classes and the same chain, spelled the Python way. ① to ④ in
  [How it works](#how-it-works) line the two files up.
- **A virtual environment and pip instead of npm**: `.venv/` plays the part of `node_modules/`, `requirements.txt`
  the part of package.json's `dependencies`, and `pip install -r` the part of `npm install`.
- **A server and a page**: the chain runs on every `GET /api/hello`, and index.html calls that as soon as it opens.
- **Tests**: project 01 had none. Here, `python -m pytest` runs the tests in `tests/test_hello.py` (see
  [Test it](#test-it)).

## Before you start

- **Python 3.11 or newer** (3.13 is used here). Check with `python --version`; if that fails, install Python from
  python.org. If `python` isn't found on macOS or Linux, use `python3` for the `python -m venv .venv` step; inside
  the active venv, `python` works on every system.
- Nothing else: no API key, no Node, nothing from project 01. [Run it](#run-it) installs what this project needs.

## Files

| File | What it is |
|---|---|
| `hello.py` | The chain, `prompt \| to_text`, in steps ① to ④. Runs on its own with `python hello.py`; `main.py` imports `chain` from it |
| `main.py` | The FastAPI app, steps ⑤ to ⑦: `GET /` and `GET /index.html` send the page, `GET /api/hello` runs the chain and returns `{"answer": ...}` |
| `index.html` | The page, steps ⑧ and ⑨: as soon as it opens, it calls `/api/hello` and shows the answer, or what went wrong |
| `tests/test_hello.py` | The tests: the chain, `hello.py` run as a script, `GET /api/hello` and the page |
| `pytest.ini` | pytest's settings: `pythonpath = .` lets the tests `import hello` and `import main` wherever pytest is started from; `testpaths = tests` makes it look for tests only in `tests/` |
| `requirements.txt` | The app's packages, each pinned to one exact version with `==`: `fastapi`, `uvicorn`, `langchain-core` |
| `requirements-dev.txt` | Everything in `requirements.txt` (its `-r` line) plus the test tools, `pytest` and `httpx2` |
| `images/` | The two pictures on this page: the code from start-up to answer, and the commands that run it. They're SVG files: pictures written as text, which GitHub shows as images |
| `README.md` | This page |

`.venv/` appears when you set up, and `__pycache__/` and `.pytest_cache/` when you run the server and the tests.
The repo's `.gitignore` keeps all three out of git.

## How it works

### `pip install -r requirements-dev.txt`, then `python hello.py` and `uvicorn main:app`

`requirements.txt` lists the packages the app needs:

```text
fastapi==0.142.2
uvicorn==0.54.0
langchain-core==1.6.6
```

and `requirements-dev.txt` adds the ones the tests need:

```text
# Extra packages for running the tests. `pip install -r requirements-dev.txt` installs these and requirements.txt.
-r requirements.txt
pytest==9.1.1          # runs the tests in tests/
httpx2==2.14.0         # FastAPI's TestClient sends the tests' requests to the app with it, without starting a server
```

- **`fastapi`**: the web framework `main.py` is written with: `FastAPI`, `@app.get(...)` and `FileResponse`.
- **`uvicorn`**: the server that runs the app. `uvicorn main:app` loads `main.py` and answers on port 8000.
- **`langchain-core`**: LangChain's base package, the Python side of project 01's `@langchain/core`: prompts and
  Runnables, and no connection to any model.
- **`==`** pins each package to one version. Only these packages are pinned: there's no lock file here like 01's
  `package-lock.json`, so pip installs the packages they need at their newest allowed versions, which can be newer
  than the ones the tests ran with.
- **`-r requirements.txt`**, in `requirements-dev.txt`, installs everything in `requirements.txt`; the two lines after
  it add `pytest` and `httpx2`, for the tests.
- **`.venv/`**: `python -m venv .venv` makes it, a folder for this project's packages, like 01's `node_modules/`.
  Activating it makes `python` and `pip` use that folder, and `pip install -r requirements-dev.txt` fills it.

Then there are two ways to run the code: `python hello.py` runs `hello.py` on its own, and `uvicorn main:app` starts
the server.

### `hello.py` and `main.py`, from start-up to answer

`uvicorn main:app` imports `main.py` once, when the server starts, and `main.py`'s `from hello import chain` runs
`hello.py` from the top. After that, nothing runs until a request comes in:

![hello.py and main.py, from start-up to answer. Once, at start-up: main.py takes Path, FastAPI and FileResponse, and from hello import chain runs hello.py from the top: it takes PromptTemplate and RunnableLambda, ① makes prompt, ② makes to_text and ③ makes chain, none of them run yet, and ④ is skipped because hello.py was imported, not run. Then ⑤ makes app, ⑥ makes PAGE and page() for GET / and /index.html, and ⑦ makes hello() for GET /api/hello; their bodies don't run yet. uvicorn prints Application startup complete and waits. Each time you open the page: the browser asks for GET /, ⑥ page() sends index.html, the page's ⑧ fetch asks for GET /api/hello, and ⑦ hello() runs the chain: {} goes into prompt, which gives a StringPromptValue to to_text, which gives back the string; await waits for it, and return sends {"answer":"Hello World, welcome to LangChain!"}. ⑨ The page shows Hello World, welcome to LangChain!](images/start-up-to-answer.svg)

At start-up, ① to ③ and ⑤ to ⑦ only make things: the chain, the app, and its two functions, `page()` for `/` and
`/index.html` and `hello()` for `/api/hello`. ④ is skipped, because `hello.py` is imported, not run. When you open
the page, `page()` sends it (⑥), the page asks for `/api/hello` (⑧), and ⑦'s `await chain.ainvoke({})` is the line
that does the work; ⑨ shows the answer. The sections below go through the steps in order, with the code's comments
left out.

### The imports

`hello.py`'s:

```python
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
```

and `main.py`'s:

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from hello import chain
```

`hello.py` takes two names from `langchain_core`. The package is installed as `langchain-core`, with a dash, and
imported as `langchain_core`, with an underscore, because a Python name can't contain a dash. `main.py` takes `Path`
from Python's own `pathlib`, `FastAPI` and `FileResponse` from `fastapi`, and `chain` from `hello.py`. That last
line is the one to notice: importing a file runs it, so `from hello import chain` runs `hello.py` from the top and
builds the chain, once, when the server starts.

### ① The template

```python
prompt = PromptTemplate.from_template("Hello World, welcome to LangChain!")
```

`from_template()` turns a text into a prompt template, as `fromTemplate()` did in project 01. This text is fixed, so
each time the prompt runs it gives back the same words, inside a `StringPromptValue`.

### ② The converter

```python
to_text = RunnableLambda(lambda value: value.to_string())
```

`prompt.invoke({})` gives back `StringPromptValue(text='Hello World, welcome to LangChain!')`: an object, not a
string. `to_text` calls its `to_string()`, the Python version of project 01's `toString()`, and passes on the plain
text. `lambda value: value.to_string()` is Python's one-line function, like JavaScript's
`(value) => value.toString()`, and Python's `RunnableLambda(...)` takes it directly, with no `.from`.

### ③ The chain

```python
chain = prompt | to_text
```

`prompt | to_text` builds a `RunnableSequence`, one Runnable that runs `prompt` and then `to_text`;
`prompt.pipe(to_text)` builds the same thing. Building it runs nothing: no step is called until the chain is
invoked, in ④ or ⑦.

### ④ Running it on its own

```python
if __name__ == "__main__":
    answer = chain.invoke({})
    print(answer)
```

Python sets `__name__` to `"__main__"` only in the file you run. So `python hello.py` builds the chain, runs it and
prints `Hello World, welcome to LangChain!`. When `main.py` says `from hello import chain`, `__name__` is `"hello"`:
the file still runs from top to bottom, so the chain gets built, but this block is skipped and nothing is printed.
Python's `invoke()` gives back the string itself, so there's no `await` here. Project 01's `hello.js` had no such
check: it ran `await chain.invoke({})` every time.

Side by side with project 01's `hello.js`:

| Project 01 (JavaScript) | Project 02 (Python) |
|---|---|
| `import { PromptTemplate } from "@langchain/core/prompts";` | `from langchain_core.prompts import PromptTemplate` |
| `PromptTemplate.fromTemplate("...")` | `PromptTemplate.from_template("...")` |
| `RunnableLambda.from((value) => value.toString())` | `RunnableLambda(lambda value: value.to_string())` |
| `prompt.pipe(toText)` | `prompt \| to_text` |
| `const answer = await chain.invoke({});` | `answer = chain.invoke({})` |
| `console.log(answer);` | `print(answer)` |

### ⑤ The app

```python
app = FastAPI(title="AgenticProgramming project 2")
```

`uvicorn main:app` means "in `main.py`, serve the object called `app`", and `title=` gives the app a name. The
functions below it run only when a request comes in. With `--reload`, uvicorn also watches the folder's `.py` files:
save `hello.py` and the terminal logs `WARNING:  StatReload detected changes in 'hello.py'. Reloading...`, then the
server restarts with your change.

### ⑥ GET / sends the page

```python
PAGE = Path(__file__).resolve().parent / "index.html"


@app.get("/")
@app.get("/index.html")
async def page():
    return FileResponse(PAGE, headers={"Cache-Control": "no-cache"})
```

- `Path(__file__).resolve().parent` is the folder `main.py` is in, and `/` on a `Path` adds a name to it, so `PAGE`
  is the `index.html` next to `main.py`. A bare `"index.html"` would be looked for in whatever folder the server or
  the tests were started from.
- Each `@app.get(...)` line registers the function below it for one address, so `/` and `/index.html` both send the
  page. `FileResponse` reads the file on every request: after you edit `index.html`, a refresh shows the change,
  with no restart.
- `Cache-Control: no-cache` tells the browser to ask the server again before it reuses its saved copy of the page.
  The other FastAPI projects in this repo use port 8000 too, so without it, the browser could show this page later,
  while one of them is running.
- The page comes from the same server as the API, so its `fetch("/api/hello")` needs no `http://...` in front, which
  is why the same page works on your laptop and in Codespaces.

### ⑦ GET /api/hello runs the chain

```python
@app.get("/api/hello")
async def hello():
    answer = await chain.ainvoke({})
    return {"answer": answer}
```

This is the line that does the work: `await chain.ainvoke({})` runs `prompt`, then `to_text`, and gives back the
string.

| Step | Gets | Gives back |
|---|---|---|
| `prompt` | `{}` | a `StringPromptValue` |
| `to_text` | that `StringPromptValue` | the string `Hello World, welcome to LangChain!` |
| `chain` (both steps, in order) | `{}` | the same string |

- `ainvoke()` is `invoke()`'s async twin. It gives back a coroutine, an answer that arrives later, like project 01's
  Promise, so `await` waits for it ([Things to try](#things-to-try) shows what you get without it). `async def` with
  `await` lets the server work on other requests while this one waits.
- FastAPI turns the returned dict into JSON: `{"answer":"Hello World, welcome to LangChain!"}`.

### ⑧ The page calls /api/hello

```js
fetch("/api/hello")
```

The script sits at the end of the page, outside any function, so it runs once, as soon as the page loads. Until the
answer comes back, the page shows "Asking the server…". Each refresh loads the page again and so calls the server
again: two more lines in the terminal, `"GET / HTTP/1.1" 200 OK` for the page and `"GET /api/hello HTTP/1.1" 200 OK`
for its fetch.

### ⑨ The page shows the answer, or what went wrong

```js
  .then((res) => {
    if (!res.ok) throw new Error(`the server answered HTTP ${res.status}`);
    return res.json();
  })
  .then((data) => {
    document.getElementById("answer").textContent = data.answer;
  })
  .catch((err) => {
    document.getElementById("answer").textContent = `Something went wrong: ${err.message}`;
  });
```

Each `.then` runs when the step before it has finished. `fetch()` itself fails only when no answer comes back (the
server is stopped, say); an error answer such as a 500 still arrives as a normal answer. So the page checks `res.ok`
(true for statuses 200 to 299) and throws its own error. `res.json()` reads the body as JSON, `data.answer` is the
greeting, and `textContent` puts it on the page. Anything that goes wrong on the way lands in `.catch`: a page opened
straight from the folder shows `Something went wrong: Failed to fetch` (Chrome's wording), and a chain that crashes
shows `Something went wrong: the server answered HTTP 500`.

## Run it

```bash
cd tutorials/02-langchain-python      # from the repo root
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
pip install -r requirements-dev.txt  # once: the packages, into .venv/
```

Creating the venv and installing are once only; activate it again in every new terminal. Then:

```bash
python hello.py                      # just the chain
uvicorn main:app --reload            # the server; Ctrl+C stops it
```

![A terminal. cd tutorials/02-langchain-python goes into the project's folder. python -m venv .venv, once, makes .venv/. source .venv/Scripts/activate, in each new terminal, makes the prompt start with (.venv). pip install -r requirements-dev.txt, once, prints a few lines per package, then Successfully installed and the packages, then a notice that a new pip is available, information only. python hello.py prints Hello World, welcome to LangChain!: the chain alone. uvicorn main:app --reload prints six lines, ending with Application startup complete: main.py is imported, the chain is built, and the server waits. Opening http://127.0.0.1:8000 adds GET / 200 OK, the page; GET /api/hello 200 OK, the page's fetch, which runs the chain; and GET /favicon.ico 404 Not Found, the browser asking for a tab icon, harmless. Ctrl+C prints five lines as the server stops.](images/run-it.svg)

`pip install` prints a few lines for each package it gets, then a `Successfully installed ...` line that lists every
package it put in `.venv/`. A `[notice]` after it, saying a new pip is available, is information only.

`python hello.py` prints:

```text
Hello World, welcome to LangChain!
```

`uvicorn main:app --reload` prints these lines, then waits:

```text
INFO:     Will watch for changes in these directories: ['...02-langchain-python']
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [46024] using StatReload
INFO:     Started server process [18724]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

- `Will watch for changes`: `--reload` watches this folder (your terminal shows its full path).
- `Uvicorn running on http://127.0.0.1:8000`: the address to open.
- `Started reloader process` and `Started server process`: with `--reload` there are two processes, one that watches
  the files and one that serves. The server process has just imported `main.py`, so the chain is built.
- `Waiting for application startup.` and `Application startup complete.`: the server is ready and waits for
  requests.

Only one server can use port 8000 at a time: if another project's server is running, stop it (Ctrl+C) first (see
[When things go wrong](#when-things-go-wrong)).

With the server running, open the page:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page (calls the server as soon as it opens) | http://127.0.0.1:8000 (or `/index.html`) | `https://<codespace-name>-8000.app.github.dev` (or `/index.html`) |
| The raw JSON | http://127.0.0.1:8000/api/hello | `https://<codespace-name>-8000.app.github.dev/api/hello` |

In Codespaces, `127.0.0.1` is the codespace, not your laptop. Use the forwarded address instead: open the **Ports**
tab next to **Terminal** and click the globe icon on port 8000, or click **Open in Browser** in the pop-up that
appears when the server starts. `<codespace-name>` is the first part of the codespace's own address, for example
`orange-succotash-gw4799ggp42vqv` in `orange-succotash-gw4799ggp42vqv.github.dev`.

The page shows `Hello World, welcome to LangChain!`, and the terminal adds:

```text
INFO:     127.0.0.1:65317 - "GET / HTTP/1.1" 200 OK
INFO:     127.0.0.1:65317 - "GET /api/hello HTTP/1.1" 200 OK
INFO:     127.0.0.1:65183 - "GET /favicon.ico HTTP/1.1" 404 Not Found
```

- `GET /`: the browser asks for the page, and `page()` sends it (⑥).
- `GET /api/hello`: the page's fetch (⑧); `hello()` runs the chain (⑦).
- `GET /favicon.ico ... 404 Not Found`: the browser asks every site for a tab icon, and this one has none. Harmless.

The curl example is for bash (macOS, Linux, Codespaces, Git Bash). Run it in a second terminal, since the server
keeps the first one busy:

```bash
curl http://127.0.0.1:8000/api/hello
# {"answer":"Hello World, welcome to LangChain!"}
```

Ctrl+C stops the server:

```text
INFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [18724]
INFO:     Stopping reloader process [46024]
```

The numbers in brackets are process IDs, and the number after `127.0.0.1:` is the browser's side of the connection:
yours will differ.

## Test it

There are 7 tests, all plain: no key, no network and no server to start. They come from 6 test functions, because
`@pytest.mark.parametrize` runs the page test once for `/` and once for `/index.html`.

| Test | What it checks |
|---|---|
| `test_chain_returns_the_message_as_a_string` | `chain.invoke({})` returns exactly the greeting, as a `str` |
| `test_prompt_gives_an_object_and_to_text_turns_it_into_text` | The prompt alone gives a `StringPromptValue`, and `to_text` turns it into the greeting |
| `test_running_hello_py_prints_the_message` | `python hello.py`, run as a separate process, prints the greeting |
| `test_api_returns_the_answer` | `GET /api/hello` answers 200 with `{"answer": "Hello World, welcome to LangChain!"}` |
| `test_page_is_served_and_calls_the_api[/]` and `[/index.html]` | Both addresses send HTML, marked `no-cache`, that contains `fetch("/api/hello")` |
| `test_page_checks_res_ok_and_shows_what_went_wrong` | The page checks `res.ok`, and shows `Something went wrong: ...` when something fails |

`TestClient(app)` calls the FastAPI app directly, inside the test run, so there's no uvicorn to start. The script
test runs `hello.py` with `sys.executable`, the Python that is running the tests (your venv's), and reads what it
prints. pytest can `import hello` and `import main` because of `pytest.ini` (see [Files](#files)).

```bash
python -m pytest          # all the tests; the last line says "7 passed"
python -m pytest -v       # the same tests, one line each, with its name
```

## When things go wrong

An error can print many lines. The "What you see" column quotes the part that says what went wrong.

| What happens | What you see | What to do |
|---|---|---|
| PowerShell won't run the activate script | `...Activate.ps1 cannot be loaded because running scripts is disabled on this system` | Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` once, then activate again (or use Git Bash or Command Prompt) |
| The venv isn't active, or the packages aren't installed | `ModuleNotFoundError: No module named 'langchain_core'`, or the shell can't find `uvicorn` (bash: `uvicorn: command not found`; PowerShell: `The term 'uvicorn' is not recognized ...`). Ubuntu may instead say `Command 'uvicorn' not found, but can be installed with:` and suggest `sudo apt install uvicorn` | Activate the venv (don't install uvicorn another way); if that isn't enough, run `pip install -r requirements-dev.txt` |
| A command run outside the project folder, such as the repo root | uvicorn: `ERROR:    Error loading ASGI app. Could not import module "main".` (with `--reload`, it keeps running); python: `can't open file '...hello.py': [Errno 2] No such file or directory`; pip: `ERROR: Could not open requirements file: [Errno 2] No such file or directory: 'requirements-dev.txt'` | Press Ctrl+C if uvicorn is still running, `cd tutorials/02-langchain-python`, then run the command again |
| Port 8000 is taken, usually by another project's server | On Windows, when both servers were started with `--reload` as here: no error. This terminal shows the usual `Uvicorn running on http://127.0.0.1:8000`, but the other server goes on answering: the page is the other project's (its tab title says which), and the `"GET ..."` lines appear in the other server's terminal, not this one. If the other server runs without `--reload`, this one stops with `ERROR:    [WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions`. On Linux and Codespaces, this one stops with `ERROR:    [Errno 98] Address already in use`; on macOS, the same with `[Errno 48]` | Stop the other server (Ctrl+C in its terminal). If this one stopped, start it again; if it is still running, the next refresh reaches it. Or start this one with `uvicorn main:app --reload --port 8001` and use 8001 in the address |
| index.html was opened straight from the folder | The page says `Something went wrong: Failed to fetch` (Chrome's wording) | Open http://127.0.0.1:8000 instead: the server sends the page and answers its fetch |
| A `{` or `}` in the greeting | With `{World}`: `python hello.py` stops with `KeyError: "Input to PromptTemplate is missing variables {'World'}. ...`, and on the server the page says `Something went wrong: the server answered HTTP 500` while the terminal shows `ERROR:    Exception in ASGI application` and a long traceback ending in the same `KeyError`. With a lone `}` or `{`, the template itself is refused: `python hello.py` stops, and the server can't start, with a traceback ending in `ValueError: Single '}' encountered in format string`, `ValueError: Single '{' encountered in format string` (a `{` at the very end) or `ValueError: end of string while looking for conversion specifier` | Read the last line of the error, then take the braces out or undo the edit |
| A 404 you didn't ask for | `"GET /favicon.ico HTTP/1.1" 404 Not Found` in the terminal | Nothing: the browser asks every site for a tab icon, and this one has none |

## Things to try

1. **Change the greeting.** In `hello.py`, change the text in `from_template(...)`, for example to
   `"Good morning, welcome to LangChain!"`. `python hello.py` prints your text. With `uvicorn main:app --reload`
   running, saving the file logs `StatReload detected changes in 'hello.py'. Reloading...`, and a refresh shows your
   text on the page. Leave out `{` and `}`: they have a special meaning in a template, and `python hello.py` would
   stop with an error (see [When things go wrong](#when-things-go-wrong)).
2. **Use `str(value)` instead of `to_string()`.** Change the converter to
   `RunnableLambda(lambda value: str(value))`. `python hello.py` now prints `text='Hello World, welcome to LangChain!'`:
   Python's `str()` describes the object instead of giving its text. `python -m pytest` catches it with
   `4 failed, 3 passed`: only the page tests still pass. Put `to_string()` back.
3. **Drop the converter.** Change the chain to `chain = prompt`. `/api/hello` now sends the prompt's object, turned
   into JSON, `{"answer":{"text":"Hello World, welcome to LangChain!","type":"StringPromptValue"}}`, and the page
   shows `[object Object]`, which is what JavaScript makes of an object where it expects text. That's the job
   `to_text` does.
4. **See what `ainvoke()` gives back.** In ④, change `chain.invoke({})` to `chain.ainvoke({})`, with no `await`.
   `python hello.py` prints `<coroutine object RunnableSequence.ainvoke at 0x...>` and then a warning,
   `RuntimeWarning: coroutine 'RunnableSequence.ainvoke' was never awaited` (Python 3.13 starts that line with
   `<sys>:0:`, older versions with `sys:1:`). `ainvoke()` gives back a coroutine, an answer that arrives later, like
   project 01's Promise. That's why ⑦ says `await chain.ainvoke({})`. Put `invoke` back.

## Next

**[Project 03 · Run on a button click](../03-langchain-button/README.md)**: the same chain and routes, but nothing
runs when the page opens: each click of a button calls the server once.
