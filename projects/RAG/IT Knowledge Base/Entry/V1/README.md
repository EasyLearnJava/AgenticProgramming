# Entry · V1 · RAG in a Notebook

The smallest version of the idea, in one Jupyter notebook: four sentences become vectors, the vectors go into a
vector database, and a question finds the closest sentences. Built with **sentence-transformers** (the library that
runs a small embedding model, `all-MiniLM-L6-v2`, on the CPU) and **Chroma** (a vector database, here in memory), in
five short code cells.

> **Needs:** a GitHub Codespace, or Linux or a Mac with Apple silicon, with Python 3.11 or newer. The model runs
> inside the notebook. On Windows with long paths off, the packages may not install this deep in your folders: see
> [Troubleshooting](#️-troubleshooting).

---

## 🎯 What This Notebook Does

- **Loads an embedding model**, `all-MiniLM-L6-v2`, on the CPU: it turns any text into 384 numbers
- **Indexes four sentences** about landmarks in a Chroma collection, `demo`: it deletes the collection first if it's
  there, makes it fresh, then adds each sentence with its vector and an id
- **Answers a query**, "Where is the Eiffel Tower located?", with the 2 closest sentences
- **Tries a hybrid search**: it keeps only the sentences with "Eiffel" or "Paris" in them, then scores each one by how
  close its meaning is to the query

It finds the closest sentences and prints them.

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
```

### The Steps in This Notebook

1. **Import** → `SentenceTransformer` and `util` from sentence-transformers, and `chromadb`
2. **Load the model** → `all-MiniLM-L6-v2`, on the CPU
3. **Index** → a new `demo` collection; the 4 sentences embedded in one `model.encode()` call and added with ids
   `"0"` to `"3"`
4. **Query** → the question embedded the same way, then the 2 closest sentences from the collection
5. **Hybrid search and re-ranking** → a keyword filter first, then a cosine similarity score for each match

---

## 📋 Prerequisites

- **A GitHub Codespace** on this repo, or Linux or a Mac with Apple silicon, with **Python 3.11 or newer**
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
pip install -r requirements-dev.txt  # once: sentence-transformers, PyTorch (CPU only), Chroma, the kernel, pytest
```

`requirements.txt` gets PyTorch from PyTorch's own CPU-only index, so the install skips NVIDIA's GPU libraries, which
the model doesn't need.

### Step 5: Open the Notebook and Run All

1. Open `rag_basics.ipynb` from the Explorer on the left. If VS Code offers to install the Jupyter extension,
   install it.
2. Click **Select Kernel** (top right) → **Python Environments...** → the one whose path ends in
   `Entry/V1/.venv/bin/python`. If it isn't in the list: open the Command Palette (`Ctrl+Shift+P`), run
   **Python: Select Interpreter** → **Enter interpreter path...**, and give
   `projects/RAG/IT Knowledge Base/Entry/V1/.venv/bin/python`.
3. Click **Run All**.

The cells run top to bottom, and each one's output appears under it. The first run takes longer: cell 2 downloads the
model. What the last three cells print:

```text
Indexed documents: ['The Eiffel Tower is in Paris.', 'The Colosseum is in Rome.', 'The Statue of Liberty is in New York.', 'The Burj Khalifa is in Dubai.']

Basic RAG Results: ['The Eiffel Tower is in Paris.', 'The Burj Khalifa is in Dubai.']

Hybrid Search + Reranking Results:
The Eiffel Tower is in Paris. (score=0.8500)
```

Cells 1 and 2 print no results of their own, but they can show a loading bar and a warning or two from the model's
download (about `HF_TOKEN`, or `IProgress`); they're harmless. The notebook is saved with the results above, so
GitHub shows them without running anything.

You can also run one cell at a time: click a cell, then **Shift+Enter**. Run them in order: each cell uses what the
cells before it made.

---

## 📁 Project Structure

```text
V1/
├── rag_basics.ipynb                      # the notebook: 5 code cells, saved with their results
├── tests/
│   └── test_notebook.py                  # 5 tests: runs every cell, then checks what each one printed
├── requirements.txt                      # sentence-transformers, PyTorch (CPU), Chroma and the kernel, pinned
├── requirements-dev.txt                  # requirements.txt plus pytest, nbclient and nbformat, for the tests
├── pytest.ini                            # finds the tests in tests/
└── README.md                             # you are here
```

---

## 🧪 Testing

```bash
python -m pytest                     # 5 passed     (add -v for one line per test)
```

The tests run the whole notebook in a new kernel, as **Run All** does, with `nbclient`, then check what each cell
printed: no cell fails; the four sentences are indexed; the query's 2 closest sentences, the Eiffel Tower first; the
hybrid search's one keyword match, with its score; and that the results saved in the notebook are the ones a run
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

---

## 📚 Next Steps

**[Entry · V2 · Parent-Doc and Window Retrieval](../V2/README.md)**: this notebook searched four one-line sentences.
V2 searches four longer documents two ways, whole and cut into sentences, and tries the question reworded.

### Ideas to Try

- Ask another question in cell 4, such as `"Which landmark is in Italy?"`, and see which sentences come back
- Set `n_results=1` in cell 4, so only the closest sentence returns
- Add a sentence to `documents` in cell 3, then run cells 3 to 5 again
- Change the keywords in cell 5 to match your new question
