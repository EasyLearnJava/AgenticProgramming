# AgenticProgramming

Agents built one step at a time, starting from the smallest LangChain chain. Every project in [`tutorials/`](tutorials)
is one small step that runs on its own: just code, a README that says what you build, what you learn and how it works,
and (from project 02 on) tests. Start at [project 01](tutorials/01-langchain-basic/README.md) and go in order: each step
builds on the one before.

**The running example is one greeting.** It starts as fixed text, "Hello World, welcome to LangChain!", then takes a
name, picks a style and greets a whole list. From project 10, Gemini writes it, and later projects measure it, stream
it, shape it into a typed object and keep its prompt in versioned files. Where a greeting is too simple to show an
idea, a project uses other material: a CSV of fruit sales (08), questions to answer (13, 14), word problems (16) and a
customer's support message (15, 16).

**What's here today:** 17 projects, from the smallest chain up to prompts kept as versioned files. **Not written
yet:** the same Gemini call without a framework, comparing models, and running an open model yourself; after those,
tools, agents and memory.

## Who it's for

- **Beginners to LangChain and LLM apps** (apps built on a large language model, such as Google's Gemini) who know
  basic Python.
- **Project 01 needs a little JavaScript.** Every project after it is Python.
- **No LLM experience needed.** Projects 01 to 08 use no model and no API key, 09 sets up the key, and 10 makes the
  first real call.
- Where it helps, the READMEs compare Python with Java.

By the end you can build and test a small web app that calls Gemini safely: the key stays on the server, bad input is
refused before any call, each call's tokens, time and cost are measured, answers stream in or come back as typed
objects, and prompts live in versioned files.

## The path

Seven stages, 17 projects. Each title links to that project's README.

### 01 · The smallest chain, in JavaScript

The words every later project uses (prompt template, Runnable, pipe, invoke), in one file with nothing else around
them.

| # | Project | What you build | What you learn |
|---|---|---|---|
| 01 | [LangChain basic](tutorials/01-langchain-basic/README.md) | `hello.js`: a prompt template piped into a converter step. `npm start` prints "Hello World, welcome to LangChain!" | `PromptTemplate`, `RunnableLambda`, `.pipe()`, `await chain.invoke({})`, npm basics |

### 02-07 · LangChain without a model

With no model, every answer is predictable and free, so you can learn how a chain is built, served by FastAPI, called
from a web page and tested.

| # | Project | What you build | What you learn |
|---|---|---|---|
| 02 | [LangChain basic (Python)](tutorials/02-langchain-python/README.md) | The same chain in Python, a FastAPI server, and a page that calls `GET /api/hello` as soon as it opens; the repo's first tests | `prompt \| to_text`, `if __name__ == "__main__":`, FastAPI and uvicorn, `ainvoke()`, `fetch()`, pytest with `TestClient` |
| 03 | [Run on a button click](tutorials/03-langchain-button/README.md) | A page that calls the server once per click, with the button greyed out while it waits | `addEventListener("click", ...)`, `async`/`await`, `try`/`catch`/`finally` |
| 04 | [Pass one input](tutorials/04-langchain-input/README.md) | A name typed into the page, sent as JSON in a `POST`, trimmed and checked before the chain runs | a `{name}` template variable, `sys.argv`, a Pydantic body model, 422 errors in plain words |
| 05 | [Pass several inputs](tutorials/05-langchain-inputs/README.md) | A greeting, a name and a city in one template, with a default greeting, and each bad field's error shown next to it | several variables, `prompt.partial()`, `Literal` and optional fields, `model_dump(exclude_none=True)` |
| 06 | [Run steps side by side](tutorials/06-langchain-parallel/README.md) | One name in, four results out: three steps side by side plus one computed key, and the chain's graph | `RunnableParallel`, `RunnablePassthrough`, `.assign()`, `get_graph().draw_mermaid()` |
| 07 | [Branch and batch a chain](tutorials/07-langchain-branch/README.md) | A formal or a casual greeting picked for each person, and `POST /api/batch` for 1 to 10 people at once | `RunnableBranch`, `batch()` and `abatch()`, `config={"max_concurrency": 3}`, a list in a Pydantic model |

### 08 · Building with an AI coding assistant

A coding assistant can write code fast. This step practises the habits that keep it right: small, clear requests,
and you read, run and test every change before you keep it.

| # | Project | What you build | What you learn |
|---|---|---|---|
| 08 | [Vibe-code a data app](tutorials/08-vibecode-data-app/README.md) | A Streamlit page over a CSV of fruit sales (filters, totals, two charts), and four mini-specs to rebuild it with your own assistant | mini-specs (goal, inputs, done when), reviewing each change, Streamlit's rerun model, pandas, `AppTest` |

### 09 · The Gemini key

An API key is a password for your account: whoever has it can call the model, and you pay for it. So it stays on the
server: out of the page, out of every response and out of git.

| # | Project | What you build | What you learn |
|---|---|---|---|
| 09 | [Get a Gemini key and keep it secret](tutorials/09-gemini-key/README.md) | A key restricted to the Gemini API, with a budget alert, kept in `.env`; `config.py`, which stops without it; a server and page that never show it | environment variables and `python-dotenv`, failing fast with your own error class, `.gitignore` and `.env.example` |

### 10-12 · Your first real LLM

A real model is priced by the token, answers differently every time and can fail, so you learn to call it with its
errors handled, measure what each call would cost, and stream the answer.

| # | Project | What you build | What you learn |
|---|---|---|---|
| 10 | [First real LLM call](tutorials/10-gemini-llm/README.md) | `prompt \| model \| parser` with Gemini writing a welcome for any name: a 422 before any call for a bad name, a 502 when Gemini fails | `ChatGoogleGenerativeAI`, `StrOutputParser`, `max_output_tokens`, plain and live tests |
| 11 | [Tokens and cost](tutorials/11-gemini-tokens/README.md) | The same welcome with its numbers: tokens counted before and after, the time, the price, and a cap you set for each call | tokens, `get_num_tokens()`, `usage_metadata`, `model.bind()`, why temperature is ignored on this model |
| 12 | [Streaming answers](tutorials/12-gemini-stream/README.md) | A three-paragraph welcome that appears piece by piece, in the terminal and on the page, with the time to the first words | `stream()` and `astream()`, generators, `StreamingResponse`, `getReader()`, errors in a stream |

### 13-15 · Prompt basics

How you write the prompt decides what comes back. These are the three tools you'll reach for most: a role, examples,
and a schema for the answer.

| # | Project | What you build | What you learn |
|---|---|---|---|
| 13 | [Give the model a role: the system prompt](tutorials/13-gemini-system-prompt/README.md) | One question answered twice, for a beginner and for an expert, where only the system prompt changes | `ChatPromptTemplate.from_messages`, system and human messages, two calls at once, prompt injection |
| 14 | [Show, don't tell: few-shot examples](tutorials/14-gemini-few-shot/README.md) | 10 questions asked with and without three example answers, each answer's format checked in code | `FewShotChatMessagePromptTemplate`, examples vs instructions, `batch()` with `return_exceptions=True` |
| 15 | [Structured output](tutorials/15-gemini-structured/README.md) | A greeting and a support ticket that come back as checked Pydantic objects, each field in its own box on the page | `with_structured_output()`, a Pydantic class as the schema, `OutputParserException`, `response_model=` |

### 16-17 · Reasoning and prompt files

Reasoning trades tokens and time for right answers, and a prompt kept in a versioned file can be reviewed, compared
and rolled back like code.

| # | Project | What you build | What you learn |
|---|---|---|---|
| 16 | [Reasoning: chain-of-thought and thinking](tutorials/16-gemini-reasoning/README.md) | Six word problems asked three ways (directly, step by step, with thinking) and scored in code; a badly written prompt, fixed | chain-of-thought, `thinking_level`, what reasoning costs, `asyncio.gather` with a `Semaphore`, prompt anti-patterns |
| 17 | [Prompts as versioned files](tutorials/17-gemini-prompt-files/README.md) | The greeting prompt as files, `prompts/greeting.v1.md` to `v3.md`, the active one picked in `prompt_versions.toml`, and every answer labelled with its version | prompt files, fingerprints with `hashlib`, `tomllib`, `with_config()`, checking files at start-up |

## Before you start

- **Python 3.11 or newer**, for projects 02 to 17 (08's pandas and 17's `tomllib` need 3.11). Check with
  `python --version`; on macOS and Linux it may be called `python3`.
- **Node.js 20 or newer**, which comes with npm, for project 01 (22 is used here). Check with `node --version`.
- **git**, to get the code. Check with `git --version`.
- **A Google account**, for the Gemini key you make in project 09. Gemini's free tier is enough.
- **Or install nothing: use GitHub Codespaces.** On the repo's GitHub page, click **Code**, then the **Codespaces**
  tab, then **Create codespace on main**. You get a computer in the cloud with VS Code in your browser, Python, Node
  and git already installed, and the repo already cloned.

To get the code onto your own computer:

```bash
git clone https://github.com/EasyLearnJava/AgenticProgramming.git
cd AgenticProgramming
```

On Windows, clone into a short folder such as `C:\code`: in a deep folder, installing Streamlit (project 08) can hit
Windows' 260-character limit on file paths.

## How a project is laid out

The Python projects share one layout. Here is project 02's:

```text
tutorials/02-langchain-python/
├── hello.py              the chain; runs on its own: python hello.py
├── main.py               the FastAPI server: GET / and /index.html send the page; /api/... runs the chain
├── index.html            the page: plain HTML and a little JavaScript that calls /api/...
├── tests/
│   └── test_hello.py     the tests, run with pytest
├── pytest.ini            pytest's settings: import hello and main from this folder, look for tests only in tests/
├── requirements.txt      the app's packages, each pinned to one exact version with ==
├── requirements-dev.txt  requirements.txt plus the test tools, pytest and httpx
└── README.md             what you build and learn, how it works, how to run it and test it
```

Later projects add a few files:

| From | Added | What it's for |
|---|---|---|
| project 09 | `config.py` | Loads `GOOGLE_API_KEY` and checks it: with no usable key, the script or the server stops with a one-line message. `python config.py` runs the check on its own |
| project 09 | `.env.example` | The template for `.env`, the file that holds your key. It's committed, so it only ever holds a placeholder |
| project 10 | `tests/conftest.py` | Runs before the tests and skips the live tests (the ones that call Gemini) when there's no key |
| project 10 | a `live` marker in `pytest.ini` | Lets you pick the live tests, or leave them out (see [Tests](#tests)) |

`config.py`, `.env.example` and `tests/conftest.py` are the same file in every project that has them.

Four projects differ:

- **01** is JavaScript: `hello.js`, `package.json` and `package-lock.json`, and no tests.
- **08** is a Streamlit app: `app.py` (the page), `data.py` (the pandas functions), `fruit_sales.csv`,
  `.streamlit/config.toml` and `tests/test_data.py`. It has no `main.py` or `index.html`.
- **09** has no chain yet, so no `hello.py`: `python config.py` is the script you run on its own, and the tests are in
  `tests/test_config.py`.
- **17** adds `prompts/` (the prompt files), `prompt_files.py` and `prompt_versions.toml`.

When you set up and run a project, `.venv/` (in 01: `node_modules/`), `__pycache__/` and `.pytest_cache/` appear, and
from project 09 on you add your own `.env`. The repo's `.gitignore` keeps all of them out of git.

## Run a project

Each project installs and runs on its own, from its own folder. Start in the repo's top folder; for project 02:

```bash
cd tutorials/02-langchain-python
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell: .venv\Scripts\Activate.ps1
#   Windows Git Bash:   source .venv/Scripts/activate
pip install -r requirements-dev.txt
```

Creating the venv and installing are once per project; activate it again in every new terminal. If `python` isn't
found on macOS or Linux, use `python3` for the `python -m venv .venv` step; inside the active venv, `python` works
everywhere. Then:

```bash
python hello.py                      # the chain on its own, in the terminal
uvicorn main:app --reload            # the server; Ctrl+C stops it
```

`--reload` restarts the server when you save a `.py` file, but not when you change `.env` or a prompt file: then press
Ctrl+C and start it again. With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 | `https://<codespace-name>-8000.app.github.dev` |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

In Codespaces, `127.0.0.1` is the codespace, not your laptop: open the **Ports** tab next to **Terminal** and click the
globe icon on port 8000, or click **Open in Browser** in the pop-up that appears when the server starts.

Only one server can use port 8000 at a time: stop the previous project's server (Ctrl+C) before starting this one.

A few projects run differently:

- **01** (JavaScript) prints one line in the terminal, with no server and no page:

  ```bash
  cd tutorials/01-langchain-basic
  npm install                          # once: downloads @langchain/core into node_modules/
  npm start                            # runs hello.js: Hello World, welcome to LangChain!
  ```

- **08** (Streamlit): after the setup, `python data.py` tries the data functions, and `streamlit run app.py` serves
  the page at http://localhost:8501 (in Codespaces, `https://<codespace-name>-8501.app.github.dev`, port 8501 in the
  **Ports** tab). It doesn't use port 8000.
- **09 to 17** need your key first: see the next section. 09 has no chain yet, so `python config.py` takes the place of
  `python hello.py` there.

Each project's README has its exact commands, curl examples and what you should see.

## Your Gemini key (projects 09 on)

**The rule: the key stays on the server.** It lives in a `.env` file in the project's folder, or in a Codespaces
secret, and never in the code, the page, a response, a commit, a screenshot or a chat.

1. **Make it once, in [project 09](tutorials/09-gemini-key/README.md).** You create an API key in the Google Cloud
   console, restricted to the Gemini API, with application restrictions set to None, and set a budget alert. Then you
   save it in that project's folder:

   ```bash
   cd tutorials/09-gemini-key
   cp .env.example .env                 # then open .env and replace your-key-here with your key
   ```

2. **Copy it into each later project, once.** Each project reads only the `.env` in its own folder, so from the new
   project's folder (`tutorials/10-gemini-llm`, say):

   ```bash
   cp ../09-gemini-key/.env .env
   ```

3. **Or use a Codespaces secret instead of files.** On GitHub, go to **Settings → Codespaces → Secrets → New secret**,
   name it `GOOGLE_API_KEY` and give it access to this repository. Every project sees it, with nothing to copy. Stop
   and restart the codespace after adding it: a running codespace doesn't see a new secret.
4. **Check it** in any project from 09 on with `python config.py`. It prints `GOOGLE_API_KEY is set.`, never the key
   itself, or one line that says what to fix.

`.env` is in the repo's `.gitignore`, so git never sees it.

Every run of `hello.py`, every click and every curl with a good input in projects 10 to 17 is a real call to Gemini,
and uses your key's quota. The free tier is enough for these projects, but it limits how many calls you can make per
minute (see [When things go wrong](#when-things-go-wrong)). Each of them also caps the length of every answer with
`max_output_tokens`.

## Tests

Every Python project has a `tests/` folder. Run the tests from the project's folder, with its venv active:

```bash
python -m pytest                     # every test; the live ones are skipped when there's no key
python -m pytest -m "not live"       # only the plain tests: no call, no cost
python -m pytest -m live             # only the live tests: real calls to Gemini
```

- **Plain tests** need no key and no network, and cost nothing. They call the app directly (with FastAPI's
  `TestClient`, or Streamlit's `AppTest` in 08), so there's no server to start first, and from project 10 on a
  stand-in takes Gemini's place.
- **Live tests** (projects 10 to 17) are marked `@pytest.mark.live` and call the real Gemini, so they need your key
  and use its quota. Gemini's words change every time, so they check what must hold, such as the shape of the answer,
  not its exact words. With no key, `tests/conftest.py` skips them with the reason
  `live test: needs GOOGLE_API_KEY (see project 9)`; `python -m pytest -rs` shows it.

Projects 02 to 09 have only plain tests, so `python -m pytest` is all they need. Project 01 has no tests: running it is
the check. Each project's README says what its tests check, and how many there are.

## When things go wrong

| What happens | What you see | What to do |
|---|---|---|
| Port 8000 is taken, usually by the previous project's server | uvicorn stops with an error about the address: `[Errno 98] Address already in use` on Linux and Codespaces, `[Errno 48]` on macOS, `[Errno 10048]` or `[WinError 10013]` on Windows. On Windows, when both servers use `--reload`, there may be no error at all: the old server keeps answering, and the page is the previous project's (its tab title says which) | Stop the other server (Ctrl+C in its terminal), then start this one again. Or run this one on another port, `uvicorn main:app --reload --port 8001`, and open http://127.0.0.1:8001 |
| Windows PowerShell won't activate the venv | `...Activate.ps1 cannot be loaded because running scripts is disabled on this system` (in project 01, the same for `npm.ps1`) | Run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` once, then activate again. Or use Git Bash |
| The venv isn't active, in a new terminal say | `uvicorn: command not found` (PowerShell: `The term 'uvicorn' is not recognized ...`), or a `ModuleNotFoundError` naming a package such as `langchain_core` | Activate the venv again (see [Run a project](#run-a-project)); if that isn't enough, run `pip install -r requirements-dev.txt` |
| No key in this project's folder | `Can't build the chain: GOOGLE_API_KEY is not set. ...` (in 09: `Can't start the server: ...`). With `--reload`, uvicorn still says `Uvicorn running on ...`, but the page won't open | In 10 to 17, `cp ../09-gemini-key/.env .env` in this project's folder; in 09, make the key first (see [Your Gemini key](#your-gemini-key-projects-09-on)). Then press Ctrl+C and start the server again: `--reload` doesn't notice a new `.env` |
| A wrong key | The page says `Gemini didn't answer (GoogleInvalidRequestError).` (in 11: `ClientError`), and the server's terminal says `API key not valid` | Fix the key in `.env` (or in the Codespaces secret), then restart the server |
| A key restricted to websites | The page says `Gemini didn't answer (...)`, and the server's terminal says `403 PERMISSION_DENIED` and "Requests from referer &lt;empty&gt; are blocked." | The server sends no website address, so Google blocks every call. Make a server key with application restrictions set to None, as [project 09](tutorials/09-gemini-key/README.md) shows. Don't use the "Browser key (auto created by Firebase)" |
| Too many calls in a minute on the free tier | Answers slow down while the library retries by itself, then an error such as `Gemini didn't answer (GoogleRateLimitError).` The terminal says `429 RESOURCE_EXHAUSTED` | Wait a minute and try again |
| `.env` saved as UTF-16, which Windows PowerShell 5's `echo ... > .env` does | `.env isn't saved as UTF-8 text. Open it in an editor and save it with UTF-8 encoding.` | Save `.env` as UTF-8 in your editor, or make it again with `cp .env.example .env` and put the key back in |
| Printing non-English text or an emoji on Windows into a file, a pipe, or Git Bash's terminal (which Python sees as a pipe) | `UnicodeEncodeError: 'charmap' codec can't encode character ...` | Run `export PYTHONUTF8=1` (Git Bash) or `$env:PYTHONUTF8 = "1"` (PowerShell) first: Python then writes UTF-8 |
| A streamed answer arrives all at once | The whole answer appears in one go, usually in Codespaces | A proxy between the page and the server held the pieces back: see [project 12](tutorials/12-gemini-stream/README.md#when-things-go-wrong). Try the page on your laptop, or `python hello.py`, which goes through no proxy |

Projects 10 to 17 also print `Direct use of automatic function calling (AFC) ... is not recommended` on the first call
in each run. It comes from `google-genai`, the library under `langchain-google-genai`, and it's harmless. Each project's
README has its own table for its own surprises.

## Adding the next step

For the maintainer, when a new project joins:

1. **The folder**: `tutorials/NN-short-name/`, with the next two-digit number and a few lowercase words joined by
   hyphens, like `17-gemini-prompt-files`.
2. **The files** every Python project has (see [How a project is laid out](#how-a-project-is-laid-out)): `hello.py`
   (the chain, runnable on its own), `main.py` (`GET /` and `/index.html` serve the page, plus `/api/...`),
   `index.html` (a plain page whose `<title>` and `<h1>` are "Project N: the README's title"), `tests/`, `pytest.ini`,
   `requirements.txt` (every package pinned with `==`), `requirements-dev.txt` and `README.md`. A project that calls
   Gemini also gets `config.py`, `.env.example` and `tests/conftest.py`, copied unchanged, and the `live` marker in
   `pytest.ini`.
3. **The code's habits**: a docstring at the top of every `.py` file (what it does, an input -> output example, how to
   run it), numbered steps ① ② ③ in the comments, a 422 for bad input before any model call, and a 502 when Gemini
   fails, with the full reason logged on the server and only the error's type sent to the page.
4. **The README**, with these sections in this order: `# NN · Title`, a short intro with an input -> output block,
   What you'll build, What you'll learn, What's new since project NN-1, Before you start, Files (every file in the
   folder), How it works, Run it, Test it (the only place with test counts), When things go wrong, Things to try,
   Next.
5. **The links**: point the previous project's Next at the new project, and add a row for it to
   [The path](#the-path), in its stage or a new one.
6. **The checks**: `python -m pytest` passes, every command in the README works, and every link opens.
