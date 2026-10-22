# Entry · V2 · Parent-Doc and Window Retrieval

Four short documents, stored two ways in one Jupyter notebook: whole, and cut into sentences ("windows"). A question
finds the closest whole documents; then the same question, reworded by hand, is searched in both. Built with
**sentence-transformers** (the library that runs a small embedding model, `all-MiniLM-L6-v2`, on the CPU) and
**Chroma** (a vector database, here in memory), in six short code cells.

> **Needs:** a GitHub Codespace, or Linux or a Mac with Apple silicon, with Python 3.11 or newer. The model runs
> inside the notebook. On Windows with long paths off, the packages may not install this deep in your folders: see
> [Troubleshooting](#️-troubleshooting).

---

## 🎯 What This Notebook Does

- **Loads an embedding model**, `all-MiniLM-L6-v2`, on the CPU: it turns any text into 384 numbers
- **Indexes four documents twice**, in two Chroma collections: `docs` holds each document whole; `windows` holds each
  sentence on its own, 6 in all. It deletes both collections first if they're there
- **Parent-doc retrieval**: the 2 documents closest to "Where is the Statue of Liberty?"
- **Simple query reformulation**: the same question reworded by hand, "Statue of Liberty location New York", and the
  2 closest documents to that
- **Window retrieval**: the 2 sentences closest to the reworded question

It prints the results of the last three, so you can compare a whole-document search with a sentence search.

**Try it:** open `rag_basics.ipynb` and click **Run All**.

---

## 🏗️ Architecture

```text
Cell 1   import SentenceTransformer, chromadb; model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
              │
Cell 2   4 documents ──> model.encode() ──> collection "docs"      (4 points, ids d0 to d3)
           │
           └─> split at ". " ──> 6 sentences ──> model.encode() ──> collection "windows"   (6 points, w0 to w5)
              │
Cell 3   "Where is the Statue of Liberty?" ──> model.encode() ──> q_emb
              │
Cell 4   q_emb ──> "docs" ──> the 2 closest documents
Cell 5   "Statue of Liberty location New York" ──> model.encode() ──> q_ref_emb ──> "docs" ──> the 2 closest documents
Cell 6   q_ref_emb ──> "windows" ──> the 2 closest sentences
```

### The Steps in This Notebook

1. **Import and load the model** → `SentenceTransformer` and `chromadb`; `all-MiniLM-L6-v2` on the CPU
2. **Index** → delete `docs` and `windows` if they're there; add the 4 documents to `docs`, then each sentence to
   `windows`
3. **Embed the question** → "Where is the Statue of Liberty?" becomes `q_emb`; nothing is searched yet
4. **Parent-doc retrieval** → search `docs` with `q_emb`
5. **Query reformulation** → embed the reworded question, `q_ref_emb`, and search `docs` with it
6. **Window retrieval** → search `windows` with `q_ref_emb`

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
cd "projects/RAG/IT Knowledge Base/Entry/V2"   # from the repo root; quotes for the spaces
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
   `Entry/V2/.venv/bin/python`. If it isn't in the list: open the Command Palette (`Ctrl+Shift+P`), run
   **Python: Select Interpreter** → **Enter interpreter path...**, and give
   `projects/RAG/IT Knowledge Base/Entry/V2/.venv/bin/python`.
3. Click **Run All**.

The cells run top to bottom, and each one's output appears under it. The first run takes longer: cell 1 downloads the
model. What the last three cells print:

```text
Parent-doc results: [['The Statue of Liberty is a gift from France, located in New York, USA.', 'The Colosseum is in Rome, Italy. It is an ancient amphitheater.']]
Reformulated results: [['The Statue of Liberty is a gift from France, located in New York, USA.', 'The Eiffel Tower is in Paris, France. It is one of the most famous landmarks.']]
Window results: [['The Statue of Liberty is a gift from France, located in New York, USA.', 'It is one of the most famous landmarks.']]
```

Cells 2 and 3 print nothing. Cell 1 can show a loading bar and a warning or two from the model's download (about
`HF_TOKEN`, or `IProgress`); they're harmless. The notebook is saved with the results above, so GitHub shows them
without running anything.

You can also run one cell at a time: click a cell, then **Shift+Enter**. Run them in order: each cell uses what the
cells before it made.

---

## 📁 Project Structure

```text
V2/
├── rag_basics.ipynb                      # the notebook: 6 code cells, saved with their results
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
printed: no cell fails, and the first three print nothing; the exact results of the parent-doc search, the reworded
search and the window search; and that the results saved in the notebook are the ones a run prints. They take a
minute or two: the notebook runs once, in a new kernel.

---

## 📊 Understanding the Output

Each result is a list inside a list, `[[...]]`: `query()` can take several questions at once, and gives one list of
results per question. Here there's one question, so one inner list.

Chroma's distance for every document and sentence, for each search (smaller is closer):

| Searched | Parent-doc, cell 4 | Reworded, cell 5 |
|---|---|---|
| The Statue of Liberty is a gift from France, located in New York, USA. | **0.4995** | **0.4119** |
| The Colosseum is in Rome, Italy. It is an ancient amphitheater. | **1.2956** | 1.4376 |
| The Eiffel Tower is in Paris, France. It is one of the most famous landmarks. | 1.3324 | **1.4227** |
| The Burj Khalifa in Dubai is the tallest building in the world. | 1.5226 | 1.5808 |

| Sentence (window) | Window, cell 6 |
|---|---|
| The Statue of Liberty is a gift from France, located in New York, USA. | **0.4119** |
| It is one of the most famous landmarks. | **1.1166** |
| The Colosseum is in Rome, Italy | 1.4034 |
| It is an ancient amphitheater. | 1.5399 |
| The Eiffel Tower is in Paris, France | 1.5434 |
| The Burj Khalifa in Dubai is the tallest building in the world. | 1.5808 |

The 2 in bold are the ones each cell printed. The Statue of Liberty comes first every time, and closer with the
reworded question (0.4119 against 0.4995). The second place is always far behind: `n_results=2` asks for two, and
Chroma returns two, however far the second one is. With the reworded question, the Eiffel Tower passes the
Colosseum by a small margin, 1.4227 against 1.4376.

---

## 🎓 Key Concepts Demonstrated

### 1. Two Collections From the Same Documents

```python
windows = [s for d in docs for s in d.split(". ") if s]
```

`docs` stores each document whole: 4 points. `windows` stores its sentences: each document is split wherever a full
stop is followed by a space, giving 6 sentences. `if s` would drop an empty piece; these documents have none. The
split takes the full stop with it, so a first sentence loses its own: `'The Eiffel Tower is in Paris, France'`. The
Statue of Liberty and Burj Khalifa documents are one sentence each, so they're the same in both collections, at the
same distance.

### 2. Parent-Doc Retrieval in This Notebook

Cell 4 searches `docs`, so each match is a whole document, compared by its own vector, and the text around the answer
comes with it. Here the two collections are kept apart: nothing links a window to the document it came from (the ids
are `d0` to `d3` and `w0` to `w5`).

### 3. Reformulating the Question

`"Statue of Liberty location New York"` drops "Where is the" and adds "location New York", words the Statue of
Liberty document shares ("located in New York"). Its vector lands closer to that document (0.4119) than the original
question's did (0.4995). The rewording is written by hand in the cell.

### 4. Small Windows Match, but Lose What's Around Them

Cell 6's second result is `'It is one of the most famous landmarks.'`: a sentence from the Eiffel Tower document,
which doesn't say which landmark it means. A window can match a question closely, but on its own it can lose what
the sentences around it said. The whole documents in cell 5 keep that.

### 5. The Cells Share Their Variables

`model`, `doc_col`, `win_col`, `q_emb` and `q_ref_emb` are made in one cell and used in later ones. Cell 6 searches
with `q_ref_emb`, made in cell 5, so cell 5 must run before cell 6.

---

## 🛠️ Troubleshooting

**Issue**: On Windows, `pip install` stops with `ERROR: Could not install packages due to an OSError: [Errno 2] No such file or directory: '...\.venv\Lib\site-packages\jedi\third_party\typeshed\stubs\oauthlib\oauthlib\oauth2\rfc6749\grant_types\resource_owner_password_credentials.pyi'` and `HINT: This error might have occurred since this system does not have Windows Long Path support enabled.`
**Fix**: The notebook's kernel needs `jedi`, and one of its files ends up more than 260 characters from the drive
letter when the repo sits deep in your folders. Windows refuses longer paths unless long paths are on. Run it in a
Codespace instead (Step 1).

**Issue**: `NameError: name 'q_ref_emb' is not defined`
**Fix**: Cell 6 ran before cell 5, which makes `q_ref_emb`. Run the cells in order, or use **Run All**. After the
kernel restarts, run them all again: a restart forgets every variable.

**Issue**: `ModuleNotFoundError: No module named 'sentence_transformers'`
**Fix**: The notebook is running on a Python without the packages. Pick the `.venv` kernel (Step 5), or install the
packages into it (Step 4).

---

## 📚 Next Steps

**[Basic · 01 · Read the Knowledge Base](../../Basic/01-read-the-knowledge-base/README.md)**: this notebook indexed
four documents written in its code. 01 reads a real knowledge base, a CSV file of 10 IT support articles, into
LangChain Documents.

### Ideas to Try

- Search `windows` with `q_emb`, the original question, in cell 6, and compare
- Set `n_results=3` in cell 4, so the third-closest document returns too
- Write your own rewording in cell 5, such as `"Statue of Liberty New York USA"`
- Add a document with three sentences to `docs` in cell 2, then run cells 2 to 6 again
