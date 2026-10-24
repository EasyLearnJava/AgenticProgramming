# 11 · Qdrant on Disk

The IT knowledge base app, with its chunks kept on disk between runs: Qdrant still runs inside the app, in local mode,
but now saves them in the folder `qdrant_data/`. The first run embeds and stores the 28 chunks; every run after that
finds them there and reuses them, with no call to Gemini for the chunks. The engine, the API and the chat page answer
questions from them. Built with **Qdrant** (local mode), **FastAPI**, **LangChain** and **Gemini**
(`gemini-embedding-001` and `gemini-3.5-flash-lite`).

In a RAG app, embedding the knowledge base is the slow, costly part, so a real app embeds each chunk once and keeps
its vector, until the chunk or the model changes.

> **Needs:** Python 3.11 or newer, and a Gemini API key. Qdrant runs inside the app, so there's no server to start.
> The first run makes 1 call to Gemini for the 28 chunks; later runs make none for them. Each question makes 2.

---

## 🎯 What This Project Does

- **Runs Qdrant inside the app**, in local mode: `make_client()` opens the folder `qdrant_data/`, next to the code,
  which keeps the points between runs
- **Gives each chunk an id made from how it was embedded and what it holds**: the embedding model's name, the vector
  size, the chunk's labels and its text. The same chunk, embedded the same way, always gets the same id
- **Reuses what's stored**: when the engine builds, it checks what `qdrant_data/` holds. If it's exactly these 28
  chunks, embedded the same way, it reuses them, with no call to Gemini; if not (the first run, an article changed,
  or another model or vector size), it embeds them and stores them in a new collection
- **Answers questions** with the engine in the terminal (`python pipeline.py`), and with the API and the chat page
  (`uvicorn main:app`)
- **Frees the folder when the server stops**: only one program at a time can open `qdrant_data/`, so the API closes
  it on the way out, for its next start or for `python pipeline.py`

**Try it:** run `python pipeline.py` twice, and see the second run reuse the stored chunks.

---

## 🏗️ Architecture

```text
┌──────────────────────────────────┐
│  RAGEngine.build()               │
│  ├─ load_documents()             │  ← the 10 articles
│  ├─ split_documents()            │  ← 28 chunks
│  └─ chunk_id() for each chunk    │  ← an id from the model, the size, the labels and the text
└────────────────┬─────────────────┘
                 │ make_client(): qdrant_data/
                 ↓
┌──────────────────────────────────┐
│  Qdrant, local mode, on disk     │  ← collection "it_knowledge_base", in qdrant_data/
│  holds exactly these 28 ids?     │
│  ├─ yes → reuse them             │     no call to Gemini
│  └─ no  → embed, then store anew │     embed_chunks() (1 call to Gemini), then store_vectors()
└────────────────┬─────────────────┘
                 ↓
┌──────────────────────────────────┐
│  the chain, for each question    │  ← the 5 closest chunks, then Gemini's answer (2 calls)
└──────────────────────────────────┘
   used by python pipeline.py, and by uvicorn main:app (the API and the chat page)
```

### The Pipeline in This Project

1. **Open Qdrant** → `make_client()`: local mode, inside the app, with its points in `qdrant_data/`
2. **Load and chunk** → the 10 articles become 28 chunks, each with an id made from the model, the size, its labels
   and its text
3. **Check what's stored** → if the collection holds exactly these ids, nothing more is done
4. **Embed and store if needed** → otherwise `embed_chunks()` embeds the chunks (one call), then the old collection
   is deleted, and `store_vectors()` stores them in a new one, each under its id
5. **Answer** → each question: the 5 closest chunks from Qdrant, then Gemini's answer (2 calls)
6. **Free the folder** → the API closes Qdrant when the server stops

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**, made in the Google Cloud console, under APIs & Services > Credentials. There, under API
  restrictions, restrict it to the Gemini API (the Generative Language API; not Gemini for Google Cloud API, a
  different service), so a leaked key can't be used for anything else. Every call to Gemini uses your key's quota

---

## 🚀 Quick Start

### Step 1: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Basic/11-qdrant-on-disk"    # from the repo root; quotes for the spaces
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

### Step 5: Run It

```bash
python pipeline.py                   # the three sample questions
uvicorn main:app                     # or the server and the chat page; Ctrl+C stops it
```

`uvicorn main:app` builds the engine at start-up, and its start-up line, `RAG engine built: ...`, ends with `(already
stored, reused)` when the chunks were already in `qdrant_data/`, or with `(embedded and stored)`. Then open
http://127.0.0.1:8000 for the chat page; the API answers at `/docs`, `/api/query`, `/api/stats` and `/api/health`.
Only one program at a time can open `qdrant_data/`, so stop the server (Ctrl+C) before running `python pipeline.py`.

In GitHub Codespaces, `127.0.0.1` is your own computer, not the codespace: open the **Ports** tab next to
**Terminal** and click the globe icon on port 8000.

### Or: Run It in One Command

With your key in `.env` (Step 4), this one command does Steps 2 and 3, then starts the server from Step 5:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/11-qdrant-on-disk    # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs
`uvicorn main:app` in this folder with the venv's Python, so there's nothing to activate. Ctrl+C stops it.
Then open http://127.0.0.1:8000 for the chat page. For `python pipeline.py`, use Step 5.

---

## 🧪 Testing

The plain tests keep Qdrant in memory, or in a folder of each test's own, never in `qdrant_data/`:

```bash
python -m pytest -m "not live"       # 69 passed, 9 deselected  (add -v for one line per test)
```

They use stand-ins for Gemini, so they need no key and make no calls. They check:

- **The ids**: each chunk gets its own id, always the same one, and is stored under it; another model, another
  vector size or other labels give another id; and storing the same chunks again replaces them instead of adding
  copies
- **Reuse**: the first build embeds and stores the 28 chunks, and a later build finds them and embeds nothing; other
  chunk sizes, or another embedding model, embed again and replace the stored chunks, while an engine with a
  collection of its own keeps its chunks; and a failed embedding leaves the stored chunks as they were
- **The store and the engine**: an existing collection is deleted and made new, with none of its old points, on disk
  too, while one that's opened keeps its points; the points stay on disk; the 28 chunks are embedded in one call, and
  a chunk without a vector stops the store; another data file can be read; `stats()` names the engine's own models;
  every setting is passed by name; and the server frees `qdrant_data/` when it stops
- **The pipeline**: it builds the engine, then answers each question; a second run reuses the stored chunks, in memory
  and on disk, and the server's start-up line says whether it did; without a key, it and the server stop with the
  message, not a traceback; and no other file runs anything in the terminal

The 9 deselected tests are live tests, marked `live`: they call the real Gemini, so they need your key in `.env`; with
no key, `tests/conftest.py` skips them, so plain `python -m pytest` runs only the others. Two of them, like the app,
use `qdrant_data/`: stop the server first. Together, all 9 embed more than 100 texts, the free tier's limit for a
minute, so on the free tier, run them one file at a time, a minute apart:
`python -m pytest -m live tests/test_rag_engine.py`.

---

## 🎓 Key Concepts Demonstrated

### 1. Qdrant on Disk Keeps the Data

Qdrant's local mode keeps its points in memory or, with `path=`, in a folder. Qdrant in memory loses everything when
the program ends, so every run embeds the chunks again. On disk, with `QdrantClient(path="qdrant_data")`, it saves its
points in that folder, so the chunks outlive each run of the app. It still runs inside the program, so only one
program at a time can open the folder; for several at once, Qdrant also runs as a server, with the same code.

### 2. An Id Made From the Chunk and the Model

```python
model = getattr(embeddings, "model", type(embeddings).__name__)   # "gemini-embedding-001"
labels = json.dumps(chunk.metadata, sort_keys=True)
key = f"it-kb/{model}/{size}/{labels}/{chunk.page_content}"
return str(uuid.uuid5(uuid.NAMESPACE_URL, key))
```

The same chunk, embedded the same way, always gets the same id, and `store_vectors()` stores each chunk under it.
Storing it again replaces the stored point instead of adding a copy, and the engine can check whether Qdrant holds
exactly these chunks by their ids.

The model and the size are in the key because a vector belongs to the model that made it. Vectors from two models
can't be compared, even at the same size: each model puts meanings in its own directions. So a new model, or a new
`EMBEDDING_SIZE`, gives every chunk a new id, nothing stored matches, and the chunks are embedded again. The labels
are in the key too: change only an article's priority, and its chunks are stored again with the new labels.

### 3. Reuse What's Already There

`build()` counts the points in the collection and looks up the 28 ids:

- all of them stored, and nothing else: reuse them, through `open_vector_store()`, with no call to Gemini;
- anything else (an edited article, other chunk sizes, another model or vector size): embed the chunks with
  `embed_chunks()`, then store them with `store_vectors()` in a new collection from `make_vector_store()`, which
  deletes the old one first;
- no collection yet (the first run): embed them, then make it and store them.

If any chunk changed, all 28 are embedded again, still in one call; a bigger app would embed only the new ones. And
`make_vector_store()` deletes the old collection's points before the collection itself: on Windows, Qdrant can't
remove the files of a collection it has open, and a new collection by the same name would find the old points in them.

The chunks are embedded before the old collection is deleted, so if the call to Gemini fails, the stored chunks are
still there. Two runs, one after the other, start:

```text
Step 1: Build the engine: 10 articles, 28 chunks (embedded and stored) in qdrant_data/
```

```text
Step 1: Build the engine: 10 articles, 28 chunks (already stored, reused) in qdrant_data/
```

The second run made no call to Gemini for the chunks: only the question was embedded.

Only the engine's own collection is checked or deleted: `it_knowledge_base`, unless it's given another. So an
engine with other chunk sizes can share `qdrant_data/` without replacing these chunks, in a collection of its own.
In the same program, it also shares the built engine's client, since the folder can't be opened twice at once:
`RAGEngine(collection="it_kb_1000", chunk_size=1000, client=engine.client)`.

### 4. Closing the Folder

```python
    yield
    engine.client.close()          # the server is stopping: free qdrant_data/ for the next start
```

Local mode locks `qdrant_data/` while it's open, so a second program can't open it. The API's start-up code closes
it when the server stops, so the server can start again, and `python pipeline.py` can run once the server has
stopped.

---

## 🛠️ Troubleshooting

**Issue**: `.venv\Scripts\Activate.ps1 cannot be loaded because running scripts is disabled on this system.`
**Fix**: Windows PowerShell blocks scripts until you allow them. Allow local ones once, with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or for this window only, with
`Set-ExecutionPolicy -Scope Process Bypass`, then activate again (Step 2). The one command needs no activating.

**Issue**: `GoogleGenerativeAIError: Error embedding content (INVALID_ARGUMENT): 400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'API key not valid. Please pass a valid API key.', ...`
**Fix**: Gemini didn't accept the key in `.env`. Copy it again from the Google Cloud console, with nothing before or
after it.

**Issue**: An error with `403 PERMISSION_DENIED` in it
**Fix**: Google refused the key for this service. In the Google Cloud console, open the key: under API restrictions
it should list the Gemini API (the Generative Language API), not Gemini for Google Cloud API, and under
Application restrictions, None. New settings can take up to 5 minutes to work.

**Issue**: `GoogleGenerativeAIError: Error embedding content (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, ...`
**Fix**: Your key has used its quota. On the free tier, that's 100 embedded texts a minute; a first run embeds 28
chunks, and each question 1 text. The message ends with "Please retry in" and a number of seconds. Wait that long,
then try again.

**Issue**: A question gets `{"detail":"Couldn't answer the question (...)."}` with status 502, or the page says so
**Fix**: The server's terminal has a `Couldn't answer:` line with the reason, then the traceback. Fix what it says,
then ask again.

**Issue**: `python pipeline.py`, or the server's start-up, stops with `RuntimeError: Storage folder .../qdrant_data is already accessed by another instance of Qdrant client. If you require concurrent access, use Qdrant server instead.`
**Fix**: Another program has `qdrant_data/` open: usually the server (`uvicorn main:app`) while you run
`python pipeline.py`, or the other way round. Only one program at a time can open the folder. Stop the other one
(Ctrl+C), then try again.

**Issue**: `Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).`
**Fix**: There's no `.env` with a key in this folder. Do Step 4.

**Issue**: `Can't build the models: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Replace it with your key.

**Issue**: `Can't build the models: .env isn't saved as UTF-8 text. Open it in an editor and save it with UTF-8 encoding.`
**Fix**: `.env` was saved in another encoding, often UTF-16 by Windows PowerShell 5's `echo ... > .env`. Save it
again as UTF-8, or make it with `copy .env.example .env` and edit it.

**Issue**: `ModuleNotFoundError: No module named 'langchain_core'` (or another of the packages)
**Fix**: The venv isn't active, or the packages aren't installed in it. Activate it (Step 2), then
`pip install -r requirements-dev.txt` (Step 3).

**Issue**: An error with `[Errno 10048]` or `address already in use` in it, and the server stops
**Fix**: Another server, often another project's, already has port 8000. Stop it (Ctrl+C in its terminal), or
start this one on another port, `uvicorn main:app --port 8001`, and use 8001 in the address.

**Issue**: `uvicorn` isn't found: PowerShell says it `is not recognized`, bash says `command not found`
**Fix**: The venv isn't active, so its `uvicorn` isn't on the path. Activate it (Step 2), or use the one command,
which needs no activating.

---

## 💡 Ideas to Try

- Run `python pipeline.py` twice, and compare the first line of each run.
- Change one word in an article's problem text in `data/sample_it_kb.csv`, run it again, and see the chunks embedded
  and stored anew. The tests read the same file, so put it back before you run the tests.
- Delete `qdrant_data/` and run `python pipeline.py` again: the first line says the chunks were embedded and stored.
- In `models.py`, change `EMBEDDING_SIZE` to `256` and run `python pipeline.py`: the stored 768-number vectors don't
  match, so the chunks are embedded again. Tests check for 768, so put it back (and run once more) before you run the
  tests.
