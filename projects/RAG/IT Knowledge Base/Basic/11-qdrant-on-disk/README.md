# 11 · Qdrant on Disk

The IT knowledge base app, with its chunks kept on disk between runs: Qdrant runs inside the app, in local mode, and
saves them in the folder `qdrant_data/`. The first run embeds and stores the 28 chunks; every run after that finds
them there and reuses them, with no call to Gemini for the chunks. The engine, the API and the chat page answer
questions from them. Built with **Qdrant** (local mode), **FastAPI**, **LangChain** and **Gemini**
(`gemini-embedding-001` and `gemini-3.5-flash-lite`).

> **Needs:** Python 3.11 or newer, and a Gemini API key. Qdrant runs inside the app, so there's no server to start.

---

## 🎯 What This Project Does

- **Runs Qdrant inside the app**, in local mode: `make_client()` opens the folder `qdrant_data/`, next to the code,
  which keeps the points between runs
- **Gives each chunk an id made from its text**, so the same chunk always gets the same id
- **Reuses what's stored**: when the engine builds, it checks what `qdrant_data/` holds. If it's exactly these 28
  chunks, it reuses them, with no call to Gemini; if not (the first run, or after an article changed), it stores them
  in a new collection
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
│  └─ chunk_id() for each chunk    │  ← an id made from the chunk's article, place and text
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
2. **Load and chunk** → the 10 articles become 28 chunks, each with an id made from its text
3. **Check what's stored** → if the collection holds exactly these ids, nothing more is done
4. **Embed and store if needed** → otherwise `embed_chunks()` embeds the chunks (one call), then the old collection
   is deleted, and `store_vectors()` stores them in a new one, each under its id
5. **Answer** → each question: the 5 closest chunks from Qdrant, then Gemini's answer (2 calls)
6. **Free the folder** → the API closes Qdrant when the server stops

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**: every call to Gemini uses your key's quota

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
uvicorn main:app --reload            # or the server and the chat page; Ctrl+C stops it
```

`uvicorn main:app --reload` builds the engine at start-up. Then open http://127.0.0.1:8000 for the chat page; the
API answers at `/docs`, `/api/query`, `/api/stats` and `/api/health`. Only one program at a time can open
`qdrant_data/`, so stop the server (Ctrl+C) before running `python pipeline.py`.

### Or: Run It in One Command

With your key in `.env` (Step 4), this one command does Steps 2 and 3, then starts the server from Step 5:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/11-qdrant-on-disk    # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs
`uvicorn main:app --reload` in this folder with the venv's Python, so there's nothing to activate. Ctrl+C stops it.
Then open http://127.0.0.1:8000 for the chat page. For `python pipeline.py`, use Step 5.

---

## 🧪 Testing

The tests keep Qdrant in memory, or in a folder of each test's own, never in `qdrant_data/`:

```bash
python -m pytest                     # 65 passed, 8 skipped     (add -v for one line per test)
```

The plain tests use stand-ins for Gemini, so they need no key and make no calls. For the stored chunks, they check
that an existing collection is deleted and made new, with none of its old points, on disk too, while one that's opened
keeps its points; that each chunk gets its own id, always the same one, and is stored under it; that storing the same
chunks again replaces them instead of adding copies; that the 28 chunks are embedded in one call, and a chunk without
a vector stops the store; that the first build embeds and stores the 28 chunks, and a later build finds them and
embeds nothing; that other chunk sizes replace the stored chunks, while an engine with a collection of its own keeps
its chunks; that a failed embedding leaves the stored chunks as they were; that another data file can be read; that
every setting is passed by name; that the points stay on disk; and that the server frees `qdrant_data/` when it stops.
For `pipeline.py`, they check that it builds the engine, then answers each question; that a second run reuses the
stored chunks, in memory and on disk; and that no other file runs anything in the terminal.

The 8 skipped tests are live tests, marked `live`: they call the real Gemini, so `tests/conftest.py` skips them when
no key is set. With your key in `.env`, they run too. To run only the plain ones: `python -m pytest -m "not live"`.

---

## 🎓 Key Concepts Demonstrated

### 1. Qdrant on Disk Keeps the Data

Qdrant in memory loses everything when the program ends. In local mode, `QdrantClient(path="qdrant_data")`, it saves
its points in that folder, so the chunks outlive each run of the app. It still runs inside the program, so only one
program at a time can open the folder; for several at once, Qdrant also runs as a server, with the same code.

### 2. An Id Made From the Chunk's Text

```python
key = f"it-kb/{chunk.metadata['doc_id']}/{chunk.metadata['start_index']}/{chunk.page_content}"
return str(uuid.uuid5(uuid.NAMESPACE_URL, key))
```

The same chunk always gets the same id, and `store_vectors()` stores each chunk under it. Storing it again replaces
the stored point instead of adding a copy, and the engine can check whether Qdrant holds exactly these chunks by
their ids.

### 3. Reuse What's Already There

`build()` counts the points in the collection and looks up the 28 ids:

- all of them stored, and nothing else: reuse them, through `open_vector_store()`, with no call to Gemini;
- anything else (an edited article, other chunk sizes): embed the chunks with `embed_chunks()`, then store them
  with `store_vectors()` in a new collection from `make_vector_store()`, which deletes the old one first;
- no collection yet (the first run): make it, then embed and store them.

The chunks are embedded before the old collection is deleted, so if the call to Gemini fails, the stored chunks are
still there.

Only the engine's own collection is checked or deleted: `it_knowledge_base`, unless it's given another. So an
engine with other chunk sizes can share `qdrant_data/` without replacing these chunks, in a collection of its own:
`RAGEngine(collection="it_kb_1000", chunk_size=1000)`.

### 4. Closing the Folder

```python
    yield
    engine.client.close()          # the server is stopping: free qdrant_data/ for the next start
```

Local mode locks `qdrant_data/` while it's open, so a second program can't open it. The API's start-up code closes
it when the server stops, so `uvicorn --reload` can start again after each change, and `python pipeline.py` can run
once the server has stopped.

---

## 🛠️ Troubleshooting

**Issue**: `python pipeline.py`, or the server's start-up, stops with `RuntimeError: Storage folder .../qdrant_data is already accessed by another instance of Qdrant client. If you require concurrent access, use Qdrant server instead.`
**Fix**: Another program has `qdrant_data/` open: usually the server (`uvicorn main:app`) while you run
`python pipeline.py`, or the other way round. Only one program at a time can open the folder. Stop the other one
(Ctrl+C), then try again.

**Issue**: `Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).`
**Fix**: There's no `.env` with a key in this folder. Do Step 4.

**Issue**: `Can't build the models: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Replace it with your key.

---

## 💡 Ideas to Try

- Run `python pipeline.py` twice, and compare the first line of each run.
- Change one word in an article in `data/sample_it_kb.csv`, run it again, and see the chunks embedded and stored
  anew.
- Delete `qdrant_data/` and run `python pipeline.py` again: the first line says the chunks were embedded and stored.
