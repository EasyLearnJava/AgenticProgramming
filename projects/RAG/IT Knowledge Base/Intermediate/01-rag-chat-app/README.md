# 01 · RAG Chat App

An IT help-desk chat app that answers questions from a knowledge base of IT support articles: the app from
[Basic 10](../../Basic/10-chat-page/README.md), built again production grade. It finds the same chunks, sends the
same prompt and shows the same sources. What changed is how it's built (and so its API: see What Changed From
Basic 10): one package per layer, each replaceable,
every setting in `config.yaml`, errors that always answer in one shape, and logs in which one trace ID follows a
request through every layer, and which the page shows under each answer: what happened behind the scenes. Built
with **FastAPI**, **LangChain**, **Gemini** (`gemini-embedding-001` and `gemini-3.5-flash-lite`), **Qdrant** (in
memory), **Pydantic** and Python's `logging`.

> **Needs:** Python 3.11 or newer, a Gemini API key, and a web browser. Starting it makes 1 call to Gemini (the 28
> chunks, embedded in one batch), or none once `python main.py index` has saved their vectors; each question makes 2.

---

## 🎯 What This Project Does

- **Answers IT questions from the knowledge base**: the 10 articles, cut into 28 chunks; the 5 closest chunks to
  each question; Gemini asked to answer from them only; up to 3 articles shown as sources. On a chat page at
  http://127.0.0.1:8000, through the API, or in the terminal
- **Traces every call**: each HTTP request, each question asked in the terminal, and the build at start-up gets a
  trace ID. Every log line written for it carries that ID, whichever layer wrote it, even from a worker thread.
  Responses return it in an `X-Trace-ID` header and in error bodies; the page shows it under each answer and error
- **Times each stage**: one log line per stage (load, split, embed, store, search, retrieve, generate, the whole
  question) with its duration and what it did: the chunks found with their scores, the tokens in and out, why the
  model stopped
- **Shows what happened behind the scenes, on the page**: each request gets a row of numbered boxes, two side by
  side: the answer (or what went wrong, and where); the pipeline, its steps numbered in the order they ran, each with
  its time and its share of the request; the time per step on one time scale, the slowest marked; every call it made,
  counted by kind (model calls, HTTP requests, vector store calls, retries, tool calls, failures), a dot per call; every
  log line, in order, each tagged with its step; and the chunks and the prompt the model was given. The build at
  start-up gets the same boxes
- **Logs to two places**: readable text on the console, and one JSON object per line in `logs/app.log`, rotated at
  5 MB. The API key is masked in both, and a question's text is logged there only at `DEBUG`
- **Fails clearly**: one hierarchy of errors, each with a stable code. Every API error answers in one JSON shape,
  with the trace ID, whether trying again may work, and nothing internal; the details go to the log (and to the
  request's trace, while traces are kept: that's what they're for). A bad setting, key, log file or data file stops
  the start with one line naming the problem, never a traceback
- **Bounds every outside call**: each call to Gemini has a 30-second timeout and up to 3 attempts; each question
  the API answers has a 60-second deadline, or a 504
- **Embeds the knowledge base once, not at every start**: `python main.py index` saves the chunks' vectors in
  `data/vectors.json`, and each start loads them, with no call to Gemini, when every one of its chunks has one from
  the same model; otherwise it embeds the chunks, and the log says why. On Vercel, each deployment's build runs it
- **Checks what comes in**: `config.yaml` (unknown keys, missing values, ranges), the data file (every row read, or
  none), and each question (1 to 500 characters, no unknown fields), before any of it costs a call
- **Is built from replaceable parts**: each provider sits behind an interface (LangChain's `BaseLoader`,
  `Embeddings` and `BaseChatModel`, or the app's `BaseVectorStore`), used through the layer's own thin class;
  `src/pipeline/factory.py` is the one file that picks the classes, and `config.yaml` names the providers
- **Serves safely**: liveness and readiness checks (`/health/ready`: built, and the store holds every chunk; it
  calls no model, so a load balancer asking every few seconds costs no quota), a content security policy on the page
  (its script and styles are files of their own: nothing inline), and security headers on every response

**Try it:** start it, open http://127.0.0.1:8000, click **Ask**, and read the boxes beside the answer.

### What Changed From Basic 10

The same articles, chunks, prompt and sources; everything around them is new:

| | Basic 10 | This project |
|---|---|---|
| Starting it | `uvicorn main:app` | `python main.py` (the server) or `python main.py ask` (the terminal); a host such as Vercel imports `main.py`'s `app` |
| Settings | constants in `pipeline.py` | `config.yaml`, every value checked at start-up |
| The page | `/` and `/index.html`, one file | `/`, with its script and styles under `/static/`; each request as a row of boxes: the answer, its pipeline, its time per step, its calls, its logs, what the model was given |
| The API | `POST /api/query`, `GET /api/stats`, `GET /api/health` | `POST /api/v1/query`, `GET /api/v1/info`, `GET /api/v1/traces/{trace_id}`, `GET /health/live`, `GET /health/ready` |
| A question's body | the question | the question and nothing else: another field is a 422 |
| An answer | the answer and up to 3 sources | the same, each source with its score too, and the answer's outer spaces trimmed |
| An error | FastAPI's `{"detail": ...}`: a 422, or a 502 for any failure | `{"error": {"code", "message", "trace_id", "retryable"}}`, with its own status: 400, 404, 422, 500, 502, 503 or 504 |
| Calls to Gemini | the libraries' defaults: no timeout; 6 attempts for the chat model, 1 for the embeddings | 30 s per attempt and 3 attempts for both; 60 s per question in the API |
| The data file | read as it is | every row checked first: a bad one stops the start, named |
| The chunks' vectors | embedded at every start | embedded at every start, or once, by `python main.py index`, and then loaded at each start |
| The log | uvicorn's lines, and a traceback when an answer fails | a trace ID on every line, a span per stage, JSON lines in `logs/app.log`, each request's trace on the page |

---

## 🏗️ Architecture

```text
main.py   the one way in: check the settings and the key → set up logging → build the engine → serve, or ask
   │
   ├── serve ──→ src/api: TraceMiddleware → error handlers → routes ──┐
   │                                                                  ↓
   ├── ask ──────────────────────────────────────────────→ src/pipeline: RAGEngine (factory.py wires it)
   │                                                          │
   └── index ─────────→ index(), once per deploy:  ingestion → chunking → embeddings → the vector file
                        build(), at each start:    ingestion → chunking → the vector file, or embeddings → vectordb
                        query(), each question:    retrieval (embeddings → vectordb) → prompts → llm
                                                              │
   across every layer:  src/config        the settings, from config.yaml; the key, from .env
                        src/observability the trace ID and a timed span per stage, on every log line; the trace
                                          store, which keeps each API request's lines for the page
                        src/exceptions.py one hierarchy of errors, each with its code and HTTP status
```

### One Question, Traced

```text
POST /api/v1/query  {"question": "How do I fix VPN connection timeouts?"}
  TraceMiddleware             a new trace ID, e.g. 67464f61fb33c2bd, for every line below
  └─ pipeline.query           the whole question                              (deadline: 60 s)
     ├─ retrieval.retrieve    the 5 closest chunks, each with its score
     │  ├─ embeddings.embed_query    the question's vector                   (1 call to Gemini)
     │  └─ vectordb.search           Qdrant, in a worker thread
     ├─ prompts.build         the chunks and the question, into the prompt
     └─ llm.generate          the answer, its tokens, why it stopped          (1 call to Gemini)
  Request finished            method, path, status code, duration
← 200 {"answer": "...", "sources": [...]}    with the header X-Trace-ID: 67464f61fb33c2bd

GET /api/v1/traces/67464f61fb33c2bd           the page, right after: every line above, for its boxes
```

A span's line is written when the stage ends, so in the log the inner stages come first; the trace puts each stage
where it started.

---

## 📁 Project Structure

```text
01-rag-chat-app/
├── main.py                           # the one way in: python main.py (serve), ask or index; app, for Vercel
├── config.yaml                       # every setting except the key: one section per layer
├── vercel.json                       # Vercel's build: python main.py index, skipped if nothing here changed
├── .env.example                      # copy to .env and put your Gemini key in it; .env never goes into git
├── data/
│   ├── sample_it_kb.csv              # the knowledge base: 10 IT support articles
│   └── vectors.json                  # the chunks' vectors, once python main.py index saves them (not in git)
├── logs/                             # app.log (JSON lines) and its rotated copies, written at run time
├── static/                           # the chat page: index.html, app.js (each request's boxes too), styles.css
├── src/
│   ├── exceptions.py                 # AppError and its subclasses; upstream_error() for any provider's error
│   ├── config/settings.py            # Settings (one section per layer), load_settings(), load_api_key()
│   ├── observability/
│   │   ├── tracing.py                # the current trace (a context variable), trace_context(), span()
│   │   ├── logging_setup.py          # setup_logging(): console text + JSON file, trace IDs, the key masked
│   │   └── trace_store.py            # TraceStore: each API request's log lines, kept for the page to show
│   ├── ingestion/loader.py           # KBLoader: the CSV file → Documents, all rows checked
│   ├── chunking/chunker.py           # Chunker: Documents → chunks, each with a stable chunk_id
│   ├── embeddings/
│   │   ├── embedder.py               # create_embedding_model(); Embedder: batches, checks, errors
│   │   └── vector_file.py            # VectorFile: the chunks' vectors saved, loaded only when every chunk has one
│   ├── vectordb/vector_store.py      # BaseVectorStore (the interface), QdrantStore, create_vector_store()
│   ├── retrieval/retriever.py        # KBRetriever: a LangChain retriever; embed, then search
│   ├── prompts/prompt_templates.py   # ANSWER_PROMPT, PROMPT_VERSION, format_context()
│   ├── llm/llm_client.py             # create_chat_model(); LLMClient: one call, timed, tokens logged
│   ├── pipeline/
│   │   ├── rag_engine.py             # RAGEngine: build(), index(), query(), aquery(), check_ready(), stats()
│   │   └── factory.py                # create_engine(): the one place the parts are chosen
│   ├── api/
│   │   ├── app.py                    # create_app(): routes, error handlers, middleware, the page's files
│   │   ├── routes.py                 # the page, /health/*, /api/v1/info, /api/v1/query, /api/v1/traces/{id}
│   │   ├── schemas.py                # what each route takes and gives back, and the one error shape
│   │   ├── errors.py                 # every failure → the one error shape, logged once
│   │   └── middleware.py             # TraceMiddleware: trace ID, request log line, headers, last-resort 500
│   └── utils/helpers.py              # elapsed_ms(), truncate(), print_result()
├── tests/                            # 185 tests: one file per layer, plus the API and main.py
├── requirements.txt                  # the packages, each pinned to an exact version
├── requirements-dev.txt              # requirements.txt plus pytest and httpx2, for the tests
├── pytest.ini                        # lets the tests import main and src, and finds them in tests/
├── ruff.toml                         # the linter's rules, PEP 8 naming among them
└── .gitignore                        # .env, logs, the saved vectors, .venv and caches stay out of git
```

Each package's `__init__.py` says what the package is for. Every module starts with what it handles and how it's
used.

### Naming Conventions

| What | Convention | Examples |
|---|---|---|
| Packages | one lower-case noun per layer; a layer's settings are the `config.yaml` section of the same name (`observability` reads `logging` and `tracing`) | `ingestion`, `embeddings`, `vectordb`, `llm` |
| Modules | `snake_case`, named for what they hold | `loader.py`, `vector_store.py`, `llm_client.py` |
| Classes | `PascalCase` nouns, an acronym in capitals; an interface starts with `Base`; a provider's class starts with its name | `RAGEngine`, `APISettings`, `BaseVectorStore`, `QdrantStore` |
| Layer words | `vectordb` is the layer: its package, settings and spans. A vector store is the object in it, LangChain's word for it | `vectordb.search`, `BaseVectorStore` |
| Errors | end in `Error`; one subclass per kind of failure | `ConfigError`, `UpstreamTimeoutError` |
| Functions | `snake_case` verbs: `create_*` builds a part, `load_*` reads a file or the environment | `create_engine()`, `load_settings()` |
| Constants | `UPPER_SNAKE_CASE` | `PROMPT_VERSION`, `MAX_QUESTION_LENGTH` |
| Private | a leading `_`: used only inside its module | `_google()`, `_check_row()` |
| Spans | `layer.action`, ending `ok`, `failed` or `cancelled`; the line goes to the layer's logger, `src.<layer>` | `vectordb.search ok` → `src.vectordb` |
| Loggers | a layer's spans log as `src.<layer>`, its other lines as `src.<layer>.<module>`: both under `src.<layer>`, so one level setting covers the layer | `src.retrieval`, `src.retrieval.retriever` |
| Log fields | `snake_case`, units in the name; a count is a plain noun, a list says what it holds, a setting keeps its setting's name | `duration_ms`, `chunks=28`, `found=[...]`, `top_k` |
| Error codes | `UPPER_SNAKE_CASE`, stable: clients may depend on them | `INVALID_REQUEST`, `UPSTREAM_RATE_LIMITED` |
| Routes | lower case; the API versioned under `/api/v1`, health checks under `/health` | `/api/v1/query`, `/health/ready` |
| Tests | `test_<layer>.py`; each test's name is a sentence saying what it checks | `test_a_bad_question_gets_a_422_and_costs_nothing` |

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**, made in the Google Cloud console, under APIs & Services > Credentials. There, under API
  restrictions, restrict it to the Gemini API (the Generative Language API; not Gemini for Google Cloud API, a
  different service), so a leaked key can't be used for anything else. Every call to Gemini uses your key's quota
- **A web browser**

---

## 🚀 Quick Start

### Step 1: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Intermediate/01-rag-chat-app"   # from the repo root; quotes for the spaces
```

### Step 2: Create and Activate a Virtual Environment

```bash
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
```

Creating the venv is once only; activate it again in every new terminal.

### Step 3: Install Dependencies

```bash
pip install -r requirements-dev.txt  # once: the packages and pytest, into .venv/
```

### Step 4: Add Your Gemini Key

```bash
cp .env.example .env                 # once (Windows PowerShell or Command Prompt: copy .env.example .env)
```

Open `.env` in an editor and put your key after `GOOGLE_API_KEY=`. `.env` is in `.gitignore`, so your key never goes
into git.

### Step 5: Start the Server

```bash
python main.py                       # the server; Ctrl+C stops it
```

It checks `config.yaml` and the key, builds the engine (the console says `pipeline.build ok`, then `Engine ready`),
then starts the server. When it prints `Uvicorn running on http://127.0.0.1:8000`, it's ready.

### Step 6: Open the Page

Open http://127.0.0.1:8000. The question box already holds the first sample question: click **Ask**. The answer
shows up under the box, with up to 3 articles the search found, then its trace ID and how long it took, then
the boxes that show what the server did to answer it (see On the Page: Each Request's Boxes). Any [1], [2] in an
answer number the 5 chunks in the prompt, not the articles under **Found by the search**.

In GitHub Codespaces, `127.0.0.1` is your own computer, not the codespace: open the **Ports** tab next to
**Terminal** and click the globe icon on port 8000.

### Or: Ask in the Terminal

```bash
python main.py ask                           # the three sample questions in config.yaml
python main.py ask "printer not found"       # your own question
```

Each answer is printed with its sources and its trace ID; the log goes to the console (stderr) only:
`logs/app.log` is the server's, so `ask` can run while the server does. Each question is bounded by each call's
timeout and attempts; the 60-second deadline is the API's.

### Or: Embed the Chunks Once

```bash
python main.py index                         # embeds the 28 chunks and saves their vectors in data/vectors.json
```

Every start embeds the 28 chunks again, since the index lives in the app's memory and goes when it stops. After
`index`, a start loads the saved vectors instead: no call to Gemini, and the build's boxes on the page say
`0 model calls`. Each chunk's vector is found by a hash of the chunk's text, and the file is used only when every
chunk the start makes has one, from the same model at the same size. Edit an article, change the chunking or the
model, and the start embeds the chunks again, with a warning saying why; run `index` again to save the new ones.
The file is under 0.5 MB, and it isn't in git: it's made from the data.

### Or: Run It in One Command, in GitHub Codespaces Too

From the repo root (where a codespace's terminal opens), this one command does Steps 2 to 5 for you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Intermediate/01-rag-chat-app         # the server
python "projects/RAG/IT Knowledge Base/run.py" Intermediate/01-rag-chat-app ask    # options go to main.py
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, and copies `.env.example`
to `.env` if there's no `.env` yet; then it runs `main.py` in this folder with the venv's Python, so there's nothing
to activate. A new `.env` holds only the placeholder, so when `GOOGLE_API_KEY` isn't in the environment either, the
first run stops there and says where your key goes (it never prints a key):

```text
ERROR Open <this folder>/.env, put your key after GOOGLE_API_KEY=, save it, then run this command again. (In GitHub Codespaces, a Codespaces secret named GOOGLE_API_KEY works too: then .env isn't needed.)
```

In GitHub Codespaces, step by step:

1. On the repo's GitHub page, click **Code**, then **Codespaces**, then **Create codespace on main**. Its terminal
   opens at the repo root.
2. Give it your key, one of two ways:
   - **A Codespaces secret**, so the key is in no file: on GitHub, **Settings** > **Codespaces** > **Secrets** >
     **New secret**, named `GOOGLE_API_KEY`, with access to this repository. A codespace gets it when it starts, so
     start a new one, or stop and restart the one you have.
   - **Or `.env`**: run the command once (it makes `.env` and stops), open the file with
     `code "projects/RAG/IT Knowledge Base/Intermediate/01-rag-chat-app/.env"`, put your key after `GOOGLE_API_KEY=`,
     and save it.
3. Run the command. The first time takes about a minute, for the install. When it prints
   `Uvicorn running on http://127.0.0.1:8000`, open the **Ports** tab next to **Terminal** and click the globe icon
   on port 8000: the chat page opens in a new browser tab.
4. Ctrl+C stops the server.

### Or: Deploy It to Vercel

Vercel doesn't run `python main.py`: it imports `main.py` and serves its `app`. Importing builds nothing; when Vercel
starts the app, the app's start-up (FastAPI's lifespan) runs the same steps `python main.py` does: the settings, the
key, logging, then the build. Before that, once per deployment, Vercel's build runs `python main.py index`, as
`vercel.json` says, so the chunks are embedded there and not at each start.

1. On Vercel, click **Add New...**, then **Project**, and import your copy of this repo from GitHub.
2. Set **Root Directory** to `projects/RAG/IT Knowledge Base/Intermediate/01-rag-chat-app`. Vercel finds `main.py`
   and `vercel.json` there, installs `requirements.txt`, then runs `python main.py index`.
3. Under **Environment Variables**, add `GOOGLE_API_KEY`, with your key. The build uses it to embed the chunks, and
   the app to answer. It's all the deployment needs: `config.yaml` and the data file go with the code.
4. Click **Deploy**. When it's done, open the address it gives you: the chat page.

What's different there:

- **The log goes to the console only.** Vercel sets `VERCEL=1`, and then the app writes no `logs/app.log` (a
  deployment's files are read-only). Vercel keeps the console's lines: open the deployment's **Logs**.
- **Vercel runs the app as instances: copies it starts and stops.** It starts one when a request comes and none is
  free (after a quiet spell, say), and more when requests come at once: a page load sends several. Each copy has its
  own memory, so each builds its own index at start. On their own, 4 copies starting together embed 4 × 28 = 112
  chunks within seconds, over the free tier's 100 a minute, and 36 starts use up its 1,000 a day.
- **So the build embeds the chunks once.** `python main.py index`, in the build, saves their vectors in
  `data/vectors.json`, which goes into the deployment; each copy loads them at start, with no call to Gemini. In the
  build's log, `embeddings.save_vectors ok`; in the deployment's, at each start, `embeddings.load_vectors ok` with
  `used=True`; a start that finds no file logs a warning (see Troubleshooting). Should the build fail (no key, or
  Gemini refuses), the deployment stops there, and Vercel goes on serving the one before.
- **A push that changes nothing here builds nothing.** Vercel builds a project at every push to its repo, even one
  that only changes another project in it, and each build here embeds the 28 chunks. So `vercel.json`'s
  `ignoreCommand` compares this folder at the pushed commit with the commit of the last deployment that succeeded
  (`git diff`), and when nothing in it changed, skips the build: the deployment shows as Canceled, and the one before
  goes on serving. Redeploying the deployment that's serving always builds, so a changed key reaches it.
- **Traces live in one instance's memory.** The page reads each request's trace right after its answer; should that
  read reach another instance, the page says `The trace isn't available: ...` instead of the boxes.
- **Unless you protect it, the address is public**: anyone who has it can ask questions on your key, and read a
  trace by its ID. Turn on Vercel's Deployment Protection, or delete the deployment when you're done.

To try it on your machine the way Vercel runs it, start it in this folder, with the venv active, with
`uvicorn main:app --no-access-log`, and open http://127.0.0.1:8000.

---

## 🔧 Configuration

### `config.yaml`

Every setting the app runs with, except the key. Each section is named like the package that uses it (`logging`
and `tracing` are read by `src/observability`):

| Section | Settings | What they set |
|---|---|---|
| `app` | `name`, `sample_questions` | the page's title in `/docs`; the page's buttons, and what `python main.py ask` answers |
| `ingestion` | `path`, `encoding`, `text_columns`, `metadata_columns`, `required_columns` | the data file, which columns are searched and which are shown, and which a row can't be without |
| `chunking` | `chunk_size`, `chunk_overlap` | 512 and 50 characters |
| `embeddings` | `provider`, `model`, `dimensions`, `batch_size`, `timeout_seconds`, `max_attempts`, `vector_file` | Gemini's `gemini-embedding-001` at 768 numbers; 100 texts per call; 30 s per attempt, 3 attempts; `data/vectors.json`, where `index` saves the vectors (`null`: every start embeds) |
| `vectordb` | `provider`, `location`, `collection` | Qdrant, `:memory:` (inside the app), `it_knowledge_base` |
| `retrieval` | `top_k` | 5 chunks per question |
| `llm` | `provider`, `model`, `max_output_tokens`, `timeout_seconds`, `max_attempts` | `gemini-3.5-flash-lite`; answers of at most 500 tokens; 30 s per attempt, 3 attempts |
| `pipeline` | `max_sources`, `snippet_length` | up to 3 sources per answer, 200 characters of each |
| `api` | `host`, `port`, `request_timeout_seconds` | 127.0.0.1:8000; a 504 after 60 s |
| `logging` | `level`, `console_format`, `file`, `max_bytes`, `backup_count` | `INFO`; `text` on the console; `logs/app.log`, a new file every 5 MB, 5 kept |
| `tracing` | `enabled`, `max_traces` | each API request's trace kept in memory, for the page: on; the newest 200 kept |

Paths are found from the folder `config.yaml` is in. A key that isn't known (`chunk_szie`), a missing value or one
out of range stops the start, and the message names every bad setting at once. A retry happens only for a timeout,
a connection error, a 429, or a 500, 502, 503 or 504; `max_attempts: 1` turns retries off.

### Command-Line Options

| Option | Default | What it does |
|---|---|---|
| `serve` | the default command | builds the engine, then serves the page and the API |
| `ask [QUESTION]` | | builds the engine, then answers your question, or the sample questions |
| `index` | | embeds the chunks and saves their vectors in `embeddings.vector_file`, for each start to load (Vercel's build runs it) |
| `--config FILE` | `config.yaml`, next to `main.py` | another settings file, e.g. one per environment |
| `--log-level LEVEL` | `logging.level` | `DEBUG`, `INFO`, `WARNING` or `ERROR` for this run |

The options come before the command: `python main.py --log-level DEBUG ask "vpn"`. `python main.py --help` lists
them.

### The API Key

`GOOGLE_API_KEY`, from the environment or `.env`; one set in the environment wins. On Vercel, it's one of the
project's Environment Variables. It's held as a secret value,
which prints as `**********`, and the log masks it should a library ever put it in a message.

---

## 🔍 Logging and Tracing

### Where the Log Goes

| Where | Format | For |
|---|---|---|
| The console (stderr) | one readable line: `time level [trace ID] logger: message  key=value ...` | watching it run |
| `logs/app.log` | one JSON object per line, the same facts as fields | searching, and log collectors |

Answers printed by `python main.py ask` go to stdout, and its log to stderr, never to the file. On Vercel, the
server's log goes to the console only, which Vercel keeps (see Or: Deploy It to Vercel). At `INFO`, each question
writes one line per stage and one when the request ends. `DEBUG` adds the question's text, the answer's text and each chunk found
with its title: useful while developing, not in production, where a question can hold someone's personal details.

### Find Everything About One Request

Copy the trace ID from the page (under the answer, or after an error message), the `X-Trace-ID` header, or the
terminal, then:

```bash
grep 67464f61fb33c2bd logs/app.log                    # macOS, Linux, Codespaces, Git Bash
Select-String 67464f61fb33c2bd logs\app.log           # Windows PowerShell
```

Every line of that request comes back, from every layer. The console shows them like this (the times, durations,
scores and token counts are Gemini's, so yours will differ):

```text
2026-10-29T16:02:55.412Z INFO    [67464f61fb33c2bd] src.embeddings: embeddings.embed_query ok  duration_ms=<ms> model=gemini-embedding-001
2026-10-29T16:02:55.413Z INFO    [67464f61fb33c2bd] src.vectordb: vectordb.search ok  duration_ms=<ms> collection=it_knowledge_base top_k=5 hits=5 top_score=<score>
2026-10-29T16:02:55.414Z INFO    [67464f61fb33c2bd] src.retrieval: retrieval.retrieve ok  duration_ms=<ms> top_k=5 found=[<5 chunks, as "doc_id#chunk_index">] scores=[<their scores, highest first>]
2026-10-29T16:02:55.415Z INFO    [67464f61fb33c2bd] src.prompts: prompts.build ok  duration_ms=<ms> prompt_version=answer-v1 chunks=5 prompt_chars=<n>
2026-10-29T16:02:55.432Z INFO    [67464f61fb33c2bd] src.llm: llm.generate ok  duration_ms=<ms> model=gemini-3.5-flash-lite finish_reason=STOP input_tokens=<n> output_tokens=<n>
2026-10-29T16:02:55.432Z INFO    [67464f61fb33c2bd] src.pipeline: pipeline.query ok  duration_ms=<ms> question_chars=37 sources=3 answer_chars=<n> prompt_version=answer-v1
2026-10-29T16:02:55.433Z INFO    [67464f61fb33c2bd] src.api.middleware: Request finished  method=POST path=/api/v1/query status_code=200 duration_ms=<ms>
```

And in `logs/app.log`, the same `llm.generate` line as JSON:

```text
{"time": "2026-10-29T16:02:55.432Z", "level": "INFO", "trace_id": "67464f61fb33c2bd", "logger": "src.llm", "message": "llm.generate ok", "span": "llm.generate", "status": "ok", "duration_ms": <ms>, "model": "gemini-3.5-flash-lite", "finish_reason": "STOP", "input_tokens": <n>, "output_tokens": <n>}
```

What each line tells you:

| Line | Tells you |
|---|---|
| `embeddings.embed_query` | how long Gemini took to embed the question |
| `vectordb.search` | how many chunks came back, and the best score |
| `prompts.build` | the prompt filled in: how many chunks went into it, and how long it is |
| `retrieval.retrieve` | which chunks the model was given (`3#1` = article 3, its second chunk) and how close each was |
| `llm.generate` | how long Gemini took to answer, the tokens it read and wrote (the cost), and why it stopped (`STOP`; `MAX_TOKENS` means the answer was cut off, and logs a warning) |
| `pipeline.query` | the whole question, and the prompt's version: when an answer changes, whether the prompt did |
| `Request finished` | what the caller got, and how long it waited |

A stage that fails writes `<stage> failed` with its `error_type`, and one stopped by the deadline writes
`<stage> cancelled`; then one `Request failed` line gives the error's code and full detail. The build at start-up
has a trace ID of its own, so its lines (`pipeline.create`, the engine's parts made; `ingestion.load`,
`chunking.split`, `embeddings.load_vectors`, then `embeddings.embed_documents` unless the saved vectors were used,
`vectordb.recreate`, `vectordb.upsert`, `pipeline.build`) group together too, and so do `python main.py index`'s.
Lines written outside any trace, such as uvicorn's `Uvicorn running on ...`, show `[-]`.

---

### On the Page: Each Request's Boxes

Every request the page sends to the API gets a trace, and with `tracing.enabled` on, the server keeps its log lines in
memory, in a trace store. Right after an answer (or a failure) arrives, the page reads that request's trace from
`GET /api/v1/traces/{trace_id}` and lays the request out as a row of numbered boxes, two side by side (one under the
other on a screen narrower than 960 px). Its head says what you asked, how it went (`✓ answered · 200` or
`✕ failed · 503`), how long it took, its trace ID, and how many steps, model calls and log lines it had:

| Box | What it shows |
|---|---|
| 1 · The answer | what the model wrote, and the articles the search found, each with its score. For a failure, **What went wrong**: the server's message, its code, whether trying again may work, then which step failed, after how long, and the server log's reason |
| 2 · Pipeline | each step, numbered in the order it ran: receive the request, turn the question into a vector, search the vector store, fill in the prompt, ask the chat model, send the response. Each has its time, its share of the whole request as a bar, and a line on what it did (the model, the chunks back, the tokens) |
| 3 · Time per step | every stage on one time scale, from 0 to the whole request: when it started and how long it took, a stage's own steps indented under it, the slowest one marked, and a line saying where most of the time went |
| 4 · Calls | how many calls the request made, of each kind: model calls (by model), HTTP requests (by status, and to which host), vector store calls, tokens, retries, tool calls (none: the model is given no tools, only the prompt) and failed steps. Each dot is one call; a red one failed |
| 5 · Logs | every line the server wrote for the request, numbered, in the order it wrote them, each with how many ms into the request it came and, in a circle, the pipeline step it belongs to |
| 6 · What the model was given | the chunks the search found (rank, article, place in the article: `3#1` is article 3, its second chunk, and score), then the prompt: the system message (the rules, then the chunks, numbered) and the human message (the question), exactly as sent |

The colours say what kind of work a step is, and a label beside each says it too: purple, a call to a model; teal,
a call to the vector store; gray, the app's own work. Red with ✕ is a step that failed, amber with ■ one that a
deadline or Ctrl+C stopped. Below the sample questions, **How the knowledge base was built** shows boxes 2 to 5 for
the build at start-up: making the engine's parts, reading the file, cutting the chunks, reading the saved vectors
(gray: the app reads a file, and calls no model) and, when they can't be used, embedding the chunks (one call to
Gemini), then storing them. Only the newest request stays open; click a request's head to open or close it.

The trace store keeps the app's own lines from `DEBUG` up whatever `logging.level` is (the question, the chunks found,
the prompt and the answer are `DEBUG` lines), and the libraries' from `INFO` up (httpx's line for each HTTP call,
Google's retries), so the boxes tell the whole story while the console and the file stay at their level. It keeps
the newest `tracing.max_traces` API requests (200), each up to 300 lines, and the build's for good; the page's own
files, the health checks and reading a trace aren't kept. The key is masked there too, and an error's traceback stays
in the log file: the trace has its type and message only.

Anyone who has a trace ID can read that trace, and a trace holds the question, the prompt, the answer and any error's
detail. That's what makes it useful while you learn and debug, and why `tracing.enabled` should be `false` (or the API
behind a login) before the app is shared with other people. With it off, the page shows only each answer's box, and
`GET /api/v1/traces/{trace_id}` answers 404.

You can read a trace yourself, too:

```bash
curl http://127.0.0.1:8000/api/v1/traces/67464f61fb33c2bd     # {"trace_id": "...", "events": [...], "dropped": 0}
```

Each event has `at_ms` (when it happened, in ms from the start of the request; for a stage, when it started),
`logged_ms` (when its line was written), `depth` (how many stages it sits inside), `level`, `logger`, `message`, and
for a stage `span`, `status` (`ok`, `failed` or `cancelled`) and `duration_ms`; then `fields`, what the line recorded,
and `error`, an error's type and message. The full shape is at http://127.0.0.1:8000/docs.

---

## 🚨 Errors

Every error the API answers with has one shape, whatever went wrong:

```json
{"error": {"code": "UPSTREAM_RATE_LIMITED", "message": "The AI service is busy (rate limited). Try again in a minute.",
           "trace_id": "4f1c2a9b8e7d6c5b", "retryable": true}}
```

`message` is safe to show to a user; `retryable` says whether sending the same request again later may work; a 422
adds `details`, one entry per bad field. What went wrong inside (the provider's own error, a traceback) never goes in
the error itself: it goes to the log under the trace ID. While `tracing.enabled` is on, the request's trace shows it
too (its type and message; never a traceback), since showing what happened is the trace's job: turn tracing off
before the app is shared.

| Code | HTTP | When | Retryable | Logged as |
|---|---|---|---|---|
| `INVALID_REQUEST` | 422 | the question is empty, over 500 characters, missing, or the body has another field or isn't JSON | no | `INFO`, which fields |
| `BAD_REQUEST` | 400 | the body can't be read at all: it isn't UTF-8 text | no | the request's line only |
| `NOT_FOUND`, `METHOD_NOT_ALLOWED` | 404, 405 | no such address, or the wrong method for it | no | the request's line only |
| `TRACE_NOT_FOUND` | 404 | no trace is kept with that ID: too old, never an API request, or `tracing.enabled` is off | no | `INFO` |
| `NOT_READY` | 503 | the engine isn't built, or the store lost chunks | yes | `WARNING` |
| `VECTOR_STORE_ERROR` | 503 | Qdrant failed | no | `ERROR`, with the traceback |
| `UPSTREAM_RATE_LIMITED` | 503 | Gemini said 429, after every attempt | yes | `WARNING` |
| `UPSTREAM_TIMEOUT` | 504 | a call to Gemini timed out, after every attempt | yes | `WARNING` |
| `UPSTREAM_ERROR` | 502 | Gemini refused the call (a bad key, say) or failed (5xx), or answered with no text | 5xx: yes; else no | `WARNING`, or `ERROR` with the traceback |
| `REQUEST_TIMEOUT` | 504 | the whole question took over `api.request_timeout_seconds` | yes | `WARNING` |
| `INTERNAL_ERROR` | 500 | anything else: a bug | no | `ERROR`, with the traceback |

At start-up, there's no API yet: a bad `config.yaml`, key or log file is printed as one line starting
`Can't start:`, and a failed build is logged as one line starting `Start-up failed:`, with its code; either way the
exit code is 1. `python main.py index` does the same, its failure logged as `Indexing failed:` (`VECTOR_FILE_ERROR`
when the file can't be written). The page's own files (`/`, `/static/...`) are files, not API answers: an error
there, such as a malformed `Range` header, is Starlette's own plain-text 400 or 416.

---

## 🔁 Replacing a Part

`src/pipeline/factory.py` is the one place the classes are chosen, and each provider is used through an
interface, so a part can be replaced without touching the others:

| To replace | Change | The rest sees |
|---|---|---|
| The embedding model (OpenAI, say) | add a builder to `BUILDERS` in `embeddings/embedder.py`, and its name to `EmbeddingsSettings.provider` in `config/settings.py`; set `embeddings.provider`, `model` and `dimensions` | LangChain's `Embeddings` |
| The chat model | add a builder to `BUILDERS` in `llm/llm_client.py`, and its name to `LLMSettings.provider`; set `llm.provider` and `model` | LangChain's `BaseChatModel` |
| The vector store (Chroma, pgvector, ...) | subclass `BaseVectorStore` (4 methods), add a builder to `BUILDERS` in `vectordb/vector_store.py`, and its name and its own settings (a URL, say, in place of `location: ":memory:"`) to `VectorDBSettings` | `BaseVectorStore` |
| The data source (a database, a wiki) | a LangChain `BaseLoader` whose Documents carry `doc_id`, `source` and `title`; use it in `factory.py` | LangChain's `BaseLoader` |
| The chunking | the splitter in `chunking/chunker.py` | `Chunker.split()` |
| The prompt | `prompts/prompt_templates.py`, and a new `PROMPT_VERSION` | `ANSWER_PROMPT` |
| The page | the files in `static/`: it uses `/api/v1/info`, `/api/v1/query` and `/api/v1/traces/{trace_id}` | the API |
| The log's format or destination | `observability/logging_setup.py` | Python's `logging` |

Each `provider` setting is a fixed list of names in `config/settings.py`, so a name that isn't there is refused at
start-up: a new provider needs its name there and its builder in `BUILDERS`.

`RAGEngine` uses the loader and the store through their interfaces, so any `BaseLoader` or `BaseVectorStore` works.
Its other parts are the app's own thin classes (`Chunker`, `Embedder`, `KBRetriever`, `LLMClient`), which add the
spans, checks and errors around what they wrap; replace what they wrap, not them. Two more things are contracts:
a source's score comes from `KBRetriever` (it puts `score` in each chunk's metadata), and the page reads the spans'
names and fields (`STAGE_NAMES` and `stageDetail()` in `static/app.js`). A span the page doesn't know still shows,
with its raw name and fields.

---

## 🧪 Testing

```bash
python -m pytest -m "not live"       # 183 passed, 2 deselected  (add -v for one line per test)
```

The plain tests need no key and make no calls: they use stand-ins for Gemini, and Google's own client faked at the
two methods LangChain calls, so the real Gemini classes run end to end without a network; httpx, which Google's
client sends with, is stopped from sending anything. They check each layer on its own (`test_<layer>.py`), then:

- **The trace**: one question's lines, stage by stage, every one with its trace ID, a worker thread's included; the
  trace ID printed by `ask` finds the question's lines in the log file
- **The log**: the console's text line and the file's JSON line, the key masked in both, tracebacks kept, the
  question's text only at `DEBUG`
- **The traces**: a question's trace holds every stage and line in timeline order, each at its depth, with the
  chunks found, the prompt and the tokens; a failed question's shows where it failed and why; the build's is kept for
  good and named by `/api/v1/info`; the page's files, the health checks and trace reads aren't kept; the store keeps
  the newest traces, at most 300 lines each, with the key masked and no tracebacks; and the request's line is written
  before its last bytes go out, so a trace read right after the answer holds it
- **The errors**: each provider failure (429, timeout, 5xx, a bad key) becomes the right error, for embeddings and
  for the chat model; each API failure answers in the one shape, with its status, code and trace ID, logged at the
  right level; a slow model is cancelled at the deadline
- **The start**: a bad setting (an encoding Python doesn't know among them), a missing key, a log file that can't
  be opened and a failed build each stop it with one line and exit code 1, never a traceback; Ctrl+C during a
  question returns 130, and a span it stops says `cancelled`; `ask` logs to the console only; the server runs with
  the app's logging
- **The app a host serves**: `main.py` has the top-level `app` Vercel looks for, and importing it builds nothing;
  starting it builds the engine, as `python main.py` does; without a key, the host's start fails with the one line;
  on Vercel, the log goes to the console only
- **The saved vectors**: `index` embeds the chunks once and saves their vectors, and the next start loads them with
  no call to the model and gives the same answers; they load back exact, each found by its text in any order (rows
  reordered or an article removed: still used), but only when every chunk has one from the same model and size (an
  edited or added text, another model or size: a warning says why, and the chunks are embedded); a missing file
  isn't a warning, except on Vercel, a broken one is; the file is written whole or not at all; a failed `index`
  exits 1 (Ctrl+C: 130), so Vercel's build stops; `vercel.json`'s build command runs `index`, and its ignore
  command skips a push that changed nothing here. Each test's vector file is in its own temporary folder, never
  `data/vectors.json`

The 2 deselected tests are live tests, marked `live`: they build the real engine and ask the real Gemini, once
through the engine and once through the API, so they need your key in `.env`; with no key, `tests/conftest.py`
skips them. Together they embed 30 texts (they never use saved vectors), within the free tier's 100 a minute:
`python -m pytest -m live`.

The linter checks the code against `ruff.toml`'s rules, PEP 8 naming among them; it isn't needed to run the app or the
tests:

```bash
pip install ruff
ruff check .                         # All checks passed!
```

---

## 🎓 Key Concepts Demonstrated

### 1. One Way In, One Place for the Parts

```python
settings = load_settings(config)                 # main.py, start_up(): checked before anything runs
engine = create_engine(settings, api_key)        # factory.py: the parts config.yaml names; nothing runs yet
engine.build()                                   # the work: read, chunk, embed (or load the saved vectors), store
```

`main.py` is the only file that runs anything; every other file only defines things. `factory.py` is the only file
that knows which classes are used: `RAGEngine` gets its parts passed in, rather than making them. Tests pass in
stand-ins the same way. A host such as Vercel imports `main.py` instead of running it: its `app` runs the same
start-up, `start_up()`, when the host starts it.

### 2. A Trace ID That Follows the Work

```python
_current: ContextVar[Trace | None] = ContextVar("trace", default=None)    # tracing.py: the ID, when it began
with trace_context() as trace_id:                                         # middleware.py: one per request
    ...                                                                   # every log line in here carries trace_id
```

A context variable belongs to the work being done, not to a module or a thread: each request, running at the same
time as others, sees its own. It goes with the work into async tasks and into `asyncio.to_thread()`, where the
search runs. A logging filter stamps its ID on every line, so no function has to pass it along.

### 3. A Span per Stage

```python
with span("llm.generate", model=self.model_name) as fields:          # llm_client.py
    message = await self.model.ainvoke(messages)
    fields.update(input_tokens=..., output_tokens=...)               # recorded on the span's line
```

Each stage writes one line when it ends: `ok`, `failed` or `cancelled`, how long it took, and what it recorded. Read
in order, a trace's spans say where the time went and where it failed.

### 4. Errors as Types, Answered in One Shape

```python
except Exception as err:
    raise upstream_error("llm", err) from err    # Google's 429 → UpstreamRateLimitError (503, retryable)
```

Each layer turns the failures it knows into the app's own errors, keeping the original as the cause. The API turns
each into the same JSON, with a code clients can rely on; a 4xx or 5xx from Gemini, an httpx timeout or a LangChain
error all end up as one of three upstream errors, whichever provider raised them.

### 5. Settings Checked Before Anything Runs

```python
class ChunkingSettings(Section):                 # Section: extra="forbid", frozen=True
    chunk_size: int = Field(gt=0)
    chunk_overlap: int = Field(ge=0)             # and less than chunk_size: checked too
```

Every value has a type and a range, and an unknown key is an error, so a typo can't be silently ignored. A bad
value stops the start with its name, before anything is read or called, rather than failing mid-request.

### 6. A Trace You Can Read Back

```python
class TraceStore(logging.Handler):               # trace_store.py: one more place log lines go
    def emit(self, record):
        trace = current_trace()                  # the request this line was written for
        ...                                      # filed under trace.trace_id, as an event on its timeline
```

The trace store is a logging handler, like the console and the file, so it gets every line from every module and
library without any of them knowing it's there. It files each line under its request's trace, which the page then
reads back by ID. Logging stays the one way the app reports what it does; the page is one more place to read it.

### 7. Deadlines on Everything Outside

Each call to Gemini is cut off after `timeout_seconds` and tried again, with a growing wait, up to `max_attempts`
times, but only for a timeout, a 429 or a 5xx: a bad key fails at once. Above that, each question has
`api.request_timeout_seconds` in all, so one slow call can't keep a request, or the page, waiting forever. The page
learns that deadline from `/api/v1/info`, and waits 30 seconds more, so the server's 504 comes first.

### 8. Embed Once, Start Many Times

```python
saved = self.vector_file.load(texts) if self.vector_file else None              # rag_engine.py, build()
vectors = saved if saved is not None else self.embedder.embed_documents(texts)
```

Qdrant here lives in the app's memory, and memory belongs to one process: a copy of the app that starts can't see
the index another copy built, and neither keeps it once it stops. One server that runs for hours embeds once; a host
that starts copies on demand, like Vercel, would embed once per copy. So the work that's the same for every copy,
turning the chunks into vectors, is done once, before any copy starts (`index`, in Vercel's build, which runs only
when something in this folder changed), and each copy loads the result. The saved vectors stand in for embedding
only when they're exactly what embedding would give: the file names the model and size they were made with, and the
hash of each chunk's text, so an edited article or a new model can't quietly be answered from old vectors. The same
idea, at a larger scale, is a vector database outside the app, which every copy shares.

---

## 🛠️ Troubleshooting

**Issue**: `.venv\Scripts\Activate.ps1 cannot be loaded because running scripts is disabled on this system.`
**Fix**: Windows PowerShell blocks scripts until you allow them. Allow local ones once, with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or for this window only, with
`Set-ExecutionPolicy -Scope Process Bypass`, then activate again (Step 2). The one command needs no activating.

**Issue**: `ERROR Open <this folder>/.env, put your key after GOOGLE_API_KEY=, save it, then run this command again. ...`
**Fix**: The one command made `.env` from `.env.example`, which holds only a placeholder. Put your key in it and run
the command again, or set a Codespaces secret named `GOOGLE_API_KEY` (see Or: Run It in One Command, in GitHub
Codespaces Too).

**Issue**: `Can't start: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret; on Vercel: one of the project's Environment Variables).`
**Fix**: Put your key in `.env` (Step 4), and start it again.

**Issue**: On Vercel, every request fails, and the deployment's **Logs** show `Can't start: ...` or
`Start-up failed: ...`
**Fix**: The app's start-up failed there, so it can't answer; the line says why, as it would on your machine (see the
other issues here). Most often `GOOGLE_API_KEY` isn't set for the deployment: add it under the project's
**Settings** > **Environment Variables**, then redeploy. A variable reaches only the deployments made after it's
added.

**Issue**: On Vercel, the deployment fails at the build, whose log shows `Can't start: GOOGLE_API_KEY is not set...`
or `Indexing failed: ...`
**Fix**: The build runs `python main.py index`, which embeds the chunks, so it needs the key too: add
`GOOGLE_API_KEY` under **Settings** > **Environment Variables**, then redeploy. After `Indexing failed:
UPSTREAM_RATE_LIMITED`, read the rest of the line: wait a minute and redeploy, or, when it says `Embed content
requests per day limit exceeded on Free Tier`, redeploy after midnight Pacific time, when the day's quota comes back.
Until a build succeeds, Vercel goes on serving the deployment before it.

**Issue**: On Vercel, each start's log shows `WARNING [...] main: No saved vectors on Vercel (<the path>): each instance embeds the chunks as it starts, and instances starting together can use up Gemini's quota. vercel.json has the build save them with python main.py index`, then `embeddings.load_vectors ok ... used=False reason="there's no file: python main.py index makes it"` and `embeddings.embed_documents`
**Fix**: The deployment has no saved vectors, so each copy embeds the chunks, as before the build step. Check that
`vercel.json` is in the folder set as **Root Directory**, that the project's **Framework Preset** is FastAPI (the
build command runs for a Python preset), and that the build's log shows `Running "python main.py index"`.

**Issue**: `WARNING [...] src.embeddings.vector_file: The saved vectors aren't used: there's no saved vector for 18 of the 37 chunks (an article, the columns read or the chunking changed since they were saved). The chunks are embedded instead; python main.py index saves their vectors`
**Fix**: An article, the columns read or the chunking changed after `index` saved the vectors (another model or size
says so too). The start embedded the chunks instead, so the answers are right; it just cost a call. Run
`python main.py index` again to save the new vectors. On Vercel, the next deployment's build does it.

**Issue**: `Can't start: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Replace it with your key.

**Issue**: `Can't start: .env isn't saved as UTF-8 text. Open it in an editor and save it with UTF-8 encoding.`
**Fix**: `.env` was saved in another encoding, often UTF-16 by Windows PowerShell 5's `echo ... > .env`. Save it
again as UTF-8, or make it with `copy .env.example .env` and edit it.

**Issue**: `Can't start: Config file has 1 bad setting(s): retrieval.top_k: Input should be greater than or equal to 1 (...)`
**Fix**: The message names each bad setting in `config.yaml` and says what's wrong with it. Fix them all, then start
again. `Extra inputs are not permitted` means a key that isn't known: usually a typo.

**Issue**: `ERROR [...] main: Start-up failed: UPSTREAM_ERROR: embeddings: GoogleGenerativeAIError: Error embedding content (INVALID_ARGUMENT): 400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'API key not valid. Please pass a valid API key.', ...`
**Fix**: Gemini didn't accept the key in `.env`. Copy it again from the Google Cloud console, with nothing before or
after it.

**Issue**: An error with `403 PERMISSION_DENIED` in it
**Fix**: Google refused the key for this service. In the Google Cloud console, open the key: under API restrictions
it should list the Gemini API (the Generative Language API), not Gemini for Google Cloud API, and under
Application restrictions, None. New settings can take up to 5 minutes to work.

**Issue**: `ERROR [...] main: Start-up failed: UPSTREAM_RATE_LIMITED: embeddings: GoogleGenerativeAIError: Error embedding content (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. ...`, or the page shows `The AI service is busy (rate limited). Try again in a minute.`
**Fix**: Your key has used its quota. On the free tier, that's 100 embedded texts a minute and 1,000 a day; starting
the app embeds 28 (none when it loads the saved vectors: see Or: Embed the Chunks Once), and each question 1 more.
Wait a minute, then try again. When the line says `Embed content requests per day limit exceeded on Free Tier`, the
day's are used up: they come back at midnight Pacific time, and the line says how long that is (`retry in ...`).
The page says `Try again in a minute` either way.

**Issue**: `Can't start: the log file can't be opened (Permission denied): <the full path>`
**Fix**: `logging.file` in `config.yaml` leads to a folder, or to a place you can't write. Point it at a file in a
folder you can write to, or set it to `null` for no log file.

**Issue**: The console shows `--- Logging error ---` with `PermissionError: [WinError 32] The process cannot access the file because it is being used by another process`
**Fix**: Two servers write the same log file, and Windows can't rename a file another process has open, which is
how the log is rotated. Give each server its own `logging.file`, in a config file of its own (`--config`). (`ask`
never writes the file, so it can run beside the server.)

**Issue**: `ERROR [...] main: Start-up failed: INGESTION_ERROR: Knowledge base file not found: <the full path>`
**Fix**: `ingestion.path` in `config.yaml` doesn't lead to the file. A relative path is found from the folder
`config.yaml` is in. The same line names any other problem with the file: one that can't be opened, a missing
column, or each row that can't be read, with its row and line.

**Issue**: `ERROR [-] uvicorn.error: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000): only one usage of each socket address (protocol/network address/port) is normally permitted` (on macOS and Linux, it ends in `address already in use`)
**Fix**: Another server, often another project's, already has port 8000. Stop it (Ctrl+C in its terminal), or set
`api.port` to another port in `config.yaml`, and use that port in the address.

**Issue**: `ModuleNotFoundError: No module named 'langchain_core'` (or another of the packages)
**Fix**: The venv isn't active, or the packages aren't installed in it. Activate it (Step 2), then
`pip install -r requirements-dev.txt` (Step 3).

**Issue**: The page shows a message ending in `trace ID` and an ID
**Fix**: Find that ID in `logs/app.log` (see Find Everything About One Request): the `Request failed` line has the
error's full detail, and the lines before it show which stage failed.

**Issue**: The page shows `Couldn't reach the server: ...`
**Fix**: The server isn't running, or stopped. Check its terminal, and start it again (Step 5).

**Issue**: http://127.0.0.1:8000 doesn't open in Codespaces
**Fix**: `127.0.0.1` is your own computer. Open the **Ports** tab next to **Terminal** and click the globe icon on
port 8000.

---

## 💡 Ideas to Try

- Ask a question and read its boxes: which step took longest (box 3), and how many calls went to Gemini (box 4)?
  Then find, in box 6, the chunks the answer used.
- Ask "Is the VPN busy?" while Gemini is rate limiting your key, and read where box 2 turns red and why box 1 says it
  failed.
- Ask a question, copy the trace ID under its answer, and find its lines in `logs/app.log`.
- Read a trace with `curl http://127.0.0.1:8000/api/v1/traces/<trace ID>`, and compare its events with box 5.
- Click **Ask** with an empty box: the message under it ends in a trace ID too. Find its `Request refused` line.
- Start it with `python main.py --log-level DEBUG`, ask a question, and read the question, the answer and each chunk
  found, with its title, in the log.
- Set `logging.console_format: json` in `config.yaml` and watch the console.
- Set `api.request_timeout_seconds: 0.5` and ask: the page says the question took too long, and **Behind the
  scenes** shows which stage was `cancelled`.
- Set `tracing.enabled: false`, start it again, and ask: only the answer's box, and the console and the file log as
  before.
- Put a typo in `config.yaml`, such as `chunk_szie: 400`, and start it.
- Run `python main.py index`, start it, and open **How the knowledge base was built**: the vectors are read from the
  file, and its head says `0 model calls`. Then set `chunk_size: 400`, start it again, and read the warning saying why
  the saved vectors weren't used.
- Open http://127.0.0.1:8000/docs to try the API, and read each route's error shapes there.
