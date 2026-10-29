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
  in Qdrant, and makes the retriever
- **`query(question)`, for each question: the query half**: the answer, plus up to 3 sources: the first different
  articles among the chunks the search found, each with its title, system, category and the start of the chunk's
  text. They're what Gemini was given, not a checked list of what the answer used
- **`stats()`**: what the engine holds (10 articles, 28 chunks) and how it's set up, with its own models' names
- **All the code in one file**, `pipeline.py`: the parts, from the loader to the prompt, `RAGEngine`, and `main()`,
  which builds the engine, then answers the three sample questions, or the one you give it, naming each step first.
  Two files are apart: `config.py`, which checks the key, and `utils.py`, which prints each answer

**Try it:** `python pipeline.py "printer not found"`, and read the answer with the articles the search found.

---

## 🏗️ Architecture

```text
┌───────────────────────────────────┐
│  pipeline.py: main()              │  ← the one file to run: it holds the parts below; Step 1, build; Step 2, answer
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
│  make_retriever()                 │  ← the retriever, which finds the 5 closest chunks for a question
└────────────────┬──────────────────┘
                 │ query(question), for each question
                 ↓
┌───────────────────────────────────┐
│  retriever.invoke(question)       │  ← the question embedded (1 call), the 5 closest chunks: found
│  prompt.format_messages()         │  ← the 5 chunks and the question in one prompt: messages
│  (model | StrOutputParser())      │  ← Gemini's answer from those messages (1 call)
│      .invoke(messages)            │
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
3. **Build** → `build()` loads and chunks the articles, embeds and stores the chunks, and makes the retriever
4. **Ask** → `query(question)`: the retriever finds the 5 closest chunks, the prompt is filled in with them and the
   question, and Gemini answers from it
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
python -m pytest -m "not live"       # 42 passed, 8 deselected  (add -v for one line per test)
```

The plain tests use stand-ins for Gemini, so they need no key and make no calls. They check:

- **The engine**: nothing is read or called before `build()`; `build()` embeds the 28 chunks in one call; `query()`
  gives the answer and up to 3 different articles, and Gemini gets the chunks found as the articles; other chunk
  sizes and numbers of chunks, another data file and another collection can be set, and engines in collections of
  their own keep their own chunks; building again starts with a new collection; `stats()` names the engine's own
  models; and every setting is passed by name
- **The printing**: what `print_result()` prints
- **The pipeline**: it builds the engine, then answers each question, or one of your own, after the steps' names;
  and no other file runs anything

The 8 deselected tests are live tests, marked `live`: they call the real Gemini, so they need your key in `.env`;
with no key, `tests/conftest.py` skips them, so plain `python -m pytest` runs only the others. Together they embed
147 texts, more than the free tier's limit of 100 a minute, so on the free tier, run them in two goes, a minute
apart: `python -m pytest -m live -k answer` (the four that ask for an answer, 59 texts), then
`python -m pytest -m live -k "not answer"` (the other four, 88).

---

## 🎓 Key Concepts Demonstrated

### 1. Build Once, Answer Many Times

```python
engine = RAGEngine()          # settings only
engine.build()                # ingestion: load, chunk, embed and store, make the retriever: once
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
or only spaces, after `pipeline.py`, it answers the three sample questions. `config.py` and `utils.py` only define
what it uses, and building the models makes no call, so importing any of them reads nothing and makes no call. The
engine is a parameter of `main()`, so the tests pass one with stand-ins for Gemini.

### 5. The Code in One File, the Helpers Apart

```python
from config import MissingKeyError, load_api_key   # checks the key, before the models are built
from utils import print_result                     # a helper: showing each answer
```

`pipeline.py` holds the project's code, top to bottom: the settings (the data file, the column lists, the chunk size
and overlap, the two models' names and settings, the collection's name, `TOP_K`, the sample questions,
`MAX_SOURCES` and `SNIPPET_LENGTH`), the loader, the splitter, the two models, `embed_chunks()`, the vector store
(`make_vector_store()` and `store_vectors()`), the retriever (`make_retriever()` and `format_docs()`), the prompt,
`RAGEngine`, then `main()`, which runs it. `query()` works as 07's Step 5 does: the retriever finds the chunks
first, then the prompt is filled in with them, and Gemini answers. Two files stay apart. `utils.py` holds
`print_result()`, which prints the result `main()` hands it, so `utils.py` needs nothing from `pipeline.py`.
`config.py` holds the key check, because the tests need it before `pipeline.py` is imported: `tests/conftest.py`
asks it whether there's a real key, and gives the models a fake one when there isn't.

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

**Issue**: `python utils.py` or `python config.py` prints nothing
**Fix**: Those files only define what `pipeline.py` uses. Run `python pipeline.py` (Step 5), which builds the engine
and asks it.

---

## 💡 Ideas to Try

- Ask a question of your own with `python pipeline.py "..."`, and compare the articles the answer says it used with
  the ones the search found.
- Change `MAX_SOURCES` in `pipeline.py` from 3 to 1, and see one source per answer. A test checks for up to 3, so
  put it back before you run the tests.
- In `pipeline.py`, build the engine with `RAGEngine(top_k=2)`, and compare its answers with the default 5 chunks.
