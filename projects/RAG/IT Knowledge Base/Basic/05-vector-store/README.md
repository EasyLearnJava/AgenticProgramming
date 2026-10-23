# 05 · Vector Store

Store the IT knowledge base's 28 chunks in Qdrant, a vector database: one point per chunk, with its vector, its text
and its labels, then look at them in Qdrant's web dashboard. Qdrant runs as a server in Docker, or inside the script
("in memory") with no Docker at all. Built with **LangChain** (`langchain-qdrant`), **Qdrant** and **Gemini**.

> **Needs:** Python 3.11 or newer, a Gemini API key, and Docker (or no Docker, with Qdrant in memory). Each run makes
> 1 call to Gemini, for all 28 chunks.

---

## 🎯 What This Project Does

- **Makes a collection**, `it_knowledge_base` (Qdrant's word for a table of points), for vectors of 768 numbers
  compared by cosine similarity: how closely two vectors point the same way
- **Reads and chunks the knowledge base**: `data/sample_it_kb.csv` into 10 articles, then 28 chunks of at most 512
  characters
- **Embeds and stores the chunks** through LangChain's `QdrantVectorStore`: `add_documents()` sends the 28 texts to
  Gemini in one call, and stores each chunk as a point: an id, its vector, and a payload with its text
  (`page_content`) and its labels (`metadata`)
- **Starts fresh on every run**: it deletes the collection on the server and stores the chunks again. The points get
  random ids, so without that, every run would add 28 more copies
- **Prints** where Qdrant is, the collection's settings, then every stored point, read back from Qdrant, and where to
  find the dashboard
- **Runs from one file**, `pipeline.py`, which names each step, then runs it

**Try it:** `python pipeline.py`, then open the dashboard and click through the 28 points.

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
                  │ 28 chunks; Step 3: Embed and store
                  ↓
┌───────────────────────────────────┐
│  make_vector_store(embeddings,    │  ← vector_store.py: the it_knowledge_base collection,
│                    768, client)   │     768 numbers, cosine, wrapped in QdrantVectorStore
│  store.add_documents(chunks)      │  ← one call to Gemini, then 28 points
└─────────────────┬─────────────────┘
                  │ 28 points: id + vector + payload (page_content, metadata)
        ┌─────────┴──────────┐
        ↓                    ↓
┌───────────────────┐ ┌──────────────────────┐
│  Qdrant server    │ │  Qdrant in memory    │  ← QDRANT_URL in .env: the server (Docker);
│  (Docker, :6333)  │ │  (inside the script) │     no QDRANT_URL: in memory, gone at the end
└─────────┬─────────┘ └──────────────────────┘
          │
          ↓
   the dashboard: http://localhost:6333/dashboard
```

### The Pipeline in This Project

1. **Run** → `python pipeline.py`: `main()` runs each step in order, and prints each one's name
2. **Load and chunk** → `knowledge_base.py` and `chunking.py` turn the CSV into 28 chunks
3. **Choose Qdrant** → with `QDRANT_URL` in `.env`, the server; without it, Qdrant in memory
4. **Start fresh** → `make_vector_store()` deletes the collection if it's there (on the server, the last run's)
5. **Make the collection** → then it makes it new: `it_knowledge_base`, 768 numbers per vector, cosine
6. **Embed and store** → `store.add_documents(chunks)` embeds the 28 texts in one call and stores 28 points
7. **Read back and print** → `print_points()`, from `utils.py`: the collection's settings, then every point, by
   article and place

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**, made in the Google Cloud console, under APIs & Services > Credentials. Every call to Gemini
  uses your key's quota
- **Docker**: Docker Desktop on Windows and macOS; GitHub Codespaces has Docker already. To run without Docker, see
  [Or: Run It Without Docker](#or-run-it-without-docker)
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

`.env` also has `QDRANT_URL=http://localhost:6333`, from `.env.example`: that's what tells the script to use the
server. The script runs next to Qdrant, so for it the server is always `localhost`, in Codespaces too.

### Step 5: Start the Qdrant Server

```bash
docker compose up -d                 # start Qdrant in the background (the first time, Docker downloads it)
docker compose ps                    # check: the qdrant service is "Up"
```

The server keeps running in the background until you stop it (see [Stop the Server](#stop-the-server)), so next time
you only need Step 6.

### Step 6: Run It

```bash
python pipeline.py                   # store the 28 chunks in the server
```

It prints Steps 1 and 2 in one line each, then Step 3 in full: where Qdrant is, the collection's settings, then every
stored point, one line each: its article, where in the article the chunk starts, its vector's size, its text's length
and how many labels it has. It ends with where to find the dashboard. Gemini's numbers aren't printed, so this is
exactly what you'll see:

```text
Step 1: Read the knowledge base: 10 documents
Step 2: Chunk: 28 chunks of at most 512 characters
Step 3: Embed and store
Qdrant: the server at http://localhost:6333
Collection 'it_knowledge_base': 28 points, vectors of 768 numbers, compared by Cosine
Each point holds an id, a vector and a payload with metadata, page_content

Point 1 of 28: VPN Connection Timeout, from character 0: 768 numbers, 457 characters of text, 7 labels
Point 2 of 28: VPN Connection Timeout, from character 459: 768 numbers, 110 characters of text, 7 labels
Point 3 of 28: MFA Setup Failure, from character 0: 768 numbers, 144 characters of text, 7 labels
...
Point 28 of 28: Microsoft Teams Audio Issues, from character 581: 768 numbers, 118 characters of text, 7 labels

See them in Qdrant's dashboard: http://localhost:6333/dashboard
In GitHub Codespaces: open the Ports tab, open the address for port 6333, and add /dashboard to it.
```

The `...` stands for points 4 to 27: your terminal shows all 28.

### Step 7: Open the Dashboard

| Where you run it | The dashboard's address |
|---|---|
| On your own computer | http://localhost:6333/dashboard |
| In GitHub Codespaces | `https://<codespace-name>-6333.app.github.dev/dashboard` |

In Codespaces, your browser is on your own computer, not in the codespace, so it needs the codespace's forwarded
address. The surest way to get it is the **Ports** tab:

1. Open the **Ports** tab, next to **Terminal**. Codespaces forwards port 6333 once Qdrant is running.
2. If 6333 isn't listed, click **Add Port** and type `6333`.
3. Click the globe icon on the 6333 row: it opens the exact forwarded address for your codespace.
4. Add `/dashboard` to the end of that address.

`<codespace-name>` is the first part of your codespace's own address, for example `silver-lamp-jwjq66xxgphp7rw` in
`silver-lamp-jwjq66xxgphp7rw.github.dev`. The port is private by default: open it in the browser where you're signed
in to GitHub.

In the dashboard, open **Collections**, then `it_knowledge_base`: its 28 points, each with its payload (the chunk's
text and labels) and its vector.

### Or: Run It in One Command

With your key in `.env` (Step 4) and the Qdrant server started (Step 5), this one command does Steps 2, 3 and 6 for
you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/05-vector-store   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs
`python pipeline.py` in this folder with the venv's Python, so there's nothing to activate. The output is the same as
in Step 6. Then open the dashboard as in Step 7.

### Or: Run It Without Docker

In `.env`, put a `#` at the start of the `QDRANT_URL` line:

```text
# QDRANT_URL=http://localhost:6333
```

Then `python pipeline.py` keeps Qdrant in memory, inside the script. It prints the same steps, collection and points,
but the line after `Step 3: Embed and store` is `Qdrant: in memory, inside this script`, and there's no dashboard
line, because there's no server to look at. To go back to the server, remove the `#`.

### Stop the Server

Run `docker compose down` in this folder. Its data stays in a Docker volume for next time (`docker compose down -v`
deletes it). In Codespaces, the server also stops when the codespace stops: run `docker compose up -d` again next
time. Only one program can use port 6333 at a time, so stop this server before starting another Qdrant.

---

## 📁 Project Structure

```text
05-vector-store/
├── pipeline.py                           # the one file to run: main() calls each step in order
├── vector_store.py                       # make_vector_store(): Step 3
├── utils.py                              # connect() and print_points(): the helpers that connect and print
├── models.py                             # the embedding model: gemini-embedding-001, 768 numbers
├── config.py                             # load_api_key(): the key, checked before anything else runs
├── chunking.py                           # split_documents(): Step 2, the 28 chunks of at most 512 characters
├── knowledge_base.py                     # load_documents(): Step 1, the 10 articles, text + labels
├── docker-compose.yml                    # the Qdrant server, qdrant/qdrant:v1.19.1, on port 6333
├── data/
│   └── sample_it_kb.csv                  # the knowledge base: 10 IT support articles
├── images/                               # the pictures in this README
├── tests/
│   ├── conftest.py                       # decides once whether the live tests can run
│   ├── fakes.py                          # stand-ins for Gemini: no key, no network
│   ├── test_pipeline.py                  # the steps, in memory and with a server; nothing else runs
│   ├── test_vector_store.py              # the collection, the points, what's printed
│   ├── test_models.py                    # the model's settings, and the no-key message
│   ├── test_chunking.py                  # the chunks
│   └── test_knowledge_base.py            # the Documents
├── .env.example                          # copy it to .env: your key, and QDRANT_URL for the server
├── requirements.txt                      # the packages, pinned to exact versions
├── requirements-dev.txt                  # requirements.txt plus pytest, for the tests
├── pytest.ini                            # lets the tests import the files, and finds them in tests/
└── README.md                             # you are here
```

---

## 🧪 Testing

```bash
python -m pytest                     # 22 passed, 2 skipped     (add -v for one line per test)
```

The tests never need Docker: an in-memory Qdrant stands in for the server. Most of them also use `tests/fakes.py`'s
stand-in for Gemini, so they need no key and no network. They check:

- **The store**: a new collection is empty, cosine, of the right size; storing the chunks makes 28 points in one
  embedding call; each point holds a vector, the chunk's text and its labels; an existing collection is deleted
  and made new; and what `print_points()` prints
- **The pipeline**: in memory, it stores the chunks and never embeds a question; with a server's address it uses that
  server and starts fresh on each run; with an address but no server, it stops and says what to do; and no other
  file runs anything
- **The model, the chunks and the Documents**: the model's settings and the no-key message; 28 chunks with their
  labels; 10 Documents with their text and labels

The 2 skipped tests are live tests: they call the real Gemini, so they run only when a key is set, in `.env` or the
environment. `tests/conftest.py` decides this once, before any test runs: with no key, it gives the model a fake one
so it can be built, and skips the live tests.

---

## 📊 Understanding the Output

```text
Point 1 of 28: VPN Connection Timeout, from character 0: 768 numbers, 457 characters of text, 7 labels
```

Each point is one chunk: `from character 0` is where in its article the chunk starts, `768 numbers` is its vector,
`457 characters of text` is its `page_content`, and the 7 labels are its `metadata`: the article's 6 from
`knowledge_base.py` (`doc_id`, title, system, category, priority, tags), plus `start_index` from `chunking.py`.

### The Visualize Tab: Every Chunk on One Map

In `it_knowledge_base`, the **Visualize** tab draws all 28 points as dots on one map. Its right-hand side holds a
request, and nothing is drawn until you click the small **RUN** link just above the request's `{`. To color the dots
by article, replace the request with this one, then click **RUN**:

```json
{
  "limit": 100,
  "color_by": { "payload": "metadata.title" }
}
```

- `limit`: how many points to draw. There are 28, so anything above that draws them all.
- `color_by`: the payload field that picks each dot's color. Our labels are inside `metadata`, so it's
  `metadata.title`.
- If the map stays blank, or **Data Panel** shows an error, add `"algorithm": "PCA"`. The default, UMAP, is made for
  thousands of points; PCA does better with 28.

Each dot is one chunk. The map squeezes each vector's 768 numbers into 2, so it shows roughly which chunks are near
each other, but its distances aren't the real scores.

Click a dot, and **Data Panel** shows that point's payload and, under **Similar points**, the points whose vectors are
closest to it, with their scores. On the map, the clicked dot and those neighbours stay bright, and the rest fade.
Clicking the MFA article's first chunk (its Title and Problem) gives:

![Qdrant's dashboard, Visualize tab, for it_knowledge_base. On the left, 28 dots: the clicked one circled, its nearest neighbours bright, the others faded. On the right, Data Panel shows the clicked point's payload: page_content "Title: MFA Setup Failure Problem: Employee cannot...", and metadata doc_id 1, title MFA Setup Failure, system MFA, category Security, priority High, tags mfa;authentication;mobile;security, start_index 0. Below it, Similar points lists 12 points with their scores, from 0.8691 down to 0.7558 for the last one, bd4a67d9-f0f7-4e02-bf5e-ea47122b9c8e.](images/dashboard-similar-points.png)

### What the Score Means: 0.7558

Each score is the cosine similarity between the clicked point's vector and that point's vector: how closely the two
point the same way.

- **1.0** means the same direction, the same meaning; **0** means unrelated.
- **0.7558**, the last one listed, means fairly similar: an angle of about 41° between the two vectors. The top one,
  **0.8691**, is about 30°.

It's the cosine from [How Qdrant Measures "Close": the Distance](#4-how-qdrant-measures-close-the-distance), below,
with 768 numbers instead of 2:

```text
cosine(a, b) = (a₁×b₁ + a₂×b₂ + … + a₇₆₈×b₇₆₈) / (length of a × length of b)
```

The collection uses cosine, so Qdrant stores every vector at length 1 (see
[Why Qdrant's Stored Numbers Differ From Gemini's](#5-why-qdrants-stored-numbers-differ-from-geminis)). Both lengths
are 1, so the score is just the sum of the 768 products: the two vectors multiplied number by number, then added up.
With 2 numbers, `[0.6, 0.8]` and `[0.8, 0.6]` give `0.6×0.8 + 0.8×0.6 = 0.96`. The Qdrant server does this sum
between the clicked point and every other point, and lists the highest first.

Reading the scores:

- **The order matters more than the values.** All 28 chunks are IT help-desk text, so to Gemini they're all fairly
  similar, and the scores sit close together: 0.76 to 0.87 here. What decides a search is which chunks score highest.
- **To see which chunk a score belongs to,** click the eye icon next to it.

### Check a Score Yourself

With Qdrant running and the venv active, in this folder, this reads two stored vectors from Qdrant and does the sum
itself, with no call to Gemini. Put in the id of the clicked point and the id of one point from its list:

```bash
python - <<'EOF'
from qdrant_client import QdrantClient
client = QdrantClient(url="http://localhost:6333", check_compatibility=False)
a, b = client.retrieve("it_knowledge_base", with_vectors=True,
                       ids=["f0f1e50f-598b-42f8-b135-f45456994f00", "bd4a67d9-f0f7-4e02-bf5e-ea47122b9c8e"])
print("length of a:", round(sum(x * x for x in a.vector) ** 0.5, 4))   # 1.0: stored at length 1
print("cosine:", round(sum(x * y for x, y in zip(a.vector, b.vector)), 4))
EOF
```

It prints `length of a: 1.0` and the same score as the dashboard: `0.7558` for the two points in the picture. Each run
of `pipeline.py` stores the points again, with new random ids, so copy the ids from the dashboard after your latest
run.

---

## 🎓 Key Concepts Demonstrated

### 1. A Vector Database Stores Points

A collection is a table of points, and each point has three parts: an id, a vector, and a payload. Here the payload
holds the chunk's text (`page_content`) and its labels (`metadata`), so whatever finds a vector also gets the text and
labels that go with it. `QdrantVectorStore` is LangChain's wrapper around a collection: give it chunks, and it embeds
them with the embedding model and stores the points.

### 2. A Server or In Memory

```python
QdrantClient(url="http://localhost:6333")    # the server: points kept between runs, seen in the dashboard
QdrantClient(":memory:")                     # inside the script: nothing outside can see them, gone at the end
```

The same code works with either: only the client differs. `QDRANT_URL` in `.env` picks the server; without it,
`pipeline.py` keeps Qdrant in memory.

### 3. Starting Fresh on Every Run

`QdrantVectorStore` gives each new point a random id. Storing the same 28 chunks twice would make 56 points, so
`make_vector_store()` deletes the collection first, if it's there, then makes it new. On the server, that's the
last run's collection. Each run embeds the chunks again too: one call to Gemini.

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

### 5. Why Qdrant's Stored Numbers Differ From Gemini's

With cosine, Qdrant stores each vector at length 1. It divides every number by the vector's length, which keeps the
direction:

![Normalized. A long grey arrow goes from the origin to [3, 4], length 5: what Gemini returns. A short blue arrow along the same line ends on a dashed circle of radius 1, at [0.6, 0.8]: what Qdrant stores. Every number is divided by 5. The direction, and so every cosine score, stays the same.](images/normalize.svg)

```text
Gemini returns:  [3, 4]        length √(3² + 4²) = 5
Qdrant stores:   [0.6, 0.8]    [3/5, 4/5], length 1
```

The meaning is the direction, and that doesn't change, so every cosine score stays the same. Qdrant does it so that
each search becomes a simple dot product, which is faster. It does this only with cosine; with Dot, Euclid and
Manhattan it stores the vectors exactly as they came. So if you compared the numbers Gemini returns for a chunk with
the vector stored here, they'd differ, by the same factor for every number in the vector.

### 6. Choosing a Distance

- **Use the distance the embedding model's documentation recommends.** For Gemini's embeddings, that's cosine.
- **It's fixed when the collection is created.** To change it, make a new collection and store the chunks again.
- **It decides what the scores mean.** With cosine and dot, higher is closer; with Euclid and Manhattan, lower is
  closer. This project uses cosine, so its scores read "the closer to 1, the closer the meaning".

### 7. One File Runs the Steps

`pipeline.py` is the only file that runs anything: `main()` runs Steps 1 and 2, printing a line each, then Step 3:
`connect()` picks the server or memory, `make_vector_store()` and `add_documents()` store the chunks, and
`print_points()` prints them; those two helpers are in `utils.py`. The other files only define the steps and the
helpers, so importing them makes no call. The model, its vector size and the server's address are parameters of
`main()`, so the tests pass a stand-in for Gemini and an in-memory Qdrant.

---

## 🛠️ Troubleshooting

**Issue**: `Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).`
**Fix**: There's no `.env` in this folder, and no `GOOGLE_API_KEY` in the environment. Do Step 4.

**Issue**: `Can't build the models: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Put your real key after `GOOGLE_API_KEY=`.

**Issue**: `Can't reach Qdrant at http://localhost:6333. Start it first, in this folder: docker compose up -d (or remove QDRANT_URL from .env to run Qdrant in memory).`
**Fix**: `QDRANT_URL` is set, but no server answers. `pipeline.py` stops before calling Gemini. Start the server
(Step 5), or run without Docker ([Or: Run It Without Docker](#or-run-it-without-docker)).

**Issue**: `no configuration file provided: not found`, from `docker compose up -d`
**Fix**: You're not in this folder: `docker-compose.yml` must be in the folder you run it from. Do Step 1, then
`ls docker-compose.yml` to check.

**Issue**: The dashboard says `No collection is present`
**Fix**: Nothing has been stored in this server yet. Check that, in what `python pipeline.py` prints, the line after
`Step 3: Embed and store` is `Qdrant: the server at ...`, then refresh the page (the ↻ next to **Collections**). If
it says `Qdrant: in memory, inside this script`, `.env` has no `QDRANT_URL` line, or it has a `#` in front: fix it,
and run `python pipeline.py` again.

**Issue**: `python vector_store.py` prints nothing
**Fix**: That file only defines the step. Run `python pipeline.py` (Step 6), which runs every step.

**Issue**: In Codespaces, the dashboard says `This ... page can't be found` with `HTTP ERROR 404`
**Fix**: That comes from Codespaces, not from Qdrant: nothing is answering on port 6333 inside the codespace. Check,
in the codespace's terminal:

1. **You're in this folder, with the latest code.** `docker-compose.yml` must be here:

   ```bash
   cd "projects/RAG/IT Knowledge Base/Basic/05-vector-store"   # from the repo root (/workspaces/AgenticProgramming)
   git pull
   ls docker-compose.yml
   ```

2. **Qdrant is running.** Start it, then look:

   ```bash
   docker compose up -d
   docker compose ps
   ```

   `docker compose ps` should list the qdrant service with `Up` in its status. If `up -d` printed an error, or `ps`
   lists nothing, Qdrant isn't running: the error says why.

3. **Qdrant answers inside the codespace:**

   ```bash
   curl http://localhost:6333
   ```

   A short JSON reply from Qdrant means it's working. `Connection refused` means it isn't running yet: go back to 2.

4. **The port is forwarded.** Once `curl` works, open the dashboard from the **Ports** tab, as in
   [Step 7: Open the Dashboard](#step-7-open-the-dashboard): the globe icon on the 6333 row, then `/dashboard`.
   Typing the address by hand can go wrong; the Ports tab's address can't.

---

## 📚 Next Steps

**[06 · Retriever](../06-retriever/README.md)**: this project stored the 28 chunks. 06 takes a question, turns it
into a vector with the same model, and asks Qdrant for the 5 closest chunks, with their scores.

**[Advanced · 05 · Vector Store](../../Advanced/05-vector-store/README.md)** (planned): the same project, production
grade. Its README lists what it will add.

### Ideas to Try

- In the Visualize tab, color the dots by `metadata.category` instead of `metadata.title`, and see which categories
  sit near each other.
- Click a chunk from another article, and compare its **Similar points** with the MFA one's.
- Run `python pipeline.py` twice and look at the ids in the dashboard: the same 28 chunks, with new random ids each
  time.
