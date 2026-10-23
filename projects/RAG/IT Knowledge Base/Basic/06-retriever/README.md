# 06 · Retriever

Take a question and find the chunks of the IT knowledge base that answer it: the question becomes a vector, made by
the same model as the chunks', and Qdrant gives back the 5 closest chunks, with their scores. Then a LangChain
retriever does both in one call. Built with **LangChain**, **Qdrant** (in memory) and **Gemini**.

> **Needs:** Python 3.11 or newer, and a Gemini API key. Qdrant runs inside the script. Each run makes 3
> calls to Gemini.

---

## 🎯 What This Project Does

- **Stores the knowledge base** in Qdrant, in memory: the 28 chunks of the 10 articles, embedded in one call
- **Embeds the question** with `embed_query()`: 768 numbers, made by the same model as the chunks, so the two can be
  compared. It tells Gemini this text is a question looking for documents (`RETRIEVAL_QUERY`)
- **Searches**: Qdrant compares the question's vector with the 28 stored vectors and gives back the 5 closest chunks,
  each with a score, the cosine similarity: from -1 to 1, the closer to 1, the closer the meaning
- **Does both in one call** with a retriever: `make_retriever(store).invoke(question)` embeds the question and
  searches, and returns the 5 chunks
- **Joins chunks into one text** with `format_docs()`: each chunk numbered and titled, ready to go into a prompt
- **Prints** each step for one question, `How do I fix VPN connection timeouts?`, or for yours
- **Runs from one file**, `pipeline.py`, which names each step, then runs it

**Try it:** `python pipeline.py "my email bounced"`, and see which chunks come back for your question.

---

## 🏗️ Architecture

```text
pipeline.py: main(), the one file to run, calls each step in order:
data/sample_it_kb.csv  →  10 articles  →  28 chunks         ← Steps 1 and 2: read, then chunk
                                              │ Step 3: Embed and store
                                              ↓
┌──────────────────────────────────────────────────┐
│  make_vector_store(embeddings, 768)              │  ← vector_store.py: Qdrant in memory, cosine
│  store.add_documents(chunks)                     │     the 28 chunks embedded and stored (call 1)
└────────────────────────┬─────────────────────────┘
                         │
a question ──────────────┤ Step 4: Retrieve
                         ↓
┌──────────────────────────────────────────────────┐
│  embeddings.embed_query(question)                │  ← 768 numbers for the question (call 2)
│  store.similarity_search_with_score_by_vector()  │  ← the 5 closest chunks, with their scores
└────────────────────────┬─────────────────────────┘
                         │ the same two steps, in one call:
                         ↓
┌──────────────────────────────────────────────────┐
│  make_retriever(store).invoke(question)          │  ← retriever.py: the 5 closest chunks (call 3)
│  format_docs(chunks)                             │  ← one text: [1] title + chunk, [2] title + chunk ...
└──────────────────────────────────────────────────┘
```

### The Pipeline in This Project

1. **Run** → `python pipeline.py`: `main()` runs each step in order, and prints each one's name
2. **Store** → the 28 chunks embedded in one call and stored in an in-memory Qdrant collection
3. **Embed the question** → `embed_query()`: 768 numbers, from the same model
4. **Search** → Qdrant compares the question's vector with every stored one and keeps the 5 closest, with scores
5. **Retrieve** → `make_retriever(store).invoke(question)` does steps 3 and 4 in one call
6. **Format** → `format_docs()` joins chunks into one numbered, titled text
7. **Print** → `print_retrieval()`, from `utils.py`: each step's result

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**, made in the Google Cloud console, under APIs & Services > Credentials. Every call to Gemini
  uses your key's quota
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

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs
`python pipeline.py` in this folder with the venv's Python, so there's nothing to activate. The output is the same as
in Step 5. A question at the end of the command goes to `pipeline.py`: `... Basic/06-retriever "my email bounced"`.

---

## 🧪 Testing

```bash
python -m pytest                     # 27 passed, 3 skipped     (add -v for one line per test)
```

The tests need no key and no network. Most of them use `tests/fakes.py`'s stand-in for Gemini, which turns each text
into numbers counted from a few keywords (`vpn`, `mfa`, `printer` and others), so a short question about the VPN
points closest to the VPN chunks, the same every time. They check:

- **The retriever**: searching with the question's vector gives the closest chunks and their scores; `invoke()`
  gives the k closest, closest first, the same chunks as the search by hand; `k` sets how many come back; `batch()`
  answers several questions in order, with one query call each; `format_docs()` numbers and titles each chunk; and
  what `print_retrieval()` prints
- **The pipeline**: it embeds the chunks, then the question by hand, then through the retriever; it takes a question
  of your own; and no other file runs anything
- **The store, the model, the chunks and the Documents**: 28 points with their vectors, text and labels, stored in
  one embedding call; the model's settings and the no-key message; 28 chunks; 10 Documents

The 3 skipped tests are live tests: they call the real Gemini, so they run only when a key is set, in `.env` or the
environment. `tests/conftest.py` decides this once, before any test runs: with no key, it gives the model a fake one
so it can be built, and skips the live tests.

---

## 🎓 Key Concepts Demonstrated

### 1. Documents and Questions Are Embedded Differently

```python
embeddings.embed_documents([...])    # the chunks: texts to be found (RETRIEVAL_DOCUMENT)
embeddings.embed_query(question)     # the question: a text looking for them (RETRIEVAL_QUERY)
```

Both give 768 numbers from the same model, so they can be compared. Gemini embeds the two kinds a little
differently, so that a question lands near the chunks that answer it, not just near texts that look like it.

### 2. Similarity Search

```python
store.similarity_search_with_score_by_vector(question_vector, k=5)   # -> [(chunk, score), ...], closest first
```

Qdrant compares the question's vector with every stored vector, by cosine, and keeps the `k` closest. `TOP_K` in
`retriever.py` sets `k`: 5.

### 3. The Retriever: Embed and Search in One Call

```python
retriever = make_retriever(store)                  # store.as_retriever(search_kwargs={"k": 5})
chunks = retriever.invoke("How do I fix VPN connection timeouts?")
```

A retriever is LangChain's standard way to say "give me the chunks for this question". It's a Runnable, like LangChain's
prompts and models: `invoke()` takes one question, `batch()` takes several, and it can be joined to other Runnables
with `|`.

### 4. One Text for a Prompt

```python
format_docs(chunks[:2])   # -> "[1] <title>\n<chunk text>\n\n[2] <title>\n<chunk text>"
```

A prompt takes text, not Documents. `format_docs()` joins the chunks into one text, each with a number and its
article's title, so the source of every part stays visible.

### 5. One File Runs the Steps

`pipeline.py` is the only file that runs anything: `main()` runs Steps 1 to 3, printing a line each, then Step 4,
the search by hand and with the retriever, and `print_retrieval()`, from `utils.py`, prints it. The other files
only define the steps and that helper, so importing them makes no call. The question, the model and its vector size
are parameters of `main()`, so the tests pass a stand-in for Gemini.

---

## 🛠️ Troubleshooting

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

**Issue**: `python retriever.py` prints nothing
**Fix**: That file only defines the step. Run `python pipeline.py` (Step 5), which runs every step.

---

## 💡 Ideas to Try

- Ask a question in your own words, with none of the articles' words in it:
  `python pipeline.py "my screen freezes all the time"`.
- In `retriever.py`, change `TOP_K` to `2`, and see 2 chunks come back instead of 5.
- Ask something the knowledge base doesn't cover, `python pipeline.py "how do I bake bread"`, and look at the
  scores: 5 chunks still come back, as a search always returns the closest ones.
