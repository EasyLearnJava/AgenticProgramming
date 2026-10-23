# 05 · Vector Store

Store the IT knowledge base's 28 chunks in Qdrant, a vector database: one point per chunk, with its vector, its text
and its labels. Qdrant runs inside the script, in local mode, and saves the points in a folder, `qdrant_data/`. Built
with **LangChain** (`langchain-qdrant`), **Qdrant** and **Gemini**.

> **Needs:** Python 3.11 or newer, and a Gemini API key. Qdrant runs inside the script, so there's no server to start.
> Each run makes 1 call to Gemini, for all 28 chunks.

---

## 🎯 What This Project Does

- **Makes a collection**, `it_knowledge_base` (Qdrant's word for a table of points), for vectors of 768 numbers
  compared by cosine similarity: how closely two vectors point the same way
- **Reads, chunks and embeds the knowledge base**: `data/sample_it_kb.csv` into 10 articles, then 28 chunks of at
  most 512 characters, then `embed_chunks()` sends the 28 texts to Gemini in one call, for a vector each
- **Stores each chunk as a point** with `store_vectors()`: an id, the chunk's vector, and a payload with its text
  (`page_content`) and its labels (`metadata`). Storing makes no call to Gemini: the vectors are already made
- **Starts fresh on every run**: it deletes the collection in `qdrant_data/` and stores the chunks again. The points
  get random ids, so without that, every run would add 28 more copies
- **Prints** where Qdrant keeps the points, the collection's settings, then every stored point, read back from Qdrant
- **Runs from one file**, `pipeline.py`, which names each step, then runs it

**Try it:** `python pipeline.py`, and see the 28 points read back from `qdrant_data/`.

---

## 🏗️ Architecture

```text
┌───────────────────────────────────┐
│  pipeline.py: main()              │  ← the one file to run: calls each step in order
└─────────────────┬─────────────────┘
                  │ Steps 1 and 2: Read the knowledge base, then chunk it
                  ↓
┌───────────────────────────────────┐
│  load_documents()                 │  ← knowledge_base.py: data/sample_it_kb.csv → 10 Documents, text + labels
│  split_documents()                │  ← chunking.py: 28 chunks of at most 512 characters
└─────────────────┬─────────────────┘
                  │ 28 chunks; Step 3: Embed
                  ↓
┌───────────────────────────────────┐
│  embed_chunks(chunks, embeddings) │  ← embed_chunks.py: one call to Gemini, 28 vectors of 768 numbers
└─────────────────┬─────────────────┘
                  │ 28 vectors; Step 4: Store
                  ↓
┌───────────────────────────────────┐
│  make_vector_store(embeddings,    │  ← vector_store.py: the it_knowledge_base collection,
│                    768, client)   │     768 numbers, cosine, wrapped in QdrantVectorStore
│  store_vectors(store, chunks,     │  ← 28 points, each chunk with its vector: no call to Gemini
│                vectors)           │
└─────────────────┬─────────────────┘
                  │ 28 points: id + vector + payload (page_content, metadata)
                  ↓
┌───────────────────────────────────┐
│  Qdrant, local mode               │  ← make_client(): inside the script, the points saved
│  qdrant_data/                     │     in this folder; print_points() reads them back
└───────────────────────────────────┘
```

### The Pipeline in This Project

1. **Run** → `python pipeline.py`: `main()` runs each step in order, and prints each one's name
2. **Load and chunk** → `knowledge_base.py` and `chunking.py` turn the CSV into 28 chunks
3. **Embed** → `embed_chunks()` sends the 28 texts to Gemini in one call: 28 vectors of 768 numbers
4. **Open Qdrant** → `make_client()`: local mode, inside the script, saving the points in `qdrant_data/`
5. **Start fresh** → `make_vector_store()` deletes the collection if it's there (the last run's)
6. **Make the collection** → then it makes it new: `it_knowledge_base`, 768 numbers per vector, cosine
7. **Store** → `store_vectors()` writes 28 points, each chunk with its vector, with no call to Gemini
8. **Read back and print** → `print_points()`, from `utils.py`: the collection's settings, then every point, by
   article and place
9. **Close** → `client.close()`: the points stay in the folder, and another program can open it

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
python pipeline.py                   # store the 28 chunks in qdrant_data/
```

### Or: Run It in One Command

With your key in `.env` (Step 4), this one command does Steps 2, 3 and 5 for you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/05-vector-store   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs
`python pipeline.py` in this folder with the venv's Python, so there's nothing to activate. The output is the same as
in Step 5.

### Where the Points Are Kept

`qdrant_data/` is made next to `pipeline.py` on the first run, and it stays after the script ends: open it with Qdrant
again, as in [Check a Score Yourself](#9-check-a-score-yourself), and the points are there. It's in `.gitignore`, so
it's never committed. Delete it to start over: the next run makes it again. Only one program at a time can open it.

---

## 🧪 Testing

```bash
python -m pytest                     # 27 passed, 3 skipped     (add -v for one line per test)
```

The tests keep Qdrant in memory, or in a folder of each test's own, never in `qdrant_data/`. Most of them also use
`tests/fakes.py`'s stand-in for Gemini, so they need no key and no network. They check:

- **The embeddings**: the 28 chunks are embedded in one call, one vector each, in order, from their text only
- **The store**: a new collection is empty, cosine, of the right size; storing the vectors makes 28 points with no
  call to the model, and a chunk without a vector stops it instead of being left out; each point holds a vector,
  the chunk's text and its labels, and LangChain's store reads them back as the chunks; an existing collection is
  deleted and made new, with none of its old points, on disk too; points on disk stay after Qdrant is closed; and
  what `print_points()` prints
- **The pipeline**: it embeds the chunks once, stores them on disk, and never embeds a question; the points stay in
  the folder, and each run starts fresh; and no other file runs anything
- **The model, the chunks and the Documents**: the model's settings and the no-key message; 28 chunks with their
  labels; 10 Documents with their text and labels

The 3 skipped tests are live tests: they call the real Gemini, so they run only when a key is set, in `.env` or the
environment. `tests/conftest.py` decides this once, before any test runs: with no key, it gives the model a fake one
so it can be built, and skips the live tests.

---

## 🎓 Key Concepts Demonstrated

### 1. A Vector Database Stores Points

A collection is a table of points, and each point has three parts: an id, a vector, and a payload. Here the payload
holds the chunk's text (`page_content`) and its labels (`metadata`), so whatever finds a vector also gets the text and
labels that go with it. `QdrantVectorStore` is LangChain's wrapper around a collection.

The vectors are made before the store: `embed_chunks()` in Step 3, then `store_vectors()` in Step 4. LangChain's own
`add_documents()` would embed the chunks itself, so `store_vectors()` writes the points with Qdrant's `upsert()`
instead, the text and labels under `page_content` and `metadata`: the names `QdrantVectorStore` reads them from, so
it reads the points back as the chunks.

### 2. On Disk or In Memory

```python
QdrantClient(path="qdrant_data")    # local mode: inside the script, the points kept in this folder after it ends
QdrantClient(":memory:")            # inside the script too, in memory: gone at the end
```

The same code works with either: only the client differs. `pipeline.py` uses the folder; the tests use memory, or a
folder of their own. A folder can be open in only one program at a time; for several programs at once, Qdrant also
runs as a server, `QdrantClient(url=...)`, with the same code.

### 3. Starting Fresh on Every Run

`store_vectors()` gives each new point a random id. Storing the same 28 chunks twice would make 56 points, so
`make_vector_store()` deletes the collection first, if it's there, then makes it new: in `qdrant_data/`, that's the
last run's collection. It deletes the collection's points before the collection itself: on Windows, Qdrant's local
mode can't remove the files of a collection it has open, and the new collection would find the old points in them.
Each run embeds the chunks again too: one call to Gemini.

### 4. How Qdrant Measures "Close": the Distance

When `make_vector_store()` creates the collection, it also fixes how Qdrant will measure how close two vectors are:

```python
client.create_collection(collection, vectors_config=VectorParams(size=size, distance=Distance.COSINE))
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

Cosine divides the dot product by both lengths, so only the angle is left: 1 means the same direction, 0 unrelated,
-1 opposite. `b` scores 1.00 although it's twice as long as `a`.

**Use it for** text embeddings, where the meaning is the direction, and for any vectors that don't already have
length 1, like Gemini's at 768 numbers. If a model's documentation doesn't say otherwise, cosine is the safe choice.

#### Dot: the angle and the lengths

![Dot. The same three arrows. A dashed line drops from c's tip onto a's line, and c's shadow along a is 4.8 long. Dot of a and b: 3x6 + 4x8 = 50, that is 5 x 10. Dot of a and c: 3x4 + 4x3 = 24, that is 5 x 4.8. Higher is closer, so b is closest. On vectors of length 1, dot ranks exactly like cosine.](images/dot.svg)

The dot product multiplies the numbers pair by pair and adds them up: `3×6 + 4×8 = 50`. It's the same as `a`'s length
times the other vector's "shadow" on `a`: `b`'s shadow is all of it, 10, so `5 × 10 = 50`; `c`'s is 4.8, so
`5 × 4.8 = 24`. A longer vector scores higher, so length counts as well as direction.

**Use it for** vectors that already have length 1. Then dot and cosine give exactly the same order, and dot is a
little faster. OpenAI's embeddings, and Gemini's at the full 3072 numbers, come back with length 1. Use it also when a
model's documentation says to, or when a longer vector should win on purpose (in some recommendation systems, a longer
vector means a more popular item).

#### Euclid: the straight line between the tips

![Euclid. The same three arrows. A dashed line beside a and b runs from a's tip to b's tip: 5.00 long. Another runs from a's tip to c's tip: 1.41 long. Lower is closer, so c is closest, though b points the same way as a.](images/euclid.svg)

The ordinary distance between two points: `√(3² + 4²) = 5.00` from `a`'s tip to `b`'s, `√(1² + 1²) = 1.41` to `c`'s.
Lower is closer, and 0 means the same point. `b` loses because it's long, even though it means the same thing.

**Use it for** data where the actual position matters, not just the direction: image features, sensor readings,
measurements, grouping similar items into clusters. On vectors of length 1 it ranks results in the same order as
cosine.

#### Manhattan: the walk along the grid

![Manhattan. The same three arrows. A dashed path walks from a's tip to b's tip along the grid lines: 4 up and 3 across, 3 + 4 = 7. Another walks from a's tip to c's tip: 1 across and 1 down, 1 + 1 = 2. Lower is closer, so c is closest.](images/manhattan.svg)

Like walking city blocks, with no diagonals: add up the differences, `3 + 4 = 7` to `b` and `1 + 1 = 2` to `c`.
Lower is closer.

**Use it for** text rarely. It shows up with other kinds of number data, where one big difference should count for
less than it does with Euclid, which squares every difference.

### 5. Why Qdrant Works With Vectors of Length 1

With cosine, Qdrant divides every number of a vector by the vector's length, which keeps the direction:

![Normalized. A long grey arrow goes from the origin to [3, 4], length 5: what Gemini returns. A short blue arrow along the same line ends on a dashed circle of radius 1, at [0.6, 0.8]: what Qdrant stores. Every number is divided by 5. The direction, and so every cosine score, stays the same.](images/normalize.svg)

```text
Gemini returns:  [3, 4]        length √(3² + 4²) = 5
Qdrant uses:     [0.6, 0.8]    [3/5, 4/5], length 1
```

The meaning is the direction, and that doesn't change, so every cosine score stays the same. Qdrant does it so that
each search becomes a simple dot product, which is faster. It does this only with cosine; with Dot, Euclid and
Manhattan it uses the vectors exactly as they came.

A Qdrant server keeps the vectors at length 1. Local mode, as here, does too while the script runs, but it saves them
in `qdrant_data/` as Gemini returned them: a program that opens the folder later, like the one in
[Check a Score Yourself](#9-check-a-score-yourself), reads Gemini's own numbers back. The scores are the same either
way.

### 6. Choosing a Distance

- **Use the distance the embedding model's documentation recommends.** For Gemini's embeddings, that's cosine.
- **It's fixed when the collection is created.** To change it, make a new collection and store the chunks again.
- **It decides what the scores mean.** With cosine and dot, higher is closer; with Euclid and Manhattan, lower is
  closer. This project uses cosine, so its scores read "the closer to 1, the closer the meaning".

### 7. One File Runs the Steps

`pipeline.py` is the only file that runs anything: `main()` runs Steps 1 to 3, printing a line each, then Step 4:
`make_client()` opens Qdrant on disk, `make_vector_store()` makes the collection, `store_vectors()` stores Step 3's
vectors, `print_points()`, from `utils.py`, prints them, and `client.close()` frees the folder. The other files only
define the steps and that helper, so importing them makes no call. The model, its vector size and the folder are
parameters of `main()`, so the tests pass a stand-in for Gemini and a folder of their own.

### 8. What a Score Means

A search in Qdrant gives each point it finds a score: the cosine similarity between the searched vector and the
point's vector, how closely the two point the same way.

- **1.0** means the same direction, the same meaning; **0** means unrelated.
- **0.76** means fairly similar: an angle of about 40° between the two vectors; **0.87** is about 30°.

It's the cosine from [How Qdrant Measures "Close": the Distance](#4-how-qdrant-measures-close-the-distance), above,
with 768 numbers instead of 2:

```text
cosine(a, b) = (a₁×b₁ + a₂×b₂ + … + a₇₆₈×b₇₆₈) / (length of a × length of b)
```

The collection uses cosine, so Qdrant works with every vector at length 1 (see
[Why Qdrant Works With Vectors of Length 1](#5-why-qdrant-works-with-vectors-of-length-1)). Both lengths are 1, so
the score is just the sum of the 768 products: the two vectors multiplied number by number, then added up.
With 2 numbers, `[0.6, 0.8]` and `[0.8, 0.6]` give `0.6×0.8 + 0.8×0.6 = 0.96`. A search in Qdrant does this sum
between the searched vector and every stored point, and lists the highest first.

Reading the scores:

- **The order matters more than the values.** All 28 chunks are IT help-desk text, so to Gemini they're all fairly
  similar, and the scores sit close together. What decides a search is which chunks score highest.

### 9. Check a Score Yourself

After `python pipeline.py`, with the venv active, in this folder, this reads two stored points from `qdrant_data/` and
works out their cosine itself, with no call to Gemini:

```bash
python - <<'EOF'
from qdrant_client import QdrantClient
client = QdrantClient(path="qdrant_data")
(a, b), _ = client.scroll("it_knowledge_base", limit=2, with_vectors=True)
length_a, length_b = (sum(x * x for x in point.vector) ** 0.5 for point in (a, b))
print("lengths:", round(length_a, 4), round(length_b, 4))   # as Gemini returned them
print("cosine:", round(sum(x * y for x, y in zip(a.vector, b.vector)) / (length_a * length_b), 4))
client.close()
EOF
```

It prints the two vectors' lengths, then their cosine score: the formula above, the sum of the products divided by
both lengths. The lengths aren't 1: local mode saves the vectors as Gemini returned them (see
[Why Qdrant Works With Vectors of Length 1](#5-why-qdrant-works-with-vectors-of-length-1)). `scroll()` gives the
points in id order, and each run of `pipeline.py` stores them with new random ids, so which two chunks you get changes
from run to run.

---

## 🛠️ Troubleshooting

**Issue**: `Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).`
**Fix**: There's no `.env` in this folder, and no `GOOGLE_API_KEY` in the environment. Do Step 4.

**Issue**: `Can't build the models: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Put your real key after `GOOGLE_API_KEY=`.

**Issue**: `RuntimeError: Storage folder .../qdrant_data is already accessed by another instance of Qdrant client. If you require concurrent access, use Qdrant server instead.`
**Fix**: Another program has `qdrant_data/` open, such as a Python session from
[Check a Score Yourself](#9-check-a-score-yourself) that hasn't ended. Only one program at a time can open the folder:
close the other one, then run again.

**Issue**: `python vector_store.py` prints nothing
**Fix**: That file only defines the step. Run `python pipeline.py` (Step 5), which runs every step.

---

## 💡 Ideas to Try

- In [Check a Score Yourself](#9-check-a-score-yourself), set `limit=28` and print the cosine of the first point with
  each of the others, to see which chunks score highest.
- Run `python pipeline.py` twice and print the points' ids with `scroll()`: the same 28 chunks, with new random ids
  each time.
- Delete `qdrant_data/` and run `python pipeline.py` again: the folder is made anew.
