# 12 · Tuning

Measure how well the search finds the right article, to help choose the settings. `tuning.py` asks 10 test
questions, each with the article that should answer it, for three chunk sizes, and counts how many find their article
among the closest 1, 3 and 5 chunks. The engine, the API and the chat page answer questions as before, from chunks
kept in a Qdrant server in Docker. Built with **LangChain**, **Gemini** (`gemini-embedding-001` and
`gemini-3.5-flash-lite`), **Qdrant**, **FastAPI** and **Docker**.

> **Needs:** Python 3.11 or newer, and a Gemini API key. `tuning.py` makes 13 calls to Gemini and runs in memory, with
> no Docker; the engine, the API and the chat page need Docker too.

---

## 🎯 What This Project Does

- **Asks 10 test questions**, each with the article that answers it. They use other words than the articles do
  ("sluggish", not "slow"), so finding the article means the meaning matched, not the words
- **Tries three chunk sizes**, 200, 512 and 1000 characters: for each, it stores that size's chunks and searches with
  every question
- **Counts the hits**: how many questions found their article among the closest 1, 3 and 5 chunks (k)
- **With `--answers`**, answers one question twice, from 1 chunk and from 5, to show what the number of chunks does
  to an answer
- **Keeps the app**: `python pipeline.py`, the API and the chat page, with the chunks kept in a Qdrant server in
  Docker

**Try it:** `python tuning.py`, and read which chunk size finds the most articles.

---

## 🏗️ Architecture

```text
EVAL_SET: 10 (question, the article that answers it)
          │ evaluate(): each question embedded once (10 calls)
          ↓
┌────────────────────────────────────────┐
│  for each chunk size: 200, 512, 1000   │
│  ├─ split_documents()                  │  ← 49, 28 or 10 chunks
│  ├─ a new Qdrant store, in memory      │  ← the chunks embedded (1 call per size)
│  └─ each question: the 5 closest       │  ← is its article in the first 1, 3, 5?
└───────────────────┬────────────────────┘
                    ↓
     print_table(): one line per chunk size

with --answers:  compare_top_k()  ← one question answered from 1 chunk, then from 5 (2 answers)
```

### The Pipeline in This Project

1. **Embed the questions** → each of the 10 questions once: 10 calls to Gemini, reused for every chunk size
2. **For each chunk size** → cut the articles into chunks of that size, and store them in a new in-memory Qdrant
   store: one call to Gemini per size
3. **Search** → each question finds its 5 closest chunks, once per chunk size
4. **Score** → for k = 1, 3 and 5, count the questions whose article is among the first k chunks' articles
5. **Print** → the table: one line per chunk size
6. **With `--answers`** → the first question answered from 1 chunk and from 5, with the 512-character chunks

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**: every call to Gemini uses your key's quota
- **Docker**, only for the engine, the API and the chat page: `tuning.py` doesn't need it

---

## 🚀 Quick Start

### Step 1: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Basic/12-tuning"   # from the repo root; quotes for the spaces
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

### Step 5: Run It

```bash
python tuning.py                     # the table
python tuning.py --answers           # the table, then one question answered from 1 chunk and from 5
```

`python tuning.py` prints a table with one line per chunk size: how many chunks it made, and how many of the 10
questions found their article in the top 1, 3 and 5 chunks. Here `n` stands for those counts, which come from Gemini:

```text
10 questions, each with the article that answers it.

chunk size  chunks  found in top 1  found in top 3  found in top 5
       200      49   n of 10       n of 10       n of 10
       512      28   n of 10       n of 10       n of 10
      1000      10   n of 10       n of 10       n of 10
```

With `--answers`, the two answers follow the table. The parts in `< >` come from Gemini:

```text
--- 'My VPN keeps dropping when I work from home', answered from 1 chunk:
<Gemini's answer>

--- 'My VPN keeps dropping when I work from home', answered from 5 chunks:
<Gemini's answer>
```

### Step 6: Run the App (Optional)

The engine, the API and the chat page keep their chunks in a Qdrant server, so start it first:

```bash
docker compose up -d                 # start the Qdrant server, in the background
python pipeline.py                   # the three sample questions
uvicorn main:app --reload            # or the server: the chat page at http://127.0.0.1:8000; Ctrl+C stops it
```

The first run embeds and stores the chunks in the server; every run after that reuses them. `docker compose down`
stops the server and keeps the chunks; `docker compose down -v` deletes them too.

### Or: Run It in One Command

With your key in `.env` (Step 4), this one command does Steps 2, 3 and 5 for you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/12-tuning   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs `python tuning.py`
in this folder with the venv's Python, so there's nothing to activate. Options after the project's name go to
`tuning.py`: add `--answers` at the end for the two answers. The output is the same as in Step 5.

---

## 📁 Project Structure

```text
12-tuning/
├── tuning.py                             # EVAL_SET, evaluate(), print_table(), compare_top_k()
├── docker-compose.yml                    # the Qdrant server: qdrant/qdrant:v1.19.1 on port 6333, data in a volume
├── index.html                            # the chat page
├── pipeline.py                           # the same steps in the terminal: build, then answer the sample questions
├── main.py                               # the FastAPI app: start-up, the page, the three API routes
├── rag_engine.py                         # RAGEngine (build() reuses stored chunks) and print_result()
├── rag_chain.py                          # the prompt and make_rag_chain(): retrieval, then the answer
├── retriever.py                          # make_retriever() (5 chunks per question), format_docs(), sample questions
├── vector_store.py                       # make_client(), make_vector_store(), open_vector_store(), chunk_id()
├── models.py                             # the Gemini models: the embedding model and the chat model
├── config.py                             # load_api_key(): the key from .env, checked before anything else
├── chunking.py                           # split_documents(): chunks of at most 512 characters, by default
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
python -m pytest                     # 64 passed, 8 skipped     (add -v for one line per test)
```

The plain tests use stand-ins for Gemini, so they need no key and make no calls. For the tuning, they check that the
test questions cover every article once; that `evaluate()` scores each chunk size; that the questions are embedded
once, and each chunk size's chunks once; that the table has a line per chunk size; and that `compare_top_k()` answers
the question once for each k. For `pipeline.py`, they check that it builds the engine, then answers each question;
that a second run reuses the stored chunks; that without Qdrant it stops with what to do; and that only it and
`tuning.py` run anything in the terminal.

The 8 skipped tests are live tests, marked `live`: they call the real Gemini, so `tests/conftest.py` skips them when
no key is set. With your key in `.env`, they run too. To run only the plain ones: `python -m pytest -m "not live"`.

---

## 📊 Understanding the Output

```text
chunk size  chunks  found in top 1  found in top 3  found in top 5
       200      49   n of 10       n of 10       n of 10
       │        │    └─ how many of the 10 questions had their article in the closest chunk, the 3 closest, the 5
       │        └─ how many chunks that size made from the 10 articles
       └─ the largest a chunk may be, in characters
```

- **Smaller chunks** each hold less of an article, so a question can match one part closely, but an article's answer
  may be spread over several chunks.
- **Bigger chunks** hold more context; at 1000 characters every article fits in one chunk, so there are 10.
- **A bigger k** gives the question more chances to find its article: `found in top 5` is never lower than
  `found in top 1`.

`--answers` shows the other side of k: with 1 chunk the model may miss part of the fix; with 5 it has more to go on,
and more to sort through.

`tuning.py` makes 13 calls to Gemini: one for each question and one for each chunk size. `--answers` adds 5 more: 3
embeddings (the chunks once, the question for each answer) and 2 answers. Everything in `tuning.py` runs in memory:
it doesn't touch the chunks stored in the Qdrant server.

---

## 🎓 Key Concepts Demonstrated

### 1. Measure Before You Tune

Chunk size and k are guesses until something measures them. A fixed set of questions, each with its right article,
turns "the search seems fine" into a count you can compare between settings.

### 2. Test Questions in Other Words

```python
("Everything on my computer is really sluggish", "Laptop Performance Degradation"),
```

The questions avoid the articles' own words where they can, so a hit means the meaning matched, not the spelling.

### 3. Embed Each Question Once

`evaluate()` embeds the 10 questions once and reuses their vectors for every chunk size, then searches once per
question for the most chunks needed (5) and checks the first 1, 3 and 5. Fewer calls, the same counts.

### 4. A Fresh Store for Each Setting

Each chunk size gets its own in-memory Qdrant store, so one setting's chunks never mix with another's, and the chunks
kept in the Qdrant server stay as they are.

---

## 🛠️ Troubleshooting

**Issue**: `Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).`
**Fix**: There's no `.env` with a key in this folder. Do Step 4.

**Issue**: `Can't build the models: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Replace it with your key.

**Issue**: The server stops at start-up with `RuntimeError: Can't reach Qdrant at http://localhost:6333 (<the connection error>). Start it first, in this folder:   docker compose up -d`
**Fix**: Qdrant isn't running. Run `docker compose up -d`, then start the server again. `python pipeline.py` stops
too, with `Can't reach Qdrant at ...` and the same advice: the same fix. `tuning.py` doesn't need Qdrant.

**Issue**: `ModuleNotFoundError: No module named 'langchain_core'`
**Fix**: The venv isn't active, or the packages aren't installed in it. Activate it (Step 2), then
`pip install -r requirements-dev.txt` (Step 3).

---

## 📚 Next Steps

**[Advanced · 12 · Tuning](../../Advanced/12-tuning/README.md)** (planned): the same project, production grade. Its
README lists what it will add.

### Ideas to Try

- Add 300 to `CHUNK_SIZES` in `tuning.py`, and see where it lands in the table.
- Reword one question in `EVAL_SET` to use its article's own words, and see whether it's found in the top 1 more
  often.
- Run `python tuning.py --answers`, and compare the answer from 1 chunk with the one from 5.
