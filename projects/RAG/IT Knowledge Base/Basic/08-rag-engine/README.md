# 08 · RAG Engine

The whole question-answering pipeline in one class, `RAGEngine`: built once, it then answers each question from the
IT knowledge base, with up to 3 of the articles the search found. Built with **LangChain**, **Gemini**
(`gemini-embedding-001` and `gemini-3.5-flash-lite`) and **Qdrant**, running in memory.

In a RAG app, embedding every chunk is the slow, costly part, so it happens once, not for each question.

> **Needs:** Python 3.11 or newer, and a Gemini API key. A run with the three sample questions makes 7 calls to
> Gemini, which embed 31 texts: the 28 chunks and the 3 questions.

---

## 🎯 What This Project Does

- **`build()`, once: the ingestion half**: loads the 10 articles, cuts them into 28 chunks, embeds and stores them
  in Qdrant, and makes the chain
- **`query(question)`, for each question: the query half**: the answer, plus up to 3 sources: the first different
  articles among the chunks the search found, each with its title, system, category and the start of the chunk's
  text. They're what Gemini was given, not a checked list of what the answer used
- **`stats()`**: what the engine holds (10 articles, 28 chunks) and how it's set up, with its own models' names
- **`pipeline.py`**, the one file to run, builds the engine, then answers the three sample questions, or the one you
  give it, naming each step first

**Try it:** `python pipeline.py "printer not found"`, and read the answer with the articles the search found.

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
│  embed_chunks()                   │  ← the 28 chunks embedded by Gemini (1 call)
│  make_vector_store()              │  ← Qdrant, in memory
│  store_vectors()                  │  ← 28 points, each chunk with its vector
│  make_rag_chain(make_retriever()) │  ← the chain: retriever, prompt, Gemini, parser
└────────────────┬──────────────────┘
                 │ query(question), for each question
                 ↓
┌───────────────────────────────────┐
│  chain.invoke(question)           │  ← the question's embedding and the answer (2 calls)
│  _with_sources()                  │  ← the first 3 different articles among the chunks the search found
└────────────────┬──────────────────┘
                 ↓
   {"answer": "...", "sources": [{"title", "system", "category", "snippet"}, ...]}
                 │
                 ↓
   print_result(), in utils.py: the question, the answer, then each article the search found
```

### The Pipeline in This Project

1. **Run** → `python pipeline.py`: `main()` builds the engine (Step 1), then answers each question (Step 2)
2. **Configure** → `RAGEngine()` stores the models, the Qdrant client, the data file, the collection and the
   sizes; it reads nothing
3. **Build** → `build()` loads and chunks the articles, embeds and stores the chunks, and makes the chain
4. **Ask** → `query(question)` runs the chain: the 5 closest chunks, then Gemini's answer from them
5. **List the sources** → the first 3 different articles among those chunks, closest first, each with the first 200
   characters of its chunk
6. **Print** → `print_result()`, from `utils.py`: the question, the answer, then each article the search found
7. **Report** → `stats()` gives what the engine holds and how it's set up

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

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs `python
pipeline.py` in this folder with the venv's Python, so there's nothing to activate. The project's output is the same
as in Step 5, after run.py's own lines saying what it creates, installs and runs. A question at the end of the command
goes to `pipeline.py`.

---

## 🧪 Testing

```bash
python -m pytest -m "not live"       # 44 passed, 8 deselected  (add -v for one line per test)
```

The plain tests use stand-ins for Gemini, so they need no key and make no calls. They check:

- **The engine**: nothing is read or called before `build()`; `build()` embeds the 28 chunks in one call; `query()`
  gives the answer and up to 3 different articles; other chunk sizes and numbers of chunks, another data file and
  another collection can be set, and engines in collections of their own keep their own chunks; building again
  starts with a new collection; `stats()` names the engine's own models; and every setting is passed by name
- **The printing**: what `print_result()` prints
- **The pipeline**: it builds the engine, then answers each question, or one of your own, after the steps' names;
  and no other file runs anything

The 8 deselected tests are live tests, marked `live`: they call the real Gemini, so they need your key in `.env`;
with no key, `tests/conftest.py` skips them, so plain `python -m pytest` runs only the others. Together they embed
more than 100 texts, the free tier's limit for a minute, so on the free tier, run them one file at a time, a minute
apart: `python -m pytest -m live tests/test_rag_engine.py`.

---

## 🎓 Key Concepts Demonstrated

### 1. Build Once, Answer Many Times

```python
engine = RAGEngine()          # settings only
engine.build()                # ingestion: load, chunk, embed and store, make the chain: once
engine.query("...")           # the query half, each question: retrieve, answer, then the sources
```

A RAG app has two halves. Ingestion, in `build()`, gets the knowledge base ready, once. The query half, in `query()`,
runs for each question: it only embeds the question, retrieves the closest chunks and asks for the answer.

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

### 3. Sources: the Articles the Search Found

Two of the 5 chunks found can come from one article. `_with_sources()` keeps the first chunk of each article, closest
first, and stops at 3, so every source names a different article. Gemini reads all 5 chunks; the list shows at most 3
articles; and it comes from the search, not from the answer, so it isn't a checked citation. The run shows the
difference:

```text
Sources: [1] VPN Connection Timeout, [2] VPN Connection Timeout
   found by the search: VPN Connection Timeout (VPN, Remote Access)
   found by the search: MFA Setup Failure (MFA, Security)
   found by the search: Database Connection Timeout (Database, Infrastructure)
```

The first line is the end of Gemini's answer: it says it used the VPN article's two chunks. The search also found
chunks of the MFA and Database articles, and they're listed because they were in the prompt, not because the answer
used them. The [1], [2] in an answer number the 5 chunks in the prompt (07 prints it), not the lines of this list.

### 4. One File Runs the Steps

`pipeline.py` is the only file that runs anything: `main()` builds the engine (Step 1, in one line, from `stats()`),
then answers each question (Step 2), and `print_result()`, from `utils.py`, prints each answer. With no question,
or only spaces, after `pipeline.py`, it answers the three sample questions. `rag_engine.py` and
the other files only define the parts, so importing them reads nothing and makes no call. The engine is a parameter
of `main()`, so the tests pass one with stand-ins for Gemini.

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
**Fix**: Your key has used its quota. On the free tier, that's 100 embedded texts a minute, and a run embeds 31; the
message ends with "Please retry in" and a number of seconds. Wait that long, then run it again.

**Issue**: `ModuleNotFoundError: No module named 'langchain_core'` (or another of the packages)
**Fix**: The venv isn't active, or the packages aren't installed in it. Activate it (Step 2), then
`pip install -r requirements-dev.txt` (Step 3).

**Issue**: `Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).`
**Fix**: There's no `.env` with a key in this folder. Do Step 4.

**Issue**: `Can't build the models: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Replace it with your key.

**Issue**: `Can't build the models: .env isn't saved as UTF-8 text. Open it in an editor and save it with UTF-8 encoding.`
**Fix**: `.env` was saved in another encoding, often UTF-16 by Windows PowerShell 5's `echo ... > .env`. Save it
again as UTF-8, or make it with `copy .env.example .env` and edit it.

**Issue**: `python rag_engine.py` prints nothing
**Fix**: That file only defines the engine. Run `python pipeline.py` (Step 5), which builds it and asks it.

---

## 💡 Ideas to Try

- Ask a question of your own with `python pipeline.py "..."`, and compare the articles the answer says it used with
  the ones the search found.
- Change `MAX_SOURCES` in `rag_engine.py` from 3 to 1, and see one source per answer. A test checks for up to 3, so
  put it back before you run the tests.
- In `pipeline.py`, build the engine with `RAGEngine(top_k=2)`, and compare its answers with the default 5 chunks.
