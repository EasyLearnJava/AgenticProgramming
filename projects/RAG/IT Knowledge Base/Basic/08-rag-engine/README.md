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
- **`aquery(question)`**: the same as `query()`, for async code
- **`stats()`**: what the engine holds (10 articles, 28 chunks) and how it's set up
- **The script** builds the engine and answers the three sample questions, or the one you give it

**Try it:** `python rag_engine.py "printer not found"`, and read the answer with its sources.

---

## 🏗️ Architecture

```text
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
```

### The Pipeline in This Project

1. **Configure** → `RAGEngine()` stores the models, the Qdrant client, the data file, the collection and the
   sizes; it reads nothing
2. **Build** → `build()` loads and chunks the articles, embeds and stores the chunks, and makes the chain
3. **Ask** → `query(question)` runs the chain: the 5 closest chunks, then Gemini's answer from them
4. **Name the sources** → the first 3 different articles among those chunks, closest first, each with the first 200
   characters of its chunk
5. **Report** → `stats()` gives what the engine holds and how it's set up

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
python rag_engine.py
```

It prints what it built, then each question (`Q:`), its answer (`A:`) and its sources. The parts in `< >` come from
Gemini, so they change from run to run:

```text
Built: 10 articles, 28 chunks

Q: How do I fix VPN connection timeouts?
A: <Gemini's answer>
   source: <article title> (<system>, <category>)
   ...

Q: I can't set up MFA on my mobile device
A: <Gemini's answer>
   ...

Q: My laptop is running very slow
A: <Gemini's answer>
   ...
```

To ask your own question, put it after the script's name:

```bash
python rag_engine.py "printer not found"
```

### Or: Run It in One Command

With your key in `.env` (Step 4), this one command does Steps 2, 3 and 5 for you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/08-rag-engine   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs
`python rag_engine.py` in this folder with the venv's Python, so there's nothing to activate. The output is the same
as in Step 5.

---

## 📁 Project Structure

```text
08-rag-engine/
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
├── requirements.txt                      # the packages, pinned to exact versions
├── requirements-dev.txt                  # requirements.txt plus pytest, for the tests
├── pytest.ini                            # finds the tests in tests/, and defines the "live" marker
└── README.md                             # you are here
```

---

## 🧪 Testing

```bash
python -m pytest                     # 42 passed, 6 skipped     (add -v for one line per test)
```

The plain tests use stand-ins for Gemini, so they need no key and make no calls. For the engine, they check that
nothing is read or called before `build()`; that `build()` embeds the 28 chunks in one call; that `query()` gives the
answer and up to 3 different sources; that `aquery()` gives the same; that other chunk sizes and numbers of chunks,
another data file and another collection can be set, and engines in collections of their own keep their own
chunks; and that every setting is passed by name.

The 6 skipped tests are live tests, marked `live`: they call the real Gemini, so `tests/conftest.py` skips them when
no key is set. With your key in `.env`, they run too. To run only the plain ones: `python -m pytest -m "not live"`.

---

## 📊 Understanding the Output

```text
Built: 10 articles, 28 chunks                     ← build() is done: the chunks are embedded and stored

Q: How do I fix VPN connection timeouts?         ← the question
A: <Gemini's answer>                              ← written from the 5 closest chunks only
   source: <article title> (<system>, <category>) ← up to 3 sources, each a different article, closest first
```

`query()` gives back a dictionary, and the script prints it:

```python
{"answer": "...", "sources": [{"title": "...", "system": "...", "category": "...", "snippet": "..."}, ...]}
```

Each source's `snippet` is the first 200 characters of its chunk, with `...` when the chunk is longer. `stats()`
gives `{"documents": 10, "chunks": 28, "collection": "it_knowledge_base", "chunk_size": 512, "chunk_overlap": 50,
"top_k": 5, "embedding_model": "gemini-embedding-001", "chat_model": "gemini-3.5-flash-lite"}`.

The chunks are embedded once, in `build()`: one call to Gemini. Each question then makes two: its embedding and its
answer. So the three sample questions make 7 calls in all.

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

### 4. `query()` and `aquery()`

`aquery()` does what `query()` does, with `await`: while Gemini works, a program that runs many requests at once can
get on with the others.

---

## 🛠️ Troubleshooting

**Issue**: `ModuleNotFoundError: No module named 'langchain_core'`
**Fix**: The venv isn't active, or the packages aren't installed in it. Activate it (Step 2), then
`pip install -r requirements-dev.txt` (Step 3).

**Issue**: `Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).`
**Fix**: There's no `.env` with a key in this folder. Do Step 4.

**Issue**: `Can't build the models: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Replace it with your key.

---

## 📚 Next Steps

**[09 · API](../09-api/README.md)**: this project answers questions from the command line. 09 puts the engine behind
a web server, so any program can ask it questions over HTTP.

**[Advanced · 08 · RAG Engine](../../Advanced/08-rag-engine/README.md)** (planned): the same project, production
grade. Its README lists what it will add.

### Ideas to Try

- Ask a question of your own, and check that each source is a different article.
- Change `MAX_SOURCES` in `rag_engine.py` from 3 to 1, and see one source per answer.
- Build the engine with `RAGEngine(top_k=2)`, and compare its answers with the default 5 chunks.
