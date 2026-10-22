# Entry · V3 · Cross-Encoder Reranking

Eight one-line documents, searched in two stages in one Jupyter notebook: an embedding model (a bi-encoder) finds the
3 closest to a question, then a cross-encoder reads the question with each of the 3 and scores it again. Precision@1
then checks whether the first result is the right one, before and after. Built with **sentence-transformers** (the
library that runs both models on the CPU) and **Chroma** (a vector database, here in memory), in five short code
cells.

> **Needs:** a GitHub Codespace, or Linux or a Mac with Apple silicon, with Python 3.12 or newer (the NumPy it pins
> needs 3.12). The models run inside the notebook. On Windows with long paths off, the packages may not install this
> deep in your folders: see [Troubleshooting](#️-troubleshooting).

---

## 🎯 What This Notebook Does

- **Loads two models** on the CPU: the bi-encoder `all-MiniLM-L6-v2`, which turns any text into 384 numbers, and the
  cross-encoder `cross-encoder/ms-marco-MiniLM-L-6-v2`, which reads a question and a document together and gives one
  score
- **Indexes eight documents**, four of them about Paris, in a Chroma collection, `demo`: it deletes the collection
  first if it's there, makes it fresh, then adds each document with its vector
- **Baseline retrieval**: the 3 documents closest to "Where is the Eiffel Tower located?", by the bi-encoder
- **Cross-encoder reranking**: the question paired with each of those 3, scored by the cross-encoder, and sorted by
  score
- **Compares precision@1**: whether the first result contains "Eiffel Tower", for the baseline and for the reranked
  list

**Try it:** open `rag_basics.ipynb` and click **Run All**.

---

## 🏗️ Architecture

```text
Cell 1   bi_model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
         cross_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", device="cpu")
              │
Cell 2   8 documents ──> bi_model.encode() ──> 8 vectors ──> Chroma collection "demo" (in memory)
              │
Cell 3   the question ──> bi_model.encode() ──> collection.query(n_results=3) ──> baseline_results: 3 documents
              │
Cell 4   (question, document) × 3 ──> cross_model.predict() ──> 3 scores ──> reranked: sorted by score
              │
Cell 5   precision_at_1(baseline_results), precision_at_1(reranked): is "Eiffel Tower" in the first one?
```

### The Steps in This Notebook

1. **Import and load the models** → `SentenceTransformer`, `CrossEncoder` and `util`, `chromadb`, and `numpy` as
   `np`; the bi-encoder and the cross-encoder, both on the CPU
2. **Index** → a new `demo` collection; the 8 documents embedded by the bi-encoder in one call and added with ids
   `"0"` to `"7"`
3. **Baseline retrieval** → the question embedded the same way; the 3 closest documents
4. **Cross-encoder reranking** → one score for each (question, document) pair; the documents sorted by it, highest
   first
5. **Precision@1** → 1 if the first document contains "Eiffel Tower", else 0, for each list

---

## 📋 Prerequisites

- **A GitHub Codespace** on this repo, or Linux or a Mac with Apple silicon, with **Python 3.12 or newer**: the NumPy
  version in `requirements.txt` needs 3.12
- **The internet, the first time**: the two models (about 90 MB each) download from Hugging Face on the first run,
  then they're read from the disk

---

## 🚀 Quick Start

### Step 1: Open the Repo in a Codespace

On the repo's GitHub page: **Code** → **Codespaces** → **Create codespace on main**. VS Code opens in the browser,
with a terminal at the bottom.

### Step 2: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Entry/V3"   # from the repo root; quotes for the spaces
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
the models don't need.

### Step 5: Open the Notebook and Run All

1. Open `rag_basics.ipynb` from the Explorer on the left. If VS Code offers to install the Jupyter extension,
   install it.
2. Click **Select Kernel** (top right) → **Python Environments...** → the one whose path ends in
   `Entry/V3/.venv/bin/python`. If it isn't in the list: open the Command Palette (`Ctrl+Shift+P`), run
   **Python: Select Interpreter** → **Enter interpreter path...**, and give
   `projects/RAG/IT Knowledge Base/Entry/V3/.venv/bin/python`.
3. Click **Run All**.

The cells run top to bottom, and each one's output appears under it. The first run takes longer: cell 1 downloads the
two models. What the last three cells print:

```text
Baseline Retrieval Results:
- The Eiffel Tower is in Paris.
- Montparnasse Tower is in Paris.
- Tokyo Tower is in Tokyo.

Reranked Results (Cross-Encoder):
- The Eiffel Tower is in Paris. (score=9.3069)
- Montparnasse Tower is in Paris. (score=-0.3279)
- Tokyo Tower is in Tokyo. (score=-4.3100)

Precision@1 Baseline: 1
Precision@1 Reranked: 1
```

Cell 2 prints nothing. Cell 1 can show loading bars and a warning or two from the models' download (about
`HF_TOKEN`, or `IProgress`); they're harmless. The notebook is saved with the results above, so GitHub shows them
without running anything.

You can also run one cell at a time: click a cell, then **Shift+Enter**. Run them in order: each cell uses what the
cells before it made.

---

## 📁 Project Structure

```text
V3/
├── rag_basics.ipynb                      # the notebook: 5 code cells, saved with their results
├── tests/
│   └── test_notebook.py                  # 5 tests: runs every cell, then checks what each one printed
├── requirements.txt                      # sentence-transformers, PyTorch (CPU), Chroma, NumPy, the kernel, pinned
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
printed: no cell fails, and the first two print nothing; the exact baseline results; the reranked results, in the same
order, the first score above 0 and the others below; precision@1 of 1 for both; and that the results saved in the
notebook are the ones a run prints, the scores to within 0.001. They take a minute or two: the notebook runs once, in
a new kernel.

---

## 📊 Understanding the Output

Both models, for all eight documents, ranked by the bi-encoder's distance (smaller is closer). The cross-encoder's
score is higher for a better match:

| Bi-encoder rank | Document | Bi-encoder distance | Cross-encoder score |
|---|---|---|---|
| **1** | The Eiffel Tower is in Paris. | 0.3001 | **9.3069** |
| **2** | Montparnasse Tower is in Paris. | 0.8931 | **-0.3279** |
| **3** | Tokyo Tower is in Tokyo. | 0.9810 | **-4.3100** |
| 4 | The Burj Khalifa is in Dubai. | 1.0206 | -1.4479 |
| 5 | Notre Dame Cathedral is in Paris. | 1.2047 | -7.6684 |
| 6 | The Louvre Museum is in Paris. | 1.2071 | -6.4017 |
| 7 | The Statue of Liberty is in New York. | 1.4720 | -6.8533 |
| 8 | The Colosseum is in Rome. | 1.5320 | -8.0050 |

The 3 in bold are the ones the notebook prints. The cross-encoder agrees with the bi-encoder's order for those 3, so
reranking doesn't move anything, and the Eiffel Tower is first both times: precision@1 is 1, then 1.

The other two the bi-encoder found are the other towers, ahead of the Louvre and Notre Dame, the two Paris documents
it didn't pick. The cross-encoder scored all eight here only to fill this table; the notebook scores the 3 candidates
alone.

---

## 🎓 Key Concepts Demonstrated

### 1. Two Kinds of Model

The bi-encoder turns each text into a vector on its own, so the documents' vectors are made once, in cell 2, and a
question needs only its own vector. The cross-encoder reads the question and a document together and gives one score
for the pair; there's nothing to store ahead of time, so it scores each pair when the question comes: 3 pairs here,
in one `predict()` call.

### 2. Retrieve, Then Rerank

```python
pairs = [(query, doc) for doc in baseline_results]
scores = cross_model.predict(pairs)
```

Cell 4 scores only the 3 documents cell 3 found. The table above shows what that means: the cross-encoder scores the
Burj Khalifa (-1.4479) higher than Tokyo Tower (-4.3100), but the Burj Khalifa is fourth for the bi-encoder, so it's
never a candidate. Reranking can only change the order of what the first search found.

### 3. The Cross-Encoder's Scores Are Raw

`cross_model.predict()` gives this model's scores as they come out, not squashed between 0 and 1: 9.3069 is a strong
match, and the negative ones are weak. Only their order is used: the documents are sorted by them.

### 4. Precision@1

```python
def precision_at_1(results):
    return int(any("Eiffel Tower" in doc for doc in results[:1]))
```

It looks at the first result only (`results[:1]`): 1 if it contains "Eiffel Tower", 0 if not. The notebook assumes
that's the right answer for this question, as its comment says. Here the bi-encoder already put the Eiffel Tower
first, so both lists score 1.

### 5. Imported, Not Used

Cell 1 imports `util` from sentence-transformers and `numpy` as `np`; no cell uses either of them.

---

## 🛠️ Troubleshooting

**Issue**: On Windows, `pip install` stops with `ERROR: Could not install packages due to an OSError: [Errno 2] No such file or directory: '...\.venv\Lib\site-packages\jedi\third_party\typeshed\stubs\oauthlib\oauthlib\oauth2\rfc6749\grant_types\resource_owner_password_credentials.pyi'` and `HINT: This error might have occurred since this system does not have Windows Long Path support enabled.`
**Fix**: The notebook's kernel needs `jedi`, and one of its files ends up more than 260 characters from the drive
letter when the repo sits deep in your folders. Windows refuses longer paths unless long paths are on. Run it in a
Codespace instead (Step 1).

**Issue**: `NameError: name 'baseline_results' is not defined`
**Fix**: Cell 4 ran before cell 3, which makes `baseline_results`. Run the cells in order, or use **Run All**. After
the kernel restarts, run them all again: a restart forgets every variable.

**Issue**: `ModuleNotFoundError: No module named 'sentence_transformers'`
**Fix**: The notebook is running on a Python without the packages. Pick the `.venv` kernel (Step 5), or install the
packages into it (Step 4).

---

## 📚 Next Steps

**[Basic · 01 · Read the Knowledge Base](../../Basic/01-read-the-knowledge-base/README.md)**: this notebook indexed
eight documents written in its code. 01 reads a real knowledge base, a CSV file of 10 IT support articles, into
LangChain Documents.

### Ideas to Try

- Set `n_results=8` in cell 3, so the cross-encoder reranks all eight, and see where the Burj Khalifa lands
- Ask about another Paris landmark in cell 3, and change "Eiffel Tower" in cell 5 to match
- Add a document that mentions the Eiffel Tower without being about it, and see which model ranks it higher
