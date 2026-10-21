# 09 · API

The RAG engine behind a web server, so any program can ask the IT knowledge base questions over HTTP. The engine is
built once, when the server starts; each request then answers one question, with up to 3 sources. Built with
**FastAPI**, **LangChain**, **Gemini** (`gemini-embedding-001` and `gemini-3.5-flash-lite`) and **Qdrant**, running in
memory.

> **Needs:** Python 3.11 or newer, and a Gemini API key. Starting the server makes 1 call to Gemini; each question
> makes 2.

---

## 🎯 What This Project Does

- **Builds the engine once**, when the server starts: the 10 articles, cut into 28 chunks, embedded and stored
- **`POST /api/query`** with `{"question": "..."}`: the answer and up to 3 sources
- **`GET /api/stats`**: what the engine holds and how it's set up
- **`GET /api/health`**: `{"status":"ok"}`, a quick check that the server is up
- **Checks each question before it costs anything**: an empty or blank question, or one over 500 characters, gets a
  422 error without calling Gemini
- **Hides Gemini's errors from the caller**: if Gemini doesn't answer, the caller gets a 502 error and the reason goes
  to the server's terminal

**Try it:** start the server, open http://127.0.0.1:8000/docs, and ask a question from the page FastAPI makes.

---

## 🏗️ Architecture

```text
a program, curl, or the /docs page
          │ POST /api/query {"question": "..."}
          ↓
┌───────────────────────────────────┐
│  FastAPI app (main.py)            │
│  ├─ QueryIn                       │  ← checks the question: 1 to 500 characters, else 422
│  ├─ query()                       │  ← await engine.aquery(question)
│  └─ QueryOut                      │  ← shapes the answer: {"answer", "sources"}
└────────────────┬──────────────────┘
                 ↓
┌───────────────────────────────────┐
│  RAGEngine, built at start-up     │  ← the 5 closest chunks, then Gemini's answer (2 calls)
└────────────────┬──────────────────┘
                 ↓
   {"answer": "...", "sources": [{"title", "system", "category", "snippet"}, ...]}
```

### The Pipeline in This Project

1. **Start** → `uvicorn main:app` imports `main.py`, which makes `RAGEngine()`: settings only
2. **Build** → before the first request, `lifespan()` runs `engine.build()` once: one call to Gemini for the chunks
3. **Check** → each request's JSON is checked against `QueryIn`; a bad question gets a 422 and no call
4. **Answer** → `query()` runs `engine.aquery(question)`: the question's embedding and the answer, 2 calls
5. **Reply** → the answer goes back shaped as `QueryOut`; if Gemini fails, a 502 goes back instead

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**: every call to Gemini uses your key's quota
- **curl**, to call the API from a terminal (optional: the `/docs` page does the same in a browser)

---

## 🚀 Quick Start

### Step 1: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Basic/09-api"   # from the repo root; quotes for the spaces
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

Open `.env` in an editor and put your key after `GOOGLE_API_KEY=`. You make a key in the Google Cloud console, under
APIs & Services > Credentials, as `.env.example` says. `.env` is in `.gitignore`, so your key never goes into git.

### Step 5: Start the Server

```bash
uvicorn main:app --reload            # the server; Ctrl+C stops it
```

It prints these lines, then waits for requests (the numbers in `[ ]` change each time):

```text
INFO:     Will watch for changes in these directories: ['...09-api']
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [16924] using StatReload
INFO:     Started server process [19312]
INFO:     Waiting for application startup.
INFO:     RAG engine built: 10 articles, 28 chunks
INFO:     Application startup complete.
```

`RAG engine built` means the chunks are embedded and stored: the server is ready.

### Step 6: Ask It a Question

**In the browser:** open http://127.0.0.1:8000/docs, FastAPI's page for trying each route. Click a route, then
**Try it out**, then **Execute**.

**Or with curl**, in a second terminal (the server keeps the first one busy). These are for bash: macOS, Linux,
Codespaces and Git Bash.

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/stats
curl -X POST http://127.0.0.1:8000/api/query -H "Content-Type: application/json" -d '{"question": "How do I fix VPN connection timeouts?"}'
```

Their answers, one per line. The parts in `< >` come from Gemini:

```text
{"status":"ok"}
{"documents":10,"chunks":28,"collection":"it_knowledge_base","chunk_size":512,"chunk_overlap":50,"top_k":5,"embedding_model":"gemini-embedding-001","chat_model":"gemini-3.5-flash-lite"}
{"answer":"<Gemini's answer>","sources":[{"title":"<article title>","system":"<system>","category":"<category>","snippet":"<the start of the chunk's text>"},...]}
```

In GitHub Codespaces, the curl commands work as they are, in the codespace's terminal. In the browser, `127.0.0.1` is
your own computer, not the codespace: open the **Ports** tab next to **Terminal**, click the globe icon on port 8000,
and add `/docs` to the address it opens.

### Or: Run It in One Command

With your key in `.env` (Step 4), this one command does Steps 2, 3 and 5 for you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/09-api   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs
`uvicorn main:app --reload` in this folder with the venv's Python, so there's nothing to activate. Ctrl+C stops the
server. Then ask it a question as in Step 6.

---

## 📁 Project Structure

```text
09-api/
├── main.py                               # the FastAPI app: start-up, QueryIn/QueryOut, the three routes
├── rag_engine.py                         # RAGEngine: build(), query(), aquery(), stats()
├── rag_chain.py                          # the prompt and make_rag_chain(): retrieval, then the answer
├── retriever.py                          # make_retriever() (5 chunks per question), format_docs(), sample questions
├── vector_store.py                       # make_vector_store() (Qdrant, in memory), add_knowledge_base()
├── models.py                             # the Gemini models: the embedding model and the chat model
├── config.py                             # load_api_key(): the key from .env, checked before anything else
├── chunking.py                           # split_documents(): chunks of at most 512 characters
├── knowledge_base.py                     # load_documents(): the 10 articles as Documents
├── data/
│   └── sample_it_kb.csv                  # the knowledge base: 10 IT support articles
├── tests/
│   ├── conftest.py                       # skips the live tests when there's no key
│   ├── fakes.py                          # stand-ins for Gemini, so the plain tests make no calls
│   └── test_*.py                         # one test file per module
├── .env.example                          # copy it to .env and put your key in it
├── requirements.txt                      # the packages, pinned to exact versions, FastAPI and uvicorn included
├── requirements-dev.txt                  # requirements.txt plus pytest and httpx2, for the tests
├── pytest.ini                            # finds the tests in tests/, and defines the "live" marker
└── README.md                             # you are here
```

---

## 🧪 Testing

```bash
python -m pytest                     # 48 passed, 7 skipped     (add -v for one line per test)
```

The plain tests use stand-ins for Gemini, so they need no key and make no calls. FastAPI's `TestClient` sends their
requests to the app without starting a server. For the API, they check `/api/health`; that the engine is built at
start-up; that a question gets the answer and its sources; that a bad question gets a 422 and no call; that a failed
Gemini call gets a 502 without the details; and that without a key the server stops with the message, not a stack
trace.

The 7 skipped tests are live tests, marked `live`: they call the real Gemini, so `tests/conftest.py` skips them when
no key is set. With your key in `.env`, they run too. To run only the plain ones: `python -m pytest -m "not live"`.

---

## 📊 Understanding the Output

| Request | Status | What comes back |
|---|---|---|
| `GET /api/health` | 200 | `{"status":"ok"}` |
| `GET /api/stats` | 200 | what the engine holds and how it's set up |
| `POST /api/query`, a good question | 200 | `{"answer": "...", "sources": [up to 3]}` |
| `POST /api/query`, an empty, blank or too-long question | 422 | what's wrong with it, and no call to Gemini |
| `POST /api/query`, Gemini doesn't answer | 502 | `{"detail":"Gemini didn't answer (<the error's type>)."}`; the full reason is in the server's terminal |

A bad question gets FastAPI's own description of the problem. For `{"question": ""}`:

```text
{"detail":[{"type":"string_too_short","loc":["body","question"],"msg":"String should have at least 1 character","input":"","ctx":{"min_length":1}}]}
```

Spaces around a question are removed first, so `"   "` gets the same `string_too_short` error. A question over 500
characters gets
`"type":"string_too_long"`, `"msg":"String should have at most 500 characters"`.

Each source has the article's `title`, `system` and `category`, and a `snippet`: the first 200 characters of its
chunk, with `...` when the chunk is longer.

---

## 🎓 Key Concepts Demonstrated

### 1. Build Once, at Start-Up

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    engine.build()
    ...
    yield
```

FastAPI runs the code before `yield` once, before the server takes any request. Building here embeds the chunks once,
not on every request. Importing `main.py` builds nothing: `engine = RAGEngine()` only stores settings.

### 2. The Request's Shape Is Checked Before the Route Runs

```python
class QueryIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=500)
```

FastAPI checks each request's JSON against `QueryIn` first. A bad question never reaches the engine, so it costs
nothing. `QueryOut` shapes each answer the same way on the way out.

### 3. Async Routes

```python
return await engine.aquery(body.question)
```

While Gemini works on one question, the server can take other requests.

### 4. Errors: the Detail for the Terminal, a Short Message for the Caller

When the call to Gemini fails, `query()` logs the full reason in the server's terminal and sends the caller only a 502
with the error's type. The caller learns that Gemini didn't answer, without the details of how.

---

## 🛠️ Troubleshooting

**Issue**: The terminal shows `Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).`, and the server doesn't start
**Fix**: Press Ctrl+C (with `--reload`, uvicorn keeps waiting), put your key in `.env` (Step 4), and start it again.

**Issue**: `Can't build the models: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Replace it with your key.

**Issue**: A question gets `{"detail":"Gemini didn't answer (...)."}` with status 502
**Fix**: The server's terminal has a `Gemini call failed:` line with the reason Gemini gave. Fix what it says, then
ask again.

**Issue**: http://127.0.0.1:8000 doesn't open in Codespaces
**Fix**: `127.0.0.1` is your own computer. Open the **Ports** tab next to **Terminal** and click the globe icon on port
8000.

---

## 📚 Next Steps

**[10 · Chat Page](../10-chat-page/README.md)**: this project answers programs over HTTP. 10 adds a web page, served
by the same server, to ask questions in.

**[Advanced · 09 · API](../../Advanced/09-api/README.md)** (planned): the same project, production grade. Its README
lists what it will add.

### Ideas to Try

- Send `{"question": ""}` from the `/docs` page and read the 422 it gets back.
- Ask the same question twice, and compare the two answers and their sources.
- Change `max_length=500` in `QueryIn` to 50, restart, and send a longer question.
