# 04 · Embeddings

Turn the IT knowledge base's 28 chunks into vectors with Gemini's embedding model, `gemini-embedding-001`: 768
numbers for each chunk, all in one call. Built with **LangChain** (`langchain-google-genai`) and **Gemini**.

> **Needs:** Python 3.11 or newer, and a Gemini API key. Each run makes 1 call to Gemini, for all 28 chunks.

---

## 🎯 What This Project Does

- **Reads** `data/sample_it_kb.csv` into 10 articles, and cuts them into 28 chunks of at most 512 characters
- **Checks your Gemini API key first**: without one, it stops with a message saying what to do
- **Builds Gemini's embedding model**, set to give 768 numbers per text
- **Embeds all 28 chunks in one call** with `embed_documents()`: only each chunk's text (`page_content`) is sent,
  not its labels (`metadata`)
- **Prints** how many vectors came back, then every chunk, one line each: its article, which characters it holds,
  and the first 5 of its 768 numbers

An embedding is a vector, a list of numbers that stands for a text's meaning: texts with close meanings get vectors
that point in close directions.

**Try it:** `python embed_chunks.py`, and see each chunk become 768 numbers.

---

## 🏗️ Architecture

```text
data/sample_it_kb.csv                       10 rows × 8 columns
          │
          ↓
┌──────────────────────────────────┐
│  load_documents()                │  ← knowledge_base.py: 10 Documents, text + labels
│  split_documents()               │  ← chunking.py: 28 chunks of at most 512 characters
└────────────────┬─────────────────┘
                 │ 28 chunks
                 ↓
┌──────────────────────────────────┐
│  embed_chunks(chunks, embeddings)│  ← embed_chunks.py: one embed_documents() call, text only
│  └─ embeddings                   │     models.py: gemini-embedding-001, 768 numbers;
│                                  │     config.py checks the key before the model is built
└────────────────┬─────────────────┘
                 │ one call to Gemini
                 ↓
           28 vectors of 768 numbers, in the chunks' order
                 │
                 ↓
┌──────────────────────────────────┐
│  python embed_chunks.py          │  ← every chunk, with its vector's size and first 5 numbers
└──────────────────────────────────┘
```

### The Pipeline in This Project

1. **Check the key** → `config.py` reads `GOOGLE_API_KEY` from `.env` or the environment, and stops if it's missing
2. **Build the model** → `models.py` makes `GoogleGenerativeAIEmbeddings`, 768 numbers per text. No call yet
3. **Load and chunk** → `knowledge_base.py` and `chunking.py` turn the CSV into 28 chunks
4. **Embed** → `embed_chunks()` sends the 28 chunks' texts to Gemini in one `embed_documents()` call
5. **Print** → every chunk, with the characters it holds and the start of its vector

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
python embed_chunks.py
```

It prints how many vectors came back, then every chunk, one line each: its article, which characters of the
article's text it holds, how many numbers it was converted to, and the first 5 of them. The numbers in `< >` come
from Gemini:

```text
28 chunks -> 28 vectors (gemini-embedding-001)

Chunk 1 of 28: VPN Connection Timeout, from character 0 to 457 -> converted to 768 numbers: [<the first 5 numbers>, ...]
Chunk 2 of 28: VPN Connection Timeout, from character 459 to 569 -> converted to 768 numbers: [<the first 5 numbers>, ...]
Chunk 3 of 28: MFA Setup Failure, from character 0 to 144 -> converted to 768 numbers: [<the first 5 numbers>, ...]
...
Chunk 28 of 28: Microsoft Teams Audio Issues, from character 581 to 699 -> converted to 768 numbers: [<the first 5 numbers>, ...]
```

The `...` stands for chunks 4 to 27: your terminal shows all 28.

### Or: Run It in One Command

With your key in `.env` (Step 4), this one command does Steps 2, 3 and 5 for you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/04-embeddings   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs
`python embed_chunks.py` in this folder with the venv's Python, so there's nothing to activate. The output is the same
as in Step 5.

---

## 📁 Project Structure

```text
04-embeddings/
├── embed_chunks.py                       # embed_chunks(), and the lines that print every chunk's vector
├── models.py                             # the embedding model: gemini-embedding-001, 768 numbers
├── config.py                             # load_api_key(): the key, checked before anything else runs
├── chunking.py                           # split_documents(): the 28 chunks of at most 512 characters
├── knowledge_base.py                     # load_documents(): the 10 articles, text + labels
├── data/
│   └── sample_it_kb.csv                  # the knowledge base: 10 IT support articles
├── tests/
│   ├── conftest.py                       # decides once whether the live tests can run
│   ├── fakes.py                          # stand-ins for Gemini: no key, no network
│   ├── test_embed_chunks.py              # the call to Gemini, what's sent, the script
│   ├── test_models.py                    # the model's settings, and the no-key message
│   ├── test_chunking.py                  # the chunks
│   └── test_knowledge_base.py            # the Documents
├── .env.example                          # copy it to .env and put your key in .env
├── requirements.txt                      # the packages, pinned to exact versions
├── requirements-dev.txt                  # requirements.txt plus pytest, for the tests
├── pytest.ini                            # lets the tests import the scripts, and finds them in tests/
└── README.md                             # you are here
```

`python chunking.py` and `python knowledge_base.py` also run on their own, with no key: they print the chunks and
the articles.

---

## 🧪 Testing

```bash
python -m pytest                     # 18 passed, 2 skipped     (add -v for one line per test)
```

The tests need no key and no network. Most of them use `tests/fakes.py`'s stand-in for Gemini, which turns each text
into a few numbers counted from its words, the same every time. They check:

- **The embedding**: the 28 chunks go to the model in one call, one vector each; only the chunks' texts are sent, in
  the chunks' order; and the script embeds the chunks and never a question
- **The model**: its name and vector size; and without a key, each script stops with the message, not a stack trace
- **The chunks and the Documents**: 28 chunks of at most 512 characters, each with its article's labels; 10
  Documents with their text and labels; and what `chunking.py` and `knowledge_base.py` print on their own

The 2 skipped tests are live tests: they call the real Gemini, so they run only when a key is set, in `.env` or the
environment. `tests/conftest.py` decides this once, before any test runs: with no key, it gives the model a fake one
so it can be built, and skips the live tests.

---

## 📊 Understanding the Output

```text
Chunk 1 of 28: VPN Connection Timeout, from character 0 to 457 -> converted to 768 numbers: [<the first 5 numbers>, ...]
```

`from character 0 to 457` is the part of the article's text the chunk holds: it starts at character 0 and ends just
before character 457, so it's 457 characters long. Chunk 2 holds characters 459 to 569, 110 characters: the blank
line between them (characters 457 and 458) is in neither chunk. Every chunk, short or long, is converted to the same
768 numbers.

On their own, the numbers don't tell you anything: what matters is how close two vectors point. Two chunks about the
same problem get vectors pointing in close directions; two chunks about different things don't.

---

## 🎓 Key Concepts Demonstrated

### 1. An Embedding: a Text as a Direction

```python
embeddings.embed_documents(["Title: VPN Connection Timeout ...", ...])   # -> one list of 768 numbers per text
```

An embedding model reads a text and gives back a vector: a fixed number of numbers, whatever the text's length. The
numbers aren't readable one by one; together they point in a direction, and texts with close meanings point in close
directions.

### 2. One Call for Every Chunk

`embed_chunks()` sends all 28 texts in a single `embed_documents()` call, and the vectors come back in the same
order: vector 1 belongs to chunk 1, and so on. One call for the list is faster and simpler than 28 calls.

### 3. Only the Text Is Embedded

```python
embeddings.embed_documents([chunk.page_content for chunk in chunks])
```

The labels (`metadata`) stay with each chunk but aren't sent: the vector stands for what the chunk says. `embed_documents()`
also tells Gemini these texts are documents to be found (`RETRIEVAL_DOCUMENT`).

### 4. 768 Numbers

`gemini-embedding-001` can give 128 to 3072 numbers per text. `models.py` asks for 768 (`EMBEDDING_SIZE`), one of the
sizes Google recommends: smaller vectors are cheaper to keep and to compare. Building the model makes no call to
Gemini; each `embed_...()` call does, and uses your key's quota.

### 5. The Key Is Checked First

`config.py`'s `load_api_key()` reads `GOOGLE_API_KEY` from the environment or from `.env`, and `models.py` calls it
before building the model. A missing key, the placeholder from `.env.example`, or a `.env` that isn't UTF-8 stops the
script at once with a message saying what to do, rather than with a confusing error from the first call to Gemini.
A key set in the environment (a Codespaces secret, say) wins over the one in `.env`.

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

**[05 · Vector Store](../05-vector-store/README.md)**: this project turned the 28 chunks into vectors. 05 stores
them in Qdrant, a vector database, one point per chunk with its vector, text and labels, and shows them in Qdrant's
dashboard.

**[Advanced · 04 · Embeddings](../../Advanced/04-embeddings/README.md)** (planned): the same project, production
grade. Its README lists what it will add.

### Ideas to Try

- Print the length of `vectors[0]` and `vectors[1]`: both 768, though chunk 1 is 457 characters and chunk 2 is 110.
- In `models.py`, change `EMBEDDING_SIZE` to `256`, run it again, and see each chunk converted to 256 numbers.
