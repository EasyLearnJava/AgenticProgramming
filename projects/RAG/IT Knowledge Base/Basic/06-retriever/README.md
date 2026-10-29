# 06 · Retriever

Take a question and find the chunks of the IT knowledge base that answer it, with a LangChain retriever: in one call,
the question becomes a vector, made by the same model as the chunks', and Qdrant gives back the 5 closest chunks.
Built with **LangChain**, **Qdrant** (in memory) and **Gemini**.

In a RAG app, the chunks a search finds are all the model gets to read, so an answer can only be as good as they are.

> **Needs:** Python 3.11 or newer, and a Gemini API key. Qdrant runs inside the script. Each run makes 2
> calls to Gemini, which embed 29 texts: the 28 chunks, and the question.

---

## 🎯 What This Project Does

- **Stores the knowledge base** in Qdrant, in memory: the 28 chunks of the 10 articles, embedded in one call, then
  stored with their vectors
- **Finds the closest chunks with a retriever**, in one call: `make_retriever(store).invoke(question)`
- **Embeds the question** inside that call, with `embed_query()`: 768 numbers, made by the same model as the chunks,
  so the two can be compared. It tells Gemini this text is a question looking for documents (`RETRIEVAL_QUERY`)
- **Searches** inside that call too: Qdrant compares the question's vector with the 28 stored vectors, by cosine
  similarity, and gives back the 5 closest chunks, closest first
- **Joins chunks into one text** with `format_docs()`: each chunk numbered and titled, ready to go into a prompt
- **Prints** each step for one question, `How do I fix VPN connection timeouts?`, or for yours
- **All the code in one file**, `pipeline.py`: the loader, the splitter, the model, the embedding, the vector store,
  the retriever, and `main()`, which names each step, then runs it. Two files are apart: `config.py`, which checks
  the key, and `utils.py`, which prints the search

**Try it:** `python pipeline.py "my email bounced"`, and see which chunks come back for your question.

---

## 🏗️ Architecture

```text
pipeline.py: main(), the one file to run: it holds the steps below, and calls each in order:
data/sample_it_kb.csv  →  10 articles  →  28 chunks         ← Steps 1 and 2: read, then chunk
                                              │ Steps 3 and 4: Embed, then store
                                              ↓
┌──────────────────────────────────────────────────┐
│  embed_chunks(chunks, embeddings)                │  ← the 28 chunks embedded (call 1)
│  make_vector_store(embeddings, 768)              │  ← Qdrant in memory, cosine
│  store_vectors(store, chunks, vectors)           │     28 points, each chunk with its vector
└────────────────────────┬─────────────────────────┘
                         │
a question ──────────────┤ Step 5: Retrieve
                         ↓
┌──────────────────────────────────────────────────┐
│  make_retriever(store).invoke(question)          │  ← the question embedded (call 2), then the 5 closest chunks
│  format_docs(chunks)                             │  ← one text: [1] title + chunk, [2] title + chunk ...
└──────────────────────────────────────────────────┘
```

### The Pipeline in This Project

1. **Run** → `python pipeline.py`: `main()` runs each step in order, and prints each one's name
2. **Embed and store** → `embed_chunks()` embeds the 28 chunks in one call, and `store_vectors()` stores them with
   their vectors in an in-memory Qdrant collection
3. **Retrieve** → `make_retriever(store).invoke(question)`, in one call: `embed_query()` turns the question into 768
   numbers, from the same model, then Qdrant compares them with every stored vector and keeps the 5 closest
4. **Format** → `format_docs()` joins chunks into one numbered, titled text
5. **Print** → `print_retrieval()`, from `utils.py`: the question, the 5 chunks, and the first 2 as one text

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**, made in the Google Cloud console, under APIs & Services > Credentials. There, under API
  restrictions, restrict it to the Gemini API (the Generative Language API; not Gemini for Google Cloud API, a
  different service), so a leaked key can't be used for anything else. Every call to Gemini uses your key's quota
- A network connection, to reach Gemini

---

## 🚀 Quick Start

### Step 1: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Basic/06-retriever"   # from the repo root; quotes for the spaces
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

Open `.env` in an editor and put your key after `GOOGLE_API_KEY=`. `.env` is in `.gitignore`, so your key never goes
into git: never commit it, and never put a real key in `.env.example`.

### Step 5: Run It

```bash
python pipeline.py
```

To ask your own question, put it after `pipeline.py`:

```bash
python pipeline.py "my email bounced"
```

### Or: Run It in One Command

With your key in `.env` (Step 4), this one command does Steps 2, 3 and 5 for you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/06-retriever   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs `python
pipeline.py` in this folder with the venv's Python, so there's nothing to activate. The project's output is the same
as in Step 5, after run.py's own lines saying what it creates, installs and runs. A question at the end of the command
goes to `pipeline.py`: `... Basic/06-retriever "my email bounced"`.

---

## 🧪 Testing

```bash
python -m pytest -m "not live"       # 30 passed, 4 deselected  (add -v for one line per test)
```

The tests need no key and no network. Most of them use `tests/fakes.py`'s stand-in for Gemini, which turns each text
into numbers counted from a few keywords (`vpn`, `mfa`, `printer` and others), so a short question about the VPN
points closest to the VPN chunks, the same every time. They check:

- **The retriever**: `invoke()` gives the k closest chunks, closest first, the same chunks as a search with the
  question's vector; `k` sets how many come back; `batch()` answers several questions in order, with one query call
  each; `format_docs()` numbers and titles each chunk; and what `print_retrieval()` prints
- **The pipeline**: it embeds the chunks, then the question once, through the retriever; it takes a question of your
  own; and no other file runs anything
- **The embeddings, the store, the model, the chunks and the Documents**: the 28 chunks embedded in one call, one
  vector each; 28 points with their vectors, text and labels, stored with no call to the model, and read back as the
  chunks; a chunk without a vector stops the store; the model's settings and the no-key message; 28 chunks; 10
  Documents

The 4 deselected tests are live tests, marked `live`: they call the real Gemini, so they need your key in `.env`;
with no key, `tests/conftest.py` skips them, so plain `python -m pytest` runs only the others. Together they embed 88
texts, under the free tier's limit of 100 a minute, so `python -m pytest -m live` runs them all at once; on the free
tier, wait a minute after a run first.

---

## 🎓 Key Concepts Demonstrated

### 1. Documents and Questions Are Embedded Differently

```python
embeddings.embed_documents([...])    # the chunks: texts to be found (RETRIEVAL_DOCUMENT)
embeddings.embed_query(question)     # the question: a text looking for them (RETRIEVAL_QUERY)
```

Both give 768 numbers from the same model, so they can be compared. Gemini embeds the two kinds a little
differently, so that a question lands near the chunks that answer it, not just near texts that look like it.
The retriever calls `embed_query()` for you, inside `invoke()`.

### 2. Similarity Search

```python
found = make_retriever(store).invoke(question)   # -> [chunk, ...]: the 5 closest, closest first
```

Inside `invoke()`, Qdrant compares the question's vector with every stored vector, by cosine, and keeps the `k`
closest. `TOP_K` in `pipeline.py` sets `k`: 5. For the VPN question, the run prints:

```text
The 5 closest chunks the retriever found, closest first:
  VPN Connection Timeout, from character 0
  VPN Connection Timeout, from character 459
  MFA Setup Failure, from character 146
  Database Connection Timeout, from character 0
  WiFi Connectivity Issues Office, from character 122
```

The VPN article's first chunk, its title, problem and fix, comes first, then the rest of the same article.

### 3. How Close Is Measured

Qdrant scores each chunk with the cosine similarity between the question's vector and the chunk's: how closely the
two point the same way, from -1 to 1. **1.0** means the same direction; **0** is at right angles. The retriever
ranks the chunks by it, then gives back only the chunks, not the scores.

```text
cosine(a, b) = (a₁×b₁ + a₂×b₂ + … + a₇₆₈×b₇₆₈) / (length of a × length of b)
```

**A search always returns `k` chunks**, even when none of them answers the question. For
`python pipeline.py "how do I bake bread"`:

```text
The 5 closest chunks the retriever found, closest first:
  Database Connection Timeout, from character 585
  Password Reset Failed, from character 130
  VPN Connection Timeout, from character 459
  Printer Not Found, from character 517
  SaaS Access Permission Denied, from character 575
```

Five chunks again, about nothing to do with bread. Their scores are lower (in one run, bread's closest chunk scored
0.511, against 0.775 for the VPN question's), but with this model even unrelated texts score well above 0. Nothing
here says "no match"; a minimum score would have to be chosen, below which a chunk isn't kept.

### 4. The Retriever: Embed and Search in One Call

```python
retriever = make_retriever(store)                  # store.as_retriever(search_kwargs={"k": 5})
chunks = retriever.invoke("How do I fix VPN connection timeouts?")
```

A retriever is LangChain's standard way to say "give me the chunks for this question". It's a Runnable, like
LangChain's prompts and models: `invoke()` takes one question, `batch()` takes several, and it can be joined to other
Runnables with `|`.

### 5. One Text for a Prompt

```python
format_docs(chunks)   # -> "[1] <title>\n<chunk text>\n\n[2] <title>\n<chunk text>\n\n..."
```

A prompt takes text, not Documents. `format_docs()` joins the chunks into one text, each with a number and its
article's title, so the source of every part stays visible. A prompt gets all 5; the run prints the first 2 as a
sample.

### 6. One File Runs the Steps

`pipeline.py` is the only file that runs anything: `main()` runs Steps 1 to 4, printing a line each, then Step 5,
the search with the retriever, and `print_retrieval()`, from `utils.py`, prints it. `config.py` and `utils.py` only
define what it uses, and building the model makes no call, so importing any of them makes no call. The question, the
model and its vector size are parameters of `main()`, so the tests pass a stand-in for Gemini.

### 7. The Code in One File, the Helpers Apart

```python
from config import MissingKeyError, load_api_key   # checks the key, before the model is built
from utils import print_retrieval                  # a helper: showing the search
```

`pipeline.py` holds the project's code, top to bottom: the settings (the data file, the column lists, the chunk size
and overlap, the model's name and vector size, the collection's name, `TOP_K` and the sample questions), the loader,
the splitter, the model, `embed_chunks()`, the vector store (`make_vector_store()` and `store_vectors()`), the
retriever (`make_retriever()` and `format_docs()`), then `main()`, which runs them. Two files stay apart. `utils.py`
holds `print_retrieval()`, which shows the search; `main()` hands it the sample of the prompt, already joined by
`format_docs()`, so `utils.py` needs nothing from `pipeline.py`. `config.py` holds the key check, because the tests
need it before `pipeline.py` is imported: `tests/conftest.py` asks it whether there's a real key, and gives the model
a fake one when there isn't.

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
**Fix**: Your key has used its quota. On the free tier, that's 100 embedded texts a minute, and a run embeds 29; the
message ends with "Please retry in" and a number of seconds. Wait that long, then run it again.

**Issue**: `Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).`
**Fix**: There's no `.env` in this folder, and no `GOOGLE_API_KEY` in the environment. Do Step 4.

**Issue**: `Can't build the models: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Put your real key after `GOOGLE_API_KEY=`.

**Issue**: `Can't build the models: .env isn't saved as UTF-8 text. Open it in an editor and save it with UTF-8 encoding.`
**Fix**: `.env` was saved in another encoding, often UTF-16 by Windows PowerShell 5's `echo ... > .env`. Save it
again as UTF-8, or make it with `copy .env.example .env` and edit it.

**Issue**: `ModuleNotFoundError: No module named 'langchain_core'` (or another of the packages)
**Fix**: The venv isn't active, or the packages aren't installed in it. Activate it (Step 2), then
`pip install -r requirements-dev.txt` (Step 3).

**Issue**: `python utils.py` or `python config.py` prints nothing
**Fix**: Those files only define what `pipeline.py` uses. Run `python pipeline.py` (Step 5), which runs every step.

---

## 💡 Ideas to Try

- Try a near-miss: `python pipeline.py "my screen freezes all the time"`. No article is about a frozen screen, but
  the Laptop article's problem says "applications freezing frequently" and the MFA article mentions Screen Time:
  which one comes first?
- In `pipeline.py`, change `TOP_K` to `2`, and see 2 chunks come back instead of 5. Tests check for 5, so put it
  back before `python -m pytest`.
- Try a minimum score: in `make_retriever()`, comment out the first `return` and uncomment the
  `similarity_score_threshold` one (0.8, a cosine of 0.6 or more). Then ask `"how do I bake bread"` and the VPN
  question: how many chunks does each get now? Tests check for 5, so put it back before `python -m pytest`.
