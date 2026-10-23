# 12 · Tuning

Measure how well the search finds the right article, to help choose the settings. `tuning.py` asks 10 test
questions, each with the article that should answer it, for three chunk sizes, and counts how many find their article
among the closest 1, 3 and 5 chunks. The engine, the API and the chat page answer questions as before, from chunks
kept on disk in `qdrant_data/` (Qdrant's local mode). Built with **LangChain**, **Gemini** (`gemini-embedding-001` and
`gemini-3.5-flash-lite`), **Qdrant** and **FastAPI**.

> **Needs:** Python 3.11 or newer, and a Gemini API key. `tuning.py` makes 13 calls to Gemini and runs in memory; the
> engine, the API and the chat page keep their chunks in `qdrant_data/`.

---

## 🎯 What This Project Does

- **Asks 10 test questions**, each with the article that answers it. They use other words than the articles do
  ("sluggish", not "slow"), so finding the article means the meaning matched, not the words
- **Tries three chunk sizes**, 200, 512 and 1000 characters: for each, it stores that size's chunks and searches with
  every question
- **Counts the hits**: how many questions found their article among the closest 1, 3 and 5 chunks (k)
- **With `--answers`**, answers one question twice, from 1 chunk and from 5, to show what the number of chunks does
  to an answer
- **Keeps the app**: `python pipeline.py`, the API and the chat page, with the chunks kept on disk in
  `qdrant_data/`

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
│  ├─ embed_chunks()                     │  ← the chunks embedded (1 call per size)
│  ├─ a new Qdrant store, in memory      │  ← store_vectors(): one point per chunk
│  └─ each question: the 5 closest       │  ← is its article in the first 1, 3, 5?
└───────────────────┬────────────────────┘
                    ↓
     print_table(), in utils.py: one line per chunk size

with --answers:  compare_top_k()  ← one question answered from 1 chunk, then from 5 (2 answers)
```

### The Pipeline in This Project

1. **Embed the questions** → each of the 10 questions once: 10 calls to Gemini, reused for every chunk size
2. **For each chunk size** → cut the articles into chunks of that size, embed them (one call to Gemini per size),
   and store them in a new in-memory Qdrant store
3. **Search** → each question finds its 5 closest chunks, once per chunk size
4. **Score** → for k = 1, 3 and 5, count the questions whose article is among the first k chunks' articles
5. **Print** → the table: one line per chunk size
6. **With `--answers`** → the first question answered from 1 chunk and from 5, with the 512-character chunks

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**: every call to Gemini uses your key's quota

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
APIs & Services > Credentials, as `.env.example` says. `.env` is in `.gitignore`, so your key never goes into git.

### Step 5: Run It

```bash
python tuning.py                     # the table
python tuning.py --answers           # the table, then one question answered from 1 chunk and from 5
```

### Step 6: Run the App (Optional)

The engine, the API and the chat page keep their chunks in `qdrant_data/`:

```bash
python pipeline.py                   # the three sample questions
uvicorn main:app --reload            # or the server: the chat page at http://127.0.0.1:8000; Ctrl+C stops it
```

The first run embeds and stores the chunks there; every run after that reuses them. Only one program at a time can
open `qdrant_data/`, so stop the server (Ctrl+C) before running `python pipeline.py`. Delete the folder to start over.

### Or: Run It in One Command

With your key in `.env` (Step 4), this one command does Steps 2, 3 and 5 for you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/12-tuning   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs `python tuning.py`
in this folder with the venv's Python, so there's nothing to activate. Options after the project's name go to
`tuning.py`: add `--answers` at the end for the two answers. The output is the same as in Step 5.

---

## 🧪 Testing

The tests keep Qdrant in memory, or in a folder of each test's own, never in `qdrant_data/`:

```bash
python -m pytest                     # 71 passed, 9 skipped     (add -v for one line per test)
```

The plain tests use stand-ins for Gemini, so they need no key and make no calls. For the tuning, they check that the
test questions cover every article once; that `evaluate()` scores each chunk size; that the questions are embedded
once, and each chunk size's chunks once; that the table has a line per chunk size; and that `compare_top_k()` answers
the question once for each k. For `pipeline.py`, they check that it builds the engine, then answers each question;
that a second run reuses the stored chunks, in memory and on disk; and that only it and `tuning.py` run anything in
the terminal.

The 9 skipped tests are live tests, marked `live`: they call the real Gemini, so `tests/conftest.py` skips them when
no key is set. With your key in `.env`, they run too. To run only the plain ones: `python -m pytest -m "not live"`.

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
kept in `qdrant_data/` stay as they are.

---

## 🛠️ Troubleshooting

**Issue**: `Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).`
**Fix**: There's no `.env` with a key in this folder. Do Step 4.

**Issue**: `Can't build the models: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Replace it with your key.

**Issue**: `python pipeline.py`, or the server's start-up, stops with `RuntimeError: Storage folder .../qdrant_data is already accessed by another instance of Qdrant client. If you require concurrent access, use Qdrant server instead.`
**Fix**: Another program has `qdrant_data/` open: usually the server (`uvicorn main:app`) while you run
`python pipeline.py`, or the other way round. Only one program at a time can open the folder. Stop the other one
(Ctrl+C), then try again. `tuning.py` never opens it.

**Issue**: `ModuleNotFoundError: No module named 'langchain_core'`
**Fix**: The venv isn't active, or the packages aren't installed in it. Activate it (Step 2), then
`pip install -r requirements-dev.txt` (Step 3).

---

## 💡 Ideas to Try

- Add 300 to `CHUNK_SIZES` in `tuning.py`, and see where it lands in the table.
- Reword one question in `EVAL_SET` to use its article's own words, and see whether it's found in the top 1 more
  often.
- Run `python tuning.py --answers`, and compare the answer from 1 chunk with the one from 5.
