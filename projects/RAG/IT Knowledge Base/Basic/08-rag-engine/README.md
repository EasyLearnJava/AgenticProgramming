# 08 · RAG Engine

The whole question-answering pipeline in one class, `RAGEngine`: built once, it then answers each question from the
IT knowledge base with up to 3 sources. Built with **LangChain**, **Gemini** (`gemini-embedding-001` and
`gemini-3.5-flash-lite`) and **Qdrant**, running in memory.

> **Needs:** Python 3.11 or newer, and a Gemini API key. A run with the three sample questions makes 7 calls to
> Gemini.

---

## 🎯 What This Project Does

- **`build()`, once**: loads the 10 articles, cuts them into 28 chunks, embeds and stores them in Qdrant, and makes
  the chain
- **`query(question)`, for each question**: the answer, plus up to 3 sources; each source is a different article,
  with its title, system, category and the start of the chunk's text
- **`stats()`**: what the engine holds (10 articles, 28 chunks) and how it's set up
- **`pipeline.py`**, the one file to run, builds the engine, then answers the three sample questions, or the one you
  give it, naming each step first

**Try it:** `python pipeline.py "printer not found"`, and read the answer with its sources.

---

## 🏗️ Architecture

```text
┌───────────────────────────────────┐
│  pipeline.py: main()              │  ← the one file to run: Step 1, build; Step 2, answer
└────────────────┬──────────────────┘
                 ↓
┌───────────────────────────────────┐
│  RAGEngine()                      │  ← settings only: nothing read, no call yet
└────────────────┬──────────────────┘
                 │ build(), once
                 ↓
┌───────────────────────────────────┐
│  load_documents()                 │  ← the 10 articles
│  split_documents()                │  ← 28 chunks of at most 512 characters
│  make_vector_store()              │  ← Qdrant, in memory
│  store.add_documents()            │  ← the 28 chunks embedded by Gemini (1 call)
│  make_rag_chain(make_retriever()) │  ← the chain: retriever, prompt, Gemini, parser
└────────────────┬──────────────────┘
                 │ query(question), for each question
                 ↓
┌───────────────────────────────────┐
│  chain.invoke(question)           │  ← the question's embedding and the answer (2 calls)
│  _with_sources()                  │  ← the first 3 different articles among the chunks found
└────────────────┬──────────────────┘
                 ↓
   {"answer": "...", "sources": [{"title", "system", "category", "snippet"}, ...]}
                 │
                 ↓
   print_result(), in utils.py: the question, the answer, then each source
```

### The Pipeline in This Project

1. **Run** → `python pipeline.py`: `main()` builds the engine (Step 1), then answers each question (Step 2)
2. **Configure** → `RAGEngine()` stores the models, the Qdrant client, the data file, the collection and the
   sizes; it reads nothing
3. **Build** → `build()` loads and chunks the articles, embeds and stores the chunks, and makes the chain
4. **Ask** → `query(question)` runs the chain: the 5 closest chunks, then Gemini's answer from them
5. **Name the sources** → the first 3 different articles among those chunks, closest first, each with the first 200
   characters of its chunk
6. **Print** → `print_result()`, from `utils.py`: the question, the answer, then each source
7. **Report** → `stats()` gives what the engine holds and how it's set up

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**: every call to Gemini uses your key's quota

---

## 🚀 Quick Start

### Step 1: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Basic/08-rag-engine"   # from the repo root; quotes for the spaces
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
python pipeline.py
```

To ask your own question, put it after `pipeline.py`:

```bash
python pipeline.py "printer not found"
```

### Or: Run It in One Command

With your key in `.env` (Step 4), this one command does Steps 2, 3 and 5 for you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/08-rag-engine   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs
`python pipeline.py` in this folder with the venv's Python, so there's nothing to activate. The output is the same as
in Step 5. A question at the end of the command goes to `pipeline.py`.

---

## 🧪 Testing

```bash
python -m pytest                     # 39 passed, 6 skipped     (add -v for one line per test)
```

The plain tests use stand-ins for Gemini, so they need no key and make no calls. For the engine, they check that
nothing is read or called before `build()`; that `build()` embeds the 28 chunks in one call; that `query()` gives the
answer and up to 3 different sources; that other chunk sizes and numbers of chunks, another data file and another
collection can be set, and engines in collections of their own keep their own chunks; that building again starts
with a new collection; that every setting is passed by name; and what `print_result()` prints. For the pipeline,
they check that it builds the engine, then answers each question, or one of your own, after the steps' names; and
that no other file runs anything.

The 6 skipped tests are live tests, marked `live`: they call the real Gemini, so `tests/conftest.py` skips them when
no key is set. With your key in `.env`, they run too. To run only the plain ones: `python -m pytest -m "not live"`.

---

## 🎓 Key Concepts Demonstrated

### 1. Build Once, Answer Many Times

```python
engine = RAGEngine()          # settings only
engine.build()                # load, chunk, embed and store, make the chain: once
engine.query("...")           # each question: the chain, then the sources
```

The slow, costly part, embedding every chunk, happens once in `build()`. Every question after that only embeds the
question and asks for the answer.

### 2. Configure First, Build Later

```python
RAGEngine(embeddings=..., model=..., embedding_size=768, client=None, data_path=KB_FILE,
          collection="it_knowledge_base", chunk_size=512, chunk_overlap=50, top_k=5)
```

The constructor only stores its settings, each with a default. Passing others changes how the engine is built
without changing its code: the tests pass stand-ins for Gemini this way, and `data_path` and `collection` give
an engine another knowledge base file or a collection of its own. Every setting is passed by name (the `*` at the
start of the constructor's parameters), so `RAGEngine(collection="it_kb_1000", chunk_size=1000)` can't put a value
in the wrong setting.

### 3. Sources: Different Articles, Not Just Chunks

Two of the 5 chunks found can come from one article. `_with_sources()` keeps the first chunk of each article, closest
first, and stops at 3, so every source names a different article.

### 4. One File Runs the Steps

`pipeline.py` is the only file that runs anything: `main()` builds the engine (Step 1, in one line, from `stats()`),
then answers each question (Step 2), and `print_result()`, from `utils.py`, prints each answer. `rag_engine.py` and
the other files only define the parts, so importing them reads nothing and makes no call. The engine is a parameter
of `main()`, so the tests pass one with stand-ins for Gemini.

---

## 🛠️ Troubleshooting

**Issue**: `ModuleNotFoundError: No module named 'langchain_core'`
**Fix**: The venv isn't active, or the packages aren't installed in it. Activate it (Step 2), then
`pip install -r requirements-dev.txt` (Step 3).

**Issue**: `Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).`
**Fix**: There's no `.env` with a key in this folder. Do Step 4.

**Issue**: `Can't build the models: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Replace it with your key.

**Issue**: `python rag_engine.py` prints nothing
**Fix**: That file only defines the engine. Run `python pipeline.py` (Step 5), which builds it and asks it.

---

## 💡 Ideas to Try

- Ask a question of your own with `python pipeline.py "..."`, and check that each source is a different article.
- Change `MAX_SOURCES` in `rag_engine.py` from 3 to 1, and see one source per answer.
- In `pipeline.py`, build the engine with `RAGEngine(top_k=2)`, and compare its answers with the default 5 chunks.
