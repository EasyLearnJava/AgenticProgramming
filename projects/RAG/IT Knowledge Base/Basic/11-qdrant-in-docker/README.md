# 11 · Qdrant in Docker

The IT knowledge base app, with its chunks kept in a Qdrant server that runs in Docker and keeps them on disk between
runs. The first run embeds and stores the 28 chunks; every run after that finds them there and reuses them, with no
call to Gemini for the chunks. The engine, the API and the chat page answer questions from them. Built with
**Qdrant** in **Docker**, **FastAPI**, **LangChain** and **Gemini** (`gemini-embedding-001` and
`gemini-3.5-flash-lite`).

> **Needs:** Python 3.11 or newer, a Gemini API key, and Docker (Docker Desktop on Windows and macOS; GitHub
> Codespaces has Docker already).

---

## 🎯 What This Project Does

- **Runs Qdrant as a server**, in Docker: `docker-compose.yml` starts `qdrant/qdrant:v1.19.1` on port 6333, with its
  data in a Docker volume
- **Finds the server** at the address in `.env`: `QDRANT_URL=http://localhost:6333`
- **Gives each chunk an id made from its text**, so the same chunk always gets the same id
- **Reuses what's stored**: when the engine builds, it checks what the server holds. If it's exactly these 28
  chunks, it reuses them, with no call to Gemini; if not (the first run, or after an article changed), it stores them
  anew
- **Answers questions** with the engine (`python rag_engine.py`), the API and the chat page (`uvicorn main:app`)
- **Says what to do when Qdrant isn't running**: the server stops at start-up with `docker compose up -d` in its
  message

**Try it:** run `python rag_engine.py` twice, and see the second run reuse the stored chunks.

---

## 🏗️ Architecture

```text
┌──────────────────────────────────┐
│  RAGEngine.build()               │
│  ├─ load_documents()             │  ← the 10 articles
│  ├─ split_documents()            │  ← 28 chunks
│  └─ chunk_id() for each chunk    │  ← an id made from the chunk's article, place and text
└────────────────┬─────────────────┘
                 │ make_client(): QDRANT_URL
                 ↓
┌──────────────────────────────────┐
│  Qdrant server, in Docker        │  ← collection "it_knowledge_base", kept on disk
│  holds exactly these 28 ids?     │
│  ├─ yes → reuse them             │     no call to Gemini
│  └─ no  → empty it, store anew   │     1 call to Gemini: the 28 embeddings
└────────────────┬─────────────────┘
                 ↓
┌──────────────────────────────────┐
│  the chain, for each question    │  ← the 5 closest chunks, then Gemini's answer (2 calls)
└──────────────────────────────────┘
   used by python rag_engine.py, and by uvicorn main:app (the API and the chat page)
```

### The Pipeline in This Project

1. **Start Qdrant** → `docker compose up -d` runs the server, which keeps its data in a Docker volume
2. **Connect** → `make_client()` makes a client for the server at `QDRANT_URL`
3. **Load and chunk** → the 10 articles become 28 chunks, each with an id made from its text
4. **Check what's stored** → if the collection holds exactly these ids, nothing more is done
5. **Store if needed** → otherwise the collection is emptied, and the chunks are embedded (one call) and stored
6. **Answer** → each question: the 5 closest chunks from the server, then Gemini's answer (2 calls)

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**: every call to Gemini uses your key's quota
- **Docker**: Docker Desktop on Windows and macOS; GitHub Codespaces has Docker already

---

## 🚀 Quick Start

### Step 1: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Basic/11-qdrant-in-docker"   # from the repo root; quotes for the spaces
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
APIs & Services > Credentials, as `.env.example` says. Leave the `QDRANT_URL` line as it is. `.env` is in
`.gitignore`, so your key never goes into git.

### Step 5: Start Qdrant

```bash
docker compose up -d                 # start the Qdrant server, in the background
```

It starts the server and leaves it running, even after you close the terminal. The first time, Docker downloads the
Qdrant image. Qdrant's own dashboard is at http://localhost:6333/dashboard.

To stop it, run `docker compose down` in this folder: the stored chunks stay for next time. `docker compose down -v`
deletes them too.

### Step 6: Run It

```bash
python rag_engine.py                 # the three sample questions
uvicorn main:app --reload            # or the server and the chat page; Ctrl+C stops it
```

The first `python rag_engine.py` embeds the chunks and stores them in the server:

```text
Built: 10 articles, 28 chunks (embedded and stored) in Qdrant at http://localhost:6333
```

Every run after that finds them there:

```text
Built: 10 articles, 28 chunks (already stored, reused) in Qdrant at http://localhost:6333
```

Then come each question (`Q:`), its answer (`A:`) and its sources. The parts in `< >` come from Gemini:

```text
Q: How do I fix VPN connection timeouts?
A: <Gemini's answer>
   source: <article title> (<system>, <category>)
   ...
```

`uvicorn main:app --reload` builds the engine the same way. Then open http://127.0.0.1:8000 for the chat page; the
API answers at `/docs`, `/api/query`, `/api/stats` and `/api/health`.

---

## 📁 Project Structure

```text
11-qdrant-in-docker/
├── docker-compose.yml                    # the Qdrant server: qdrant/qdrant:v1.19.1 on port 6333, data in a volume
├── index.html                            # the chat page
├── main.py                               # the FastAPI app: start-up, the page, the three API routes
├── rag_engine.py                         # RAGEngine: build() reuses stored chunks; query(), aquery(), stats()
├── rag_chain.py                          # the prompt and make_rag_chain(): retrieval, then the answer
├── retriever.py                          # make_retriever() (5 chunks per question), format_docs(), sample questions
├── vector_store.py                       # make_client(), make_vector_store(), chunk_id(), add_knowledge_base()
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
├── .env.example                          # copy it to .env: your key, and QDRANT_URL
├── requirements.txt                      # the packages, pinned to exact versions
├── requirements-dev.txt                  # requirements.txt plus pytest and httpx2, for the tests
├── pytest.ini                            # finds the tests in tests/, and defines the "live" marker
└── README.md                             # you are here
```

---

## 🧪 Testing

The tests don't need Docker:

```bash
python -m pytest                     # 55 passed, 7 skipped     (add -v for one line per test)
```

The plain tests use stand-ins for Gemini, so they need no key and make no calls. For the stored chunks, they check
that each chunk gets its own id, always the same one; that adding the same chunks again replaces them instead of
adding copies; that the first build embeds and stores the 28 chunks, and a later build finds them and embeds nothing;
that other chunk sizes replace the stored chunks; and that without Qdrant the server stops with what to do.

The 7 skipped tests are live tests, marked `live`: they call the real Gemini, so `tests/conftest.py` skips them when
no key is set. With your key in `.env`, they run too. To run only the plain ones: `python -m pytest -m "not live"`.

---

## 📊 Understanding the Output

```text
Built: 10 articles, 28 chunks (embedded and stored) in Qdrant at http://localhost:6333
                               └─ the server didn't hold exactly these chunks: they were embedded (1 call) and stored

Built: 10 articles, 28 chunks (already stored, reused) in Qdrant at http://localhost:6333
                               └─ the server held exactly these 28 chunks: no call to Gemini for them
```

`stats()`, and so `/api/stats`, also says which happened: `"reused_stored_chunks"` is `true` when the stored chunks
were reused.

Qdrant's dashboard, at http://localhost:6333/dashboard, shows the `it_knowledge_base` collection and its 28 points.

---

## 🎓 Key Concepts Demonstrated

### 1. A Server That Keeps the Data

Qdrant inside a Python program loses everything when the program ends. As a server in Docker, it keeps its data in a
Docker volume, `qdrant_storage`, so the chunks outlive each run of the app, and even `docker compose down`.

### 2. An Id Made From the Chunk's Text

```python
key = f"it-kb/{chunk.metadata['doc_id']}/{chunk.metadata['start_index']}/{chunk.page_content}"
return str(uuid.uuid5(uuid.NAMESPACE_URL, key))
```

The same chunk always gets the same id. Adding it again replaces the stored point instead of adding a copy, and the
engine can check whether the server holds exactly these chunks by their ids.

### 3. Reuse What's Already There

`build()` counts the points in the collection and looks up the 28 ids:

- all of them stored, and nothing else: reuse them, no call to Gemini;
- anything else (an edited article, other chunk sizes): empty the collection, then store the chunks anew;
- no collection yet (the first run): store them.

### 4. Configuration in `.env`

`QDRANT_URL` says where the server is, next to the key. To use a Qdrant server somewhere else, you change `.env`,
not the code.

---

## 🛠️ Troubleshooting

**Issue**: The server stops at start-up with:

```text
RuntimeError: Can't reach Qdrant at http://localhost:6333 (<the connection error>). Start it first, in this folder:   docker compose up -d
```

**Fix**: Qdrant isn't running. Run `docker compose up -d`, then start the server again.

**Issue**: `python rag_engine.py` stops with a long error that ends in `ResponseHandlingException` and the connection
error
**Fix**: The same: Qdrant isn't running. Run `docker compose up -d`, then try again. (Unlike the server,
`rag_engine.py` doesn't turn this error into a short message.)

**Issue**: `Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).`
**Fix**: There's no `.env` with a key in this folder. Do Step 4.

**Issue**: `Can't build the models: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Replace it with your key.

---

## 📚 Next Steps

**[12 · Tuning](../12-tuning/README.md)**: this project answers with fixed settings: chunks of 512 characters, 5 per
question. 12 measures how well the search finds the right article for other chunk sizes and numbers of chunks.

**[Advanced · 11 · Qdrant in Docker](../../Advanced/11-qdrant-in-docker/README.md)** (planned): the same project,
production grade. Its README lists what it will add.

### Ideas to Try

- Run `python rag_engine.py` twice, and compare the first line of each run.
- Change one word in an article in `data/sample_it_kb.csv`, run it again, and see the chunks embedded and stored
  anew.
- Open the dashboard at http://localhost:6333/dashboard and find the 28 points of `it_knowledge_base`.
