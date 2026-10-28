# 04 · Embeddings

Turn the IT knowledge base's 28 chunks into vectors with Gemini's embedding model, `gemini-embedding-001`: 768
numbers for each chunk, all in one call. Built with **LangChain** (`langchain-google-genai`) and **Gemini**.

In a RAG app, a search compares a question's vector with these vectors, so it can find the chunks closest in meaning
(semantic search), even when they use other words.

> **Needs:** Python 3.11 or newer, and a Gemini API key. Each run makes 1 call to Gemini, for all 28 chunks. On the
> free tier, each chunk counts as one request against a limit of 100 a minute, so a run uses 28.

---

## 🎯 What This Project Does

- **Reads** `data/sample_it_kb.csv` into 10 articles, and cuts them into 28 chunks of at most 512 characters
- **Checks your Gemini API key first**: without one, it stops with a message saying what to do
- **Builds Gemini's embedding model**, set to give 768 numbers per text
- **Embeds all 28 chunks in one call** with `embed_documents()`: only each chunk's text (`page_content`) is sent,
  not its labels (`metadata`)
- **Prints** how many vectors came back, then every chunk, one line each: its article, which characters it holds,
  and the first 5 of its 768 numbers
- **Prints how close chunk 1's vector is to every other chunk's**, closest first, as a cosine similarity worked out
  from the vectors themselves: no question, and no more calls to Gemini
- **All the code in one file**, `pipeline.py`: the loader, the splitter, the model, the embedding, and `main()`,
  which names each step, then runs it. Two files are apart: `config.py`, which checks the key, and `utils.py`, which
  prints the vectors

An embedding is a vector, a list of numbers that stands for a text's meaning: texts with close meanings get vectors
that point in close directions.

**Try it:** `python pipeline.py`, and see each chunk become 768 numbers, then how close chunk 1 is to all the others.

---

## 🏗️ Architecture

```text
┌──────────────────────────────────┐
│  pipeline.py: main()             │  ← the one file to run: it holds the steps below, and calls each in order
└────────────────┬─────────────────┘
                 │ Steps 1 and 2: Read the knowledge base, then chunk it
                 ↓
┌──────────────────────────────────┐
│  load_documents()                │  ← data/sample_it_kb.csv → 10 Documents, text + labels
│  split_documents()               │  ← 28 chunks of at most 512 characters
└────────────────┬─────────────────┘
                 │ 28 chunks; Step 3: Embed
                 ↓
┌──────────────────────────────────┐
│  embed_chunks(chunks, embeddings)│  ← one embed_documents() call, text only
│  └─ embeddings                   │     gemini-embedding-001, 768 numbers;
│                                  │     config.py checks the key before the model is built
└────────────────┬─────────────────┘
                 │ one call to Gemini
                 ↓
           28 vectors of 768 numbers, in the chunks' order
                 │
                 ↓
┌──────────────────────────────────┐
│  print_vectors(chunks, vectors)  │  ← utils.py: every chunk, with its vector's size and first 5 numbers;
│  └─ cosine()                     │     then how close chunk 1 is to every other chunk
└──────────────────────────────────┘
```

### The Pipeline in This Project

1. **Run** → `python pipeline.py`: `main()` runs each step in order, and prints each one's name
2. **Check the key** → `config.py` reads `GOOGLE_API_KEY` from `.env` or the environment, and stops if it's missing
3. **Build the model** → `pipeline.py` makes `GoogleGenerativeAIEmbeddings`, 768 numbers per text. No call yet
4. **Load and chunk** → `load_documents()` and `split_documents()` turn the CSV into 28 chunks
5. **Embed** → `embed_chunks()` sends the 28 chunks' texts to Gemini in one `embed_documents()` call
6. **Print** → `print_vectors()`, from `utils.py`: every chunk, with the characters it holds and the start of its
   vector, then how close chunk 1 is to each of the others

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
cd "projects/RAG/IT Knowledge Base/Basic/04-embeddings"   # from the repo root; quotes for the spaces
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

### Or: Run It in One Command

With your key in `.env` (Step 4), this one command does Steps 2, 3 and 5 for you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/04-embeddings   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs `python
pipeline.py` in this folder with the venv's Python, so there's nothing to activate. The project's output is the same
as in Step 5, after run.py's own lines saying what it creates, installs and runs.

---

## 🧪 Testing

```bash
python -m pytest -m "not live"       # 20 passed, 2 deselected  (add -v for one line per test)
```

The tests need no key and no network. Most of them use `tests/fakes.py`'s stand-in for Gemini, which turns each text
into a few numbers counted from its words, the same every time: 10 numbers count the words vpn, mfa, laptop and so
on, and one more is the text's length. It's the simplest picture of an embedding: texts that use the same words
point the same way. Gemini's 768 numbers do that for meaning, not just words. The tests check:

- **The pipeline**: its steps and what they print; it embeds the chunks in one call and never a question; and no
  other file runs anything
- **The embedding**: the 28 chunks go to the model in one call, one vector each; only the chunks' texts are sent, in
  the chunks' order; `cosine()` on vectors whose answer is known; and what `print_vectors()` prints, closeness too
- **The model**: its name and vector size; and without a key, `pipeline.py` stops with the message, not a stack trace
- **The chunks and the Documents**: 28 chunks of at most 512 characters, each with its article's labels; and
  10 Documents with their text and labels

The 2 deselected tests are live tests, marked `live`: they call the real Gemini, so they run only when a key is set,
in `.env` or the environment. `tests/conftest.py` decides this once, before any test runs: with no key, it gives the
model a fake one so it can be built, and skips the live tests, so plain `python -m pytest` runs only the others. With
your key, `python -m pytest -m live` runs both at once: together they embed 29 texts, under the free tier's limit of
100 a minute.

---

## 🎓 Key Concepts Demonstrated

### 1. An Embedding: a Text as a Direction

```python
embeddings.embed_documents(["Title: VPN Connection Timeout ...", ...])   # -> one list of 768 numbers per text
```

An embedding model reads a text and gives back a vector: a fixed number of numbers, whatever the text's length. The
numbers aren't readable one by one; together they point in a direction, and texts with close meanings point in close
directions. How close two directions are is their cosine similarity, which `cosine()` in `utils.py` works out: 1 for
the same direction, 0 at right angles. The run ends with chunk 1 against every other chunk:

```text
How close chunk 1 (VPN Connection Timeout) is to every other chunk, closest first
(cosine similarity: 1 is the same direction, 0 is at right angles):
  0.789  chunk 11: WiFi Connectivity Issues Office
  0.779  chunk 3: MFA Setup Failure
  0.778  chunk 12: WiFi Connectivity Issues Office
  0.777  chunk 23: Database Connection Timeout
  0.764  chunk 14: Password Reset Failed
  0.759  chunk 2: VPN Connection Timeout
  ...
```

The closest are other problems with connecting or signing in: WiFi, MFA, a database connection timeout and a password
reset. Chunk 2, the VPN article's own notes, is only 6th: it says "peak hours" and "ISP throttling", and never "VPN".
A vector stands for what its chunk's text says, not for the article it came from. All 27 score between 0.666 (chunk
19, the Printer article's notes) and 0.789 against chunk 1. What tells chunks apart is their order, not how big the
number is.

### 2. One Call for Every Chunk

`embed_chunks()` sends all 28 texts in a single `embed_documents()` call, and the vectors come back in the same
order: vector 1 belongs to chunk 1, and so on. One call for the list is faster and simpler than 28 calls. Gemini's
free tier still counts each text as one request, against a limit of 100 a minute, so a run uses 28 of them.

### 3. Only the Text Is Embedded

```python
embeddings.embed_documents([chunk.page_content for chunk in chunks])
```

The labels (`metadata`) stay with each chunk but aren't sent: the vector stands for what the chunk says.
`embed_documents()` also tells Gemini these texts are documents to be found (`RETRIEVAL_DOCUMENT`).

### 4. 768 Numbers

`gemini-embedding-001` can give 128 to 3072 numbers per text. `pipeline.py` asks for 768 (`EMBEDDING_SIZE`), one of
the sizes Google recommends: smaller vectors are cheaper to keep and to compare. Building the model makes no call to
Gemini; each `embed_...()` call does, and uses your key's quota.

### 5. The Key Is Checked First

`config.py`'s `load_api_key()` reads `GOOGLE_API_KEY` from the environment or from `.env`, and `pipeline.py` calls
it before building the model. A missing key, the placeholder from `.env.example`, or a `.env` that isn't UTF-8 stops
`pipeline.py` at once with a message saying what to do, rather than with a confusing error from the first call to
Gemini. A key set in the environment (a Codespaces secret, say) wins over the one in `.env`.

### 6. One File Runs the Steps

```python
def main(embeddings: Embeddings = embeddings) -> None:
    docs = load_documents()
    print(f"Step 1: Read the knowledge base: {len(docs)} documents")
    chunks = split_documents(docs)
    print(f"Step 2: Chunk: {len(chunks)} chunks of at most {CHUNK_SIZE} characters")
    print("Step 3: Embed")
    vectors = embed_chunks(chunks, embeddings)
    print_vectors(chunks, vectors, EMBEDDING_MODEL)
```

`pipeline.py` is the only file that runs anything: `main()` runs the steps in order, the earlier ones in a line each
and this project's own in full. `config.py` and `utils.py` only define what it uses, and building the model makes
no call, so importing any of them makes no call. The model is a parameter of `main()`, so the tests pass their
stand-in for Gemini.

### 7. The Code in One File, the Helpers Apart

```python
from config import MissingKeyError, load_api_key   # checks the key, before the model is built
from utils import print_vectors                    # a helper: showing the vectors
```

`pipeline.py` holds the project's code, top to bottom: the settings (the data file, the column lists, the chunk size
and overlap, the model's name and vector size), the loader, the splitter, the model, `embed_chunks()`, then
`main()`, which runs them. Two files stay apart. `utils.py` holds `cosine()` and `print_vectors()`, which show the
vectors; `main()` hands `print_vectors()` the model's name, so `utils.py` needs nothing from `pipeline.py`.
`config.py` holds the key check, because the tests need it before `pipeline.py` is imported: `tests/conftest.py`
asks it whether there's a real key, and gives the model a fake one when there isn't.

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
**Fix**: Your key has used its quota. On the free tier, that's 100 embedded texts a minute, and a run embeds 28; the
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

- In `pipeline.py`, print `len(vectors[0])` and `len(vectors[1])`, how many numbers each holds: both 768, though chunk
  1 is 457 characters and chunk 2 is 110. One test checks the pipeline's exact output, so take the print out before
  `python -m pytest`.
- In `pipeline.py`, change `EMBEDDING_SIZE` to `256`, run `python pipeline.py` again, and see each chunk converted to
  256 numbers. Tests check for 768, so put it back before `python -m pytest`.
- In `pipeline.py`'s `embed_chunks()`, put the article's title at the top of every chunk: embed
  `chunk.metadata["title"] + "\n\n" + chunk.page_content`. See whether chunk 2, the VPN article's notes, comes closer
  to chunk 1. Two tests expect the text alone, so put it back before `python -m pytest`.
