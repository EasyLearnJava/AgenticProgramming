# 05 · Vector Store

Store the IT knowledge base's 28 chunks in Qdrant, a vector database: one point per chunk, with its vector, its text
and its labels. Qdrant runs inside the script, in memory. Built with **LangChain** (`langchain-qdrant`), **Qdrant**
and **Gemini**.

In a RAG app, the vector database is where a question's vector is compared with the chunks' vectors, to find the
closest.

> **Needs:** Python 3.11 or newer, and a Gemini API key. Qdrant runs inside the script, so there's no server to start.
> Each run makes 1 call to Gemini, for all 28 chunks: on the free tier, 28 of the 100 texts it embeds a minute.

---

## 🎯 What This Project Does

- **Makes a collection**, `it_knowledge_base` (Qdrant's word for a table of points), for vectors of 768 numbers
  compared by cosine similarity: how closely two vectors point the same way
- **Reads, chunks and embeds the knowledge base**: `data/sample_it_kb.csv` into 10 articles, then 28 chunks of at
  most 512 characters, then `embed_chunks()` sends the 28 texts to Gemini in one call, for a vector each
- **Stores each chunk as a point** with `store_vectors()`: an id, the chunk's vector, and a payload with its text
  (`page_content`) and its labels (`metadata`). Storing makes no call to Gemini: the vectors are already made
- **Keeps Qdrant in memory**, inside the script: there's nothing to install or start, and the points are gone when
  the script ends, so each run stores them again
- **Prints** the collection's settings, then every stored point, read back from Qdrant
- **All the code in one file**, `pipeline.py`: the loader, the splitter, the model, the embedding, the vector store,
  and `main()`, which names each step, then runs it. Two files are apart: `config.py`, which checks the key, and
  `utils.py`, which prints the points

**Try it:** `python pipeline.py`, and see the 28 points read back from Qdrant.

---

## 🏗️ Architecture

```text
┌───────────────────────────────────┐
│  pipeline.py: main()              │  ← the one file to run: it holds the steps below, and calls each in order
└─────────────────┬─────────────────┘
                  │ Steps 1 and 2: Read the knowledge base, then chunk it
                  ↓
┌───────────────────────────────────┐
│  load_documents()                 │  ← data/sample_it_kb.csv → 10 Documents, text + labels
│  split_documents()                │  ← 28 chunks of at most 512 characters
└─────────────────┬─────────────────┘
                  │ 28 chunks; Step 3: Embed
                  ↓
┌───────────────────────────────────┐
│  embed_chunks(chunks, embeddings) │  ← one call to Gemini, 28 vectors of 768 numbers
└─────────────────┬─────────────────┘
                  │ 28 vectors; Step 4: Store
                  ↓
┌───────────────────────────────────┐
│  make_vector_store(embeddings,    │  ← Qdrant in memory, inside the script, and the
│                    768)           │     it_knowledge_base collection: 768 numbers, cosine
│  store_vectors(store, chunks,     │  ← 28 points, each chunk with its vector: no call to Gemini
│                vectors)           │
└─────────────────┬─────────────────┘
                  │ 28 points: id + vector + payload (page_content, metadata)
                  ↓
┌───────────────────────────────────┐
│  print_points(store)              │  ← utils.py: reads the points back from Qdrant, and prints them
└───────────────────────────────────┘
```

### The Pipeline in This Project

1. **Run** → `python pipeline.py`: `main()` runs each step in order, and prints each one's name
2. **Load and chunk** → `load_documents()` and `split_documents()` turn the CSV into 28 chunks
3. **Embed** → `embed_chunks()` sends the 28 texts to Gemini in one call: 28 vectors of 768 numbers
4. **Make the collection** → `make_vector_store()` starts Qdrant in memory and makes `it_knowledge_base`: 768
   numbers per vector, compared by cosine
5. **Store** → `store_vectors()` writes 28 points, each chunk with its vector, with no call to Gemini
6. **Read back and print** → `print_points()`, from `utils.py`: the collection's settings, then every point, by
   article and place

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
cd "projects/RAG/IT Knowledge Base/Basic/05-vector-store"   # from the repo root; quotes for the spaces
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
python pipeline.py                   # store the 28 chunks in Qdrant, in memory
```

### Or: Run It in One Command

With your key in `.env` (Step 4), this one command does Steps 2, 3 and 5 for you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/05-vector-store   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs `python
pipeline.py` in this folder with the venv's Python, so there's nothing to activate. The project's output is the same
as in Step 5, after run.py's own lines saying what it creates, installs and runs.

---

## 🧪 Testing

```bash
python -m pytest -m "not live"       # 24 passed, 3 deselected  (add -v for one line per test)
```

The tests keep Qdrant in memory too. Most of them also use `tests/fakes.py`'s stand-in for Gemini, so they need no
key and no network. They check:

- **The embeddings**: the 28 chunks are embedded in one call, one vector each, in order, from their text only
- **The store**: a new collection is empty, cosine, of the right size; storing the vectors makes 28 points with no
  call to the model, and a chunk without a vector stops it instead of being left out; each point holds a vector,
  the chunk's text and its labels, and LangChain's store reads them back as the chunks; an existing collection is
  deleted and made new, with none of its old points; and what `print_points()` prints
- **The pipeline**: it embeds the chunks once, stores them in memory, and never embeds a question; and no other file
  runs anything
- **The model, the chunks and the Documents**: the model's settings and the no-key message; 28 chunks with their
  labels; 10 Documents with their text and labels

The 3 deselected tests are live tests, marked `live`: they call the real Gemini, so they need your key in `.env`;
with no key, `tests/conftest.py` skips them, so plain `python -m pytest` runs only the others. Together they embed 57
texts, under the free tier's limit of 100 a minute, so `python -m pytest -m live` runs them all at once.

---

## 🎓 Key Concepts Demonstrated

### 1. A Vector Database Stores Points

A collection is a table of points, and each point has three parts: an id, a vector, and a payload. Here the payload
holds the chunk's text (`page_content`) and its labels (`metadata`), so whatever finds a vector also gets the text and
labels that go with it. `QdrantVectorStore` is LangChain's wrapper around a collection. The run reads the points
back from Qdrant and prints them:

```text
Collection 'it_knowledge_base': 28 points, vectors of 768 numbers, compared by Cosine
Each point holds an id, a vector and a payload with metadata, page_content

Point 1 of 28: VPN Connection Timeout, from character 0: 768 numbers, 457 characters of text, 7 labels
Point 2 of 28: VPN Connection Timeout, from character 459: 768 numbers, 110 characters of text, 7 labels
...
```

The 7 labels are the article's 6 (`doc_id`, title, system, category, priority and tags) plus the chunk's own
`start_index`.

The vectors are made before the store: `embed_chunks()` in Step 3, then `store_vectors()` in Step 4. LangChain's own
`add_documents()` would embed the chunks itself, so `store_vectors()` writes the points with Qdrant's `upsert()`
instead, the text and labels under `page_content` and `metadata`: the names `QdrantVectorStore` reads them from, so
it reads the points back as the chunks.

### 2. In Memory, Inside the Script

```python
QdrantClient(":memory:")            # in make_vector_store(): inside the script, in memory, gone when it ends
```

Qdrant runs in the script's own memory, so there's nothing to install or start, and the points last only as long as
the script does. That's enough here: each run embeds and stores the 28 chunks again. The same code works with Qdrant
running as a server, `QdrantClient(url=...)`: only the client differs. In memory, Qdrant compares every vector, as a
plain loop would, which is fine for 28; a Qdrant server keeps an index, so a search among millions needn't compare
them all.

`make_vector_store()` asks for that index anyway, to show how it looks: `hnsw_config` in the code under Key Concept 4.
The index is called HNSW: a graph linking each vector to its 16 nearest (`m`), so a search hops through the graph and
checks a small part of the vectors instead of every one; `ef_construct` is how thoroughly it searches while building
the graph. An index makes search faster, not better: at best it finds the same chunks. Here it does nothing: in
memory, Qdrant ignores these settings, and even a Qdrant server builds the index only once it holds thousands of
chunks, not 28.

### 3. Starting Fresh on Every Run

`store_vectors()` gives each new point a random id, so storing the same 28 chunks twice in one collection would make
56 points. `make_vector_store()` deletes a collection by that name first, if it's there, then makes it new. In memory,
each run of `pipeline.py` starts empty anyway; the delete matters when one program makes the collection again on the
same client, as one of the tests does: none of the old points are left.

### 4. How Qdrant Measures "Close": the Distance

When `make_vector_store()` creates the collection, it also fixes how Qdrant will measure how close two vectors are:

```python
client.create_collection(collection, vectors_config=VectorParams(size=size, distance=Distance.COSINE),
                         hnsw_config=HnswConfigDiff(m=16, ef_construct=100))   # the index: see Key Concept 2
```

Qdrant offers four distances. To see how they differ, take three vectors of 2 numbers instead of 768:

```text
a = [3, 4]     the stored chunk
b = [6, 8]     the same direction as a, twice as long
c = [4, 3]     a slightly different direction, the same length as a
```

Which is closer to `a`, `b` or `c`? The four distances don't agree:

| Distance | What it measures | a vs b | a vs c | Closest to a | Better score |
|---|---|---|---|---|---|
| **Cosine** | the angle between the arrows, ignoring their length | 1.00 | 0.96 | **b** | higher |
| **Dot** | the angle and the lengths, multiplied together | 50 | 24 | **b** | higher |
| **Euclid** | the straight line between the arrows' tips | 5.00 | 1.41 | **c** | lower |
| **Manhattan** | the walk between the tips along the grid lines | 7 | 2 | **c** | lower |

Cosine and Dot say `b`, which points exactly the same way as `a`. Euclid and Manhattan say `c`, whose tip is nearer.
For text, the direction is what carries the meaning, so `b` should win: that's why text embeddings use cosine.

#### Cosine: the angle (what this project uses)

![Cosine. Three arrows from the origin on a grid: a to [3, 4], b to [6, 8] along the same line as a, and c to [4, 3]. An arc marks the 16 degree angle between a and c; a and b are 0 degrees apart. Cosine of a and b: 50 / (5 x 10) = 1.00. Cosine of a and c: 24 / (5 x 5) = 0.96. Higher is closer, so b is closest: only the direction counts.](images/cosine.svg)

Cosine divides the dot product by both lengths, so only the angle is left: 1 means the same direction, 0 at right
angles, -1 opposite. `b` scores 1.00 although it's twice as long as `a`.

**Use it for** text embeddings, where the meaning is the direction, and for any vectors that don't already have
length 1, like Gemini's at 768 numbers. If a model's documentation doesn't say otherwise, cosine is the safe choice.

With cosine, Qdrant divides every number of a vector by the vector's length, which keeps the direction:

![Normalized. A long grey arrow goes from the origin to [3, 4], length 5: what Gemini returns. A short blue arrow along the same line ends on a dashed circle of radius 1, at [0.6, 0.8]: what Qdrant stores. Every number is divided by 5. The direction, and so every cosine score, stays the same.](images/normalize.svg)

The direction doesn't change, so every cosine score stays the same: Gemini's vectors don't come back at length 1, but
a point's vector read back from the collection does.

#### Dot: the angle and the lengths

![Dot. The same three arrows. A dashed line drops from c's tip onto a's line, and c's shadow along a is 4.8 long. Dot of a and b: 3x6 + 4x8 = 50, that is 5 x 10. Dot of a and c: 3x4 + 4x3 = 24, that is 5 x 4.8. Higher is closer, so b is closest. On vectors of length 1, dot ranks exactly like cosine.](images/dot.svg)

Multiply the numbers pair by pair and add them up: a longer vector scores higher, and higher is closer.

**Use it for** vectors that already have length 1: then it ranks exactly like cosine, and is a little faster.

#### Euclid: the straight line between the tips

![Euclid. The same three arrows. A dashed line beside a and b runs from a's tip to b's tip: 5.00 long. Another runs from a's tip to c's tip: 1.41 long. Lower is closer, so c is closest, though b points the same way as a.](images/euclid.svg)

The straight line between the tips: lower is closer, and `b` loses for being long, though it means the same thing.

**Use it for** data where the position matters, not just the direction, such as sensor readings or measurements.

#### Manhattan: the walk along the grid

![Manhattan. The same three arrows. A dashed path walks from a's tip to b's tip along the grid lines: 4 up and 3 across, 3 + 4 = 7. Another walks from a's tip to c's tip: 1 across and 1 down, 1 + 1 = 2. Lower is closer, so c is closest.](images/manhattan.svg)

Add up the differences, like walking city blocks with no diagonals: lower is closer.

**Use it for** number data where one big difference should count for less than with Euclid; rarely for text.

### 5. Choosing a Distance

- **Use the distance the embedding model's documentation recommends.** For Gemini's embeddings, that's cosine.
- **It's fixed when the collection is created.** To change it, make a new collection and store the chunks again.
- **It decides what a search's scores mean.** With cosine and dot, higher is closer; with Euclid and Manhattan, lower
  is closer. This project uses cosine, so its scores read "the closer to 1, the closer the meaning".

### 6. One File Runs the Steps

`pipeline.py` is the only file that runs anything: `main()` runs Steps 1 to 3, printing a line each, then Step 4:
`make_vector_store()` starts Qdrant in memory and makes the collection, `store_vectors()` stores Step 3's vectors, and
`print_points()`, from `utils.py`, reads them back and prints them. `config.py` and `utils.py` only define what it
uses, and building the model makes no call, so importing any of them makes no call. The model and its vector size
are parameters of `main()`, so the tests pass a stand-in for Gemini.

### 7. The Code in One File, the Helpers Apart

```python
from config import MissingKeyError, load_api_key   # checks the key, before the model is built
from utils import print_points                     # a helper: showing the points
```

`pipeline.py` holds the project's code, top to bottom: the settings (the data file, the column lists, the chunk size
and overlap, the model's name and vector size, the collection's name), the loader, the splitter, the model,
`embed_chunks()`, the vector store (`make_vector_store()` and `store_vectors()`), then `main()`, which runs them.
Two files stay apart. `utils.py` holds `print_points()`, which reads the points back from the store it's handed, so
it needs nothing from `pipeline.py`. `config.py` holds the key check, because the tests need it before
`pipeline.py` is imported: `tests/conftest.py` asks it whether there's a real key, and gives the model a fake one
when there isn't.

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

- In `pipeline.py`, print `f"{math.hypot(*vectors[0]):.4f}"` before `store_vectors()`, and in `print_points()` the
  same for each `point.vector` (with `import math` at the top of each file): not 1 before, 1.0000 every time after
  (Key Concept 4). One test checks the pipeline's output, so take the prints out before `python -m pytest`.
- Run `python pipeline.py` twice and print the points' ids with `scroll()`: the same 28 chunks, with new random ids
  each time.
- In `make_vector_store()`, change `Distance.COSINE` to `Distance.EUCLID`, and see `print_points()` say
  "compared by Euclid". Three tests check for cosine, and one searches, which `QdrantVectorStore` refuses unless its
  `distance=` (cosine if not given) matches the collection's, so put it back before `python -m pytest`.
