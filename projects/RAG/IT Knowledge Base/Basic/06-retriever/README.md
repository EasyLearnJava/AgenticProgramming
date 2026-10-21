# 06 · Retriever

Take a question and find the chunks of the IT knowledge base that answer it: the question becomes a vector, made by
the same model as the chunks', and Qdrant gives back the 5 closest chunks, with their scores. Then a LangChain
retriever does both in one call. Built with **LangChain**, **Qdrant** (in memory) and **Gemini**.

> **Needs:** Python 3.11 or newer, and a Gemini API key. No Docker: Qdrant runs inside the script. Each run makes 3
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

**Try it:** `python retriever.py "my email bounced"`, and see which chunks come back for your question.

---

## 🏗️ Architecture

```text
data/sample_it_kb.csv  →  10 articles  →  28 chunks
                                              │
                                              ↓
┌──────────────────────────────────────────────────┐
│  make_vector_store(embeddings, 768)              │  ← vector_store.py: Qdrant in memory, cosine
│  add_knowledge_base(store)                       │     the 28 chunks embedded and stored (call 1)
└────────────────────────┬─────────────────────────┘
                         │
a question ──────────────┤
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

1. **Store** → the 28 chunks embedded in one call and stored in an in-memory Qdrant collection
2. **Embed the question** → `embed_query()`: 768 numbers, from the same model
3. **Search** → Qdrant compares the question's vector with every stored one and keeps the 5 closest, with scores
4. **Retrieve** → `make_retriever(store).invoke(question)` does steps 2 and 3 in one call
5. **Format** → `format_docs()` joins chunks into one numbered, titled text
6. **Print** → each step's result

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
python retriever.py
```

It prints each step: the question's vector, the 5 closest chunks with their scores, the same 5 found by the retriever
in one call, and the text a prompt would get. The parts in `< >` come from Gemini:

```text
Question: How do I fix VPN connection timeouts?
The question became 768 numbers: [<the first 5 numbers>, ...]

The 5 closest chunks, with their scores, closest first:
  <score>  <article title>, from character <start_index>
  ...

The retriever, embedding and searching in one call, found:
  <article title>, from character <start_index>
  ...

What a prompt gets, the 2 closest chunks as one text (format_docs):
[1] <article title>
<the chunk's text>

[2] <article title>
<the chunk's text>
```

The `...` lines stand for the other 4 chunks: your terminal shows all 5.

To ask your own question, put it after the script's name:

```bash
python retriever.py "my email bounced"
```

---

## 📁 Project Structure

```text
06-retriever/
├── retriever.py                          # make_retriever(), format_docs(), and the lines that show each step
├── vector_store.py                       # make_vector_store(), add_knowledge_base(): Qdrant in memory
├── models.py                             # the embedding model: gemini-embedding-001, 768 numbers
├── config.py                             # load_api_key(): the key, checked before anything else runs
├── chunking.py                           # split_documents(): the 28 chunks of at most 512 characters
├── knowledge_base.py                     # load_documents(): the 10 articles, text + labels
├── data/
│   └── sample_it_kb.csv                  # the knowledge base: 10 IT support articles
├── tests/
│   ├── conftest.py                       # decides once whether the live tests can run
│   ├── fakes.py                          # stand-ins for Gemini: no key, no network
│   ├── test_retriever.py                 # the search, the retriever, format_docs(), the script
│   ├── test_vector_store.py              # the collection and the stored points
│   ├── test_models.py                    # the model's settings, and the no-key message
│   ├── test_chunking.py                  # the chunks
│   └── test_knowledge_base.py            # the Documents
├── .env.example                          # copy it to .env and put your key in .env
├── requirements.txt                      # the packages, pinned to exact versions
├── requirements-dev.txt                  # requirements.txt plus pytest, for the tests
├── pytest.ini                            # lets the tests import the scripts, and finds them in tests/
└── README.md                             # you are here
```

`python vector_store.py` also runs on its own: it stores the 28 chunks and prints the collection and every point
(one call to Gemini).

---

## 🧪 Testing

```bash
python -m pytest                     # 28 passed, 3 skipped     (add -v for one line per test)
```

The tests need no key and no network. Most of them use `tests/fakes.py`'s stand-in for Gemini, which turns each text
into numbers counted from a few keywords (`vpn`, `mfa`, `printer` and others), so a short question about the VPN
points closest to the VPN chunks, the same every time. They check:

- **The retriever**: searching with the question's vector gives the closest chunks and their scores; `invoke()`
  gives the k closest, closest first, the same chunks as the search by hand; `k` sets how many come back; `batch()`
  answers several questions in order, with one query call each; `format_docs()` numbers and titles each chunk; and
  the script embeds the chunks, then the question by hand, then through the retriever
- **The store, the model, the chunks and the Documents**: 28 points with their vectors, text and labels, stored in
  one embedding call; the model's settings and the no-key message; 28 chunks; 10 Documents

The 3 skipped tests are live tests: they call the real Gemini, so they run only when a key is set, in `.env` or the
environment. `tests/conftest.py` decides this once, before any test runs: with no key, it gives the model a fake one
so it can be built, and skips the live tests.

---

## 📊 Understanding the Output

```text
The 5 closest chunks, with their scores, closest first:
  <score>  <article title>, from character <start_index>
```

Each line is one chunk: its score, its article, and where in the article it starts. The score is the cosine
similarity between the question's vector and the chunk's: how closely the two point the same way, from -1 to 1. The
closer to 1, the closer the meaning. The scores matter by their order: the chunk with the highest one is the closest.

The retriever finds the same 5 chunks as the search by hand: it does the same two steps, embed and search, in one
call. It gives back the chunks without their scores.

```text
[1] <article title>
<the chunk's text>
```

`format_docs()` puts a number and the article's title above each chunk, and a blank line between them, so whatever
reads the text can tell which article each part came from.

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

---

## 📚 Next Steps

**[07 · Grounded Answer](../07-grounded-answer/README.md)**: this project found the chunks for a question. 07 puts
them and the question into one prompt, and Gemini answers from those chunks only.

**[Advanced · 06 · Retriever](../../Advanced/06-retriever/README.md)** (planned): the same project, production grade.
Its README lists what it will add.

### Ideas to Try

- Ask a question in your own words, with none of the articles' words in it: `python retriever.py "my screen freezes all the time"`.
- In `retriever.py`, change `TOP_K` to `2`, and see 2 chunks come back instead of 5.
- Ask something the knowledge base doesn't cover, `python retriever.py "how do I bake bread"`, and look at the
  scores: 5 chunks still come back, as a search always returns the closest ones.
