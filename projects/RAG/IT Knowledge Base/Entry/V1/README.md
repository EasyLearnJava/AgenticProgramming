# Entry · V1 · RAG in a Notebook

The smallest version of the idea, in one Jupyter notebook: four sentences become vectors, the vectors go into a
vector database, and a question finds the closest sentences. Built with **sentence-transformers** (the library that
runs a small embedding model, `all-MiniLM-L6-v2`, on the CPU) and **Chroma** (a vector database, here in memory), in
five short code cells. Four more then look inside the vectors: their numbers, how alike they are, and two graphs of
them, in 2D and in 3D.

> **Needs:** a GitHub Codespace, or Linux or a Mac with Apple silicon, with Python 3.12 or newer (the NumPy it pins
> needs 3.12). The model runs inside the notebook. On Windows with long paths off, the packages may not install this
> deep in your folders: see [Troubleshooting](#️-troubleshooting).

---

## 🎯 What This Notebook Does

- **Loads an embedding model**, `all-MiniLM-L6-v2`, on the CPU: it turns any text into 384 numbers
- **Indexes four sentences** about landmarks in a Chroma collection, `demo`: it deletes the collection first if it's
  there, makes it fresh, then adds each sentence with its vector and an id
- **Answers a query**, "Where is the Eiffel Tower located?", with the 2 closest sentences
- **Tries a hybrid search**: it keeps only the sentences with "Eiffel" or "Paris" in them, then scores each one by how
  close its meaning is to the query
- **Looks inside the vectors**: the shape of the 4 × 384 matrix they make, and the first 10 numbers of each
- **Compares them**: the cosine similarity of every sentence with every other, and of the query with each sentence
- **Draws them**: PCA takes the 4 vectors and the query's from 384 numbers down to 2, for a graph of arrows, and
  to 3, for a graph you can turn with the mouse

It finds the closest sentences, prints them, then shows why: the query's vector points the same way as the Eiffel
Tower sentence's.

**Try it:** open `rag_basics.ipynb` and click **Run All**.

---

## 🏗️ Architecture

```text
Cell 1   import SentenceTransformer, util, chromadb
Cell 2   model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")   the model, downloaded the first time
              │
Cell 3   4 sentences ──> model.encode() ──> 4 vectors ──> Chroma collection "demo" (in memory)
              │
Cell 4   the query ──> model.encode() ──> 1 vector ──> collection.query(n_results=2)
                                                       ──> the 2 closest sentences
              │
Cell 5   sentences with "Eiffel" or "Paris" ──> util.cos_sim(query, sentence) ──> sorted by score
              │
Cell 6   the 4 vectors as one matrix ──> its shape (4, 384), and each vector's first 10 numbers
              │
Cell 7   cosine_similarity() ──> every sentence against every other, then the query against each
              │
Cell 8   the 4 vectors + the query's ──> PCA, 2 numbers each ──> a graph of 5 arrows (matplotlib)
              │
Cell 9   the same 5 vectors ──> PCA, 3 numbers each ──> a 3D graph you can turn (plotly)
```

### The Steps in This Notebook

1. **Import** → `SentenceTransformer` and `util` from sentence-transformers, and `chromadb`
2. **Load the model** → `all-MiniLM-L6-v2`, on the CPU
3. **Index** → a new `demo` collection; the 4 sentences embedded in one `model.encode()` call and added with ids
   `"0"` to `"3"`
4. **Query** → the question embedded the same way, then the 2 closest sentences from the collection
5. **Hybrid search and re-ranking** → a keyword filter first, then a cosine similarity score for each match
6. **Inside the embeddings** → the vectors from cells 3 and 4 as NumPy arrays; their shape, and each one's first 10
   numbers
7. **Cosine similarity** → scikit-learn's `cosine_similarity()`: every sentence against every other, then the query
   against each
8. **2D graph** → PCA keeps the 2 directions in which the 5 vectors differ most; an arrow for each, from the origin
9. **Interactive 3D graph** → the same with 3 directions, drawn by plotly: drag to turn it, hover over a point
   to read its sentence

---

## 📋 Prerequisites

- **A GitHub Codespace** on this repo, or Linux or a Mac with Apple silicon, with **Python 3.12 or newer**
- **The internet, the first time**: the model (about 90 MB) downloads from Hugging Face on the first run, then it's
  read from the disk

---

## 🚀 Quick Start

### Step 1: Open the Repo in a Codespace

On the repo's GitHub page: **Code** → **Codespaces** → **Create codespace on main**. VS Code opens in the browser,
with a terminal at the bottom.

### Step 2: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Entry/V1"   # from the repo root; quotes for the spaces
```

### Step 3: Create and Activate a Virtual Environment

```bash
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate
```

### Step 4: Install Dependencies

```bash
pip install -r requirements-dev.txt  # once: the notebook's packages, then pytest and nbclient for the tests
```

The notebook's packages, in `requirements.txt`: sentence-transformers, PyTorch, Chroma, NumPy, scikit-learn,
matplotlib, plotly (with pandas and nbformat, which it needs to draw in a notebook) and the kernel. PyTorch comes from
PyTorch's own CPU-only index, so the install skips NVIDIA's GPU libraries, which the model doesn't need.

### Step 5: Open the Notebook and Run All

1. Open `rag_basics.ipynb` from the Explorer on the left. If VS Code offers to install the Jupyter extension,
   install it.
2. Click **Select Kernel** (top right) → **Python Environments...** → the one whose path ends in
   `Entry/V1/.venv/bin/python`. If it isn't in the list: open the Command Palette (`Ctrl+Shift+P`), run
   **Python: Select Interpreter** → **Enter interpreter path...**, and give
   `projects/RAG/IT Knowledge Base/Entry/V1/.venv/bin/python`.
3. Click **Run All**.

The cells run top to bottom, and each one's output appears under it. The first run takes longer: cell 2 downloads the
model. What cells 3 to 5 print:

```text
Indexed documents: ['The Eiffel Tower is in Paris.', 'The Colosseum is in Rome.', 'The Statue of Liberty is in New York.', 'The Burj Khalifa is in Dubai.']

Basic RAG Results: ['The Eiffel Tower is in Paris.', 'The Burj Khalifa is in Dubai.']

Hybrid Search + Reranking Results:
The Eiffel Tower is in Paris. (score=0.8500)
```

Cells 1 and 2 print no results of their own, but they can show a loading bar and a warning or two from the model's
download (about `HF_TOKEN`, or `IProgress`); they're harmless. Cells 6 to 9 print the vectors' numbers and draw the
two graphs: see [Understanding the Output](#-understanding-the-output). The notebook is saved with the results of a
run, so GitHub shows them without running anything, all but the 3D graph: GitHub doesn't draw plotly's graphs, so it
shows only cell 9's coordinates. VS Code and Jupyter draw it.

You can also run one cell at a time: click a cell, then **Shift+Enter**. Run them in order: each cell uses what the
cells before it made.

---

## 📁 Project Structure

```text
V1/
├── rag_basics.ipynb                      # the notebook: 9 code cells, saved with their results
├── tests/
│   └── test_notebook.py                  # 9 tests: runs every cell, then checks what each one shows
├── requirements.txt                      # the notebook's packages and the kernel, pinned
├── requirements-dev.txt                  # requirements.txt plus pytest and nbclient, for the tests
├── pytest.ini                            # finds the tests in tests/
└── README.md                             # you are here
```

---

## 🧪 Testing

```bash
python -m pytest                     # 9 passed     (add -v for one line per test)
```

The tests run the whole notebook in a new kernel, as **Run All** does, with `nbclient`, then check what each cell
printed or drew: no cell fails; the four sentences are indexed; the query's 2 closest sentences, the Eiffel Tower
first; the hybrid search's one keyword match, with its score; 384 numbers for each sentence; the query most like the
Eiffel Tower sentence; the 2D graph drawn, with the query's point closest to the Eiffel Tower's; the 3D graph's 5
points, whose first 2 numbers are the 2D graph's; and that the results saved in the notebook are the ones a run
prints. They take a minute or two: the notebook runs once, in a new kernel.

---

## 📊 Understanding the Output

```text
Basic RAG Results: ['The Eiffel Tower is in Paris.', 'The Burj Khalifa is in Dubai.']
```

The Eiffel Tower sentence is the closest to the query. The Burj Khalifa comes second only because `n_results=2` asks
for two: Chroma always returns that many, however far the second one is. Here are the distances Chroma measured for
all four, with the cosine similarity of each (the score that cell 5 prints):

| Sentence | Chroma's distance | Cosine similarity |
|---|---|---|
| The Eiffel Tower is in Paris. | 0.3001 | 0.8500 |
| The Burj Khalifa is in Dubai. | 1.0206 | 0.4897 |
| The Statue of Liberty is in New York. | 1.4720 | 0.2640 |
| The Colosseum is in Rome. | 1.5320 | 0.2340 |

```text
Hybrid Search + Reranking Results:
The Eiffel Tower is in Paris. (score=0.8500)
```

Only one sentence has "Eiffel" or "Paris" in it, so the keyword filter keeps one, and the re-ranking has one score to
sort: 0.85, on a scale where 1 means the same meaning. The scores are rounded to 4 decimals, so on another computer
the last digit can come out one off.

```text
Documents vs documents:
[[1.    0.2   0.217 0.425]
 [0.2   1.    0.309 0.144]
 [0.217 0.309 1.    0.228]
 [0.425 0.144 0.228 1.   ]]

Query vs documents:
D1: 0.850  The Eiffel Tower is in Paris.
D2: 0.234  The Colosseum is in Rome.
D3: 0.264  The Statue of Liberty is in New York.
D4: 0.490  The Burj Khalifa is in Dubai.
```

Row 1 is the Eiffel Tower sentence (D1) against each of the four, in order, and so on down. The diagonal is 1: each
sentence against itself. The most alike pair is D1 and D4, the Eiffel Tower and the Burj Khalifa, at 0.425. The
query's scores are the table's above, rounded to 3 decimals: scikit-learn's `cosine_similarity()` measures what
`util.cos_sim()` does.

```text
2D coordinates:
D1: (-0.471, -0.216)  The Eiffel Tower is in Paris.
D2: (0.626, -0.506)  The Colosseum is in Rome.
D3: (0.535, 0.464)  The Statue of Liberty is in New York.
D4: (-0.249, 0.418)  The Burj Khalifa is in Dubai.
Q: (-0.441, -0.160)  Where is the Eiffel Tower located?
```

384 numbers can't be drawn, so PCA (principal component analysis) finds the 2 directions in which the 5 vectors
differ most, and gives each vector its position along them. PCA first takes away the average of the 5 vectors, so the
graph's origin is that average, and each arrow shows how one vector differs from it. Q's arrow lies along D1's: the
query and the Eiffel Tower sentence point the same way, which is why the search finds that sentence first. The 2
directions keep 71% of how the 5 vectors differ, so the graph is a picture of the distances, not the measure: cell 7's
similarities are.

```text
3D coordinates:
D1: (-0.471, -0.216, 0.238)
D2: (0.626, -0.506, -0.258)
D3: (0.535, 0.464, 0.400)
D4: (-0.249, 0.418, -0.563)
Q: (-0.441, -0.160, 0.183)
```

The first 2 numbers of each point are the 2D graph's: a third direction doesn't move the first two. With it, the
graph keeps 94% of how the vectors differ. Drag the graph to turn it, scroll to zoom, and hover over a point to read
its sentence.

---

## 🎓 Key Concepts Demonstrated

### 1. The Cells Share Their Variables

`model`, `documents`, `collection` and `query` are made in one cell and used in later ones. The kernel, the Python
behind the notebook, keeps them between cells until it restarts. That's why the cells must run in order, and why the
notebook needs no functions or files of its own: each cell is a few lines that use the ones before.

### 2. A Fresh Collection on Every Run

```python
try:
    chroma_client.delete_collection("demo")
except:
    pass

collection = chroma_client.create_collection("demo")
```

Without the delete, running cell 3 a second time in the same kernel would stop at `create_collection()`, with
`InternalError: Collection [demo] already exists`. Deleting it first, then creating it, starts from nothing every
time. On the first run there's no `demo` yet, so `delete_collection()` raises `NotFoundError`, and the bare `except:`
catches it. It catches every other error too, which is why real code names the error it expects.

### 3. One Model for the Sentences and the Question

The sentences (cell 3) and the query (cell 4) go through the same `model.encode()`, so their 384 numbers can be
compared. A vector from another model would be a different set of numbers, and the distances would mean nothing.

### 4. Distance and Similarity Are the Same Measure

Chroma ranks by distance, `l2` by default, the squared straight-line distance: smaller is closer. `util.cos_sim()`
gives similarity: larger is closer. This model's vectors all have length 1, so the two always agree: Chroma's
distance is 2 − 2 × the cosine similarity. For the Burj Khalifa, 1.0206 = 2 − 2 × 0.4897.

### 5. Hybrid Search: Keywords, Then Meaning

Cell 5 combines two kinds of search: an exact word match (`"Eiffel" in doc`), then the model's score for each match.
The keyword step is a plain Python filter with the words written in: a demo of the idea, made for this one query.

---

## 🛠️ Troubleshooting

**Issue**: On Windows, `pip install` stops with `ERROR: Could not install packages due to an OSError: [Errno 2] No such file or directory: '...\.venv\Lib\site-packages\jedi\third_party\typeshed\stubs\oauthlib\oauthlib\oauth2\rfc6749\grant_types\resource_owner_password_credentials.pyi'` and `HINT: This error might have occurred since this system does not have Windows Long Path support enabled.`
**Fix**: The notebook's kernel needs `jedi`, and one of its files ends up more than 260 characters from the drive
letter when the repo sits deep in your folders. Windows refuses longer paths unless long paths are on. Run it in a
Codespace instead (Step 1).

**Issue**: `NameError: name 'model' is not defined`
**Fix**: A cell ran before the cell that makes what it uses: here, cell 3 before cell 2. Run the cells in order, or
use **Run All**. After the kernel restarts, run them all again: a restart forgets every variable.

**Issue**: `ModuleNotFoundError: No module named 'sentence_transformers'`
**Fix**: The notebook is running on a Python without the packages. Pick the `.venv` kernel (Step 5), or install the
packages into it (Step 4).

**Issue**: Cells 1 to 5 run, then cell 6, 7, 8 or 9 stops with `ModuleNotFoundError: No module named 'sklearn'`, or
`'matplotlib'`, or `'plotly'`, or cell 9 with `ValueError: Mime type rendering requires nbformat>=4.2.0 but it is not installed`
**Fix**: The kernel's `.venv` has the search packages but not the graphs'. Install `requirements.txt` into it again
(Step 4), then click **Restart** at the top of the notebook, and **Run All**.

---

## 📚 Next Steps

**[Entry · V2 · Parent-Doc and Window Retrieval](../V2/README.md)**: this notebook searched four one-line sentences.
V2 searches four longer documents two ways, whole and cut into sentences, and tries the question reworded.

### Ideas to Try

- Ask another question in cell 4, such as `"Which landmark is in Italy?"`, and see which sentences come back
- Set `n_results=1` in cell 4, so only the closest sentence returns
- Add a sentence to `documents` in cell 3, then **Run All**: it gets its own arrow in the graphs
- Change the keywords in cell 5 to match your new question
