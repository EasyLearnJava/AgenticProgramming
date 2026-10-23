# 01 · Read the Knowledge Base

Read the IT knowledge base, a CSV file of 10 IT support articles, into LangChain `Document`s: one per article, each
with its text and where it came from, and print them. Built with **LangChain** and Python's `csv` module.

> **Needs:** Python 3.11 or newer, and nothing else: this project only reads a local file.

---

## 🎯 What This Project Does

- **Reads** `data/sample_it_kb.csv`, one row at a time
- **Turns each row into a LangChain `Document`**: its `page_content` has one `column: value` line per column
- **Records where each one came from** in its `metadata`: the file's name and the row number
- **Prints** how many there are, each one's title, then every `Document` in full
- **Runs from one file**, `pipeline.py`, which names each step, then runs it

The happy path only: the file is there, and every row is a good article.

**Try it:** `python pipeline.py`, and see the 10 articles the way LangChain holds them.

---

## 🏗️ Architecture

```text
┌──────────────────────────┐
│   pipeline.py: main()    │  ← the one file to run: calls each step in order
└────────────┬─────────────┘
             │ Step 1: Read the knowledge base
             ↓
┌──────────────────────────┐
│   load_documents()       │  ← KBLoader(path).load(): configure with the file, then load it
│   └─ KBLoader.lazy_load()│     reads data/sample_it_kb.csv (10 rows × 8 columns) one row at a time:
│                          │       row → Document(page_content, metadata)
└────────────┬─────────────┘
             │ 10 Documents
             ↓
┌──────────────────────────┐
│    print_documents()     │  ← utils.py: the count, the titles, then every Document
└──────────────────────────┘
```

### The Pipeline in This Project

1. **Run** → `python pipeline.py`: `main()` prints each step's name, then runs it
2. **Load** → `load_documents()` makes a `KBLoader` that stores which file to read, then calls its `load()`
3. **Read** → `csv.DictReader` gives each row as `{column: value}`
4. **Convert** → each row becomes a `Document`: its text, and where it came from
5. **Print** → `print_documents()`, from `utils.py`: the count and the titles, then every `Document`

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- Nothing else: once the packages are installed, it runs without a network

---

## 🚀 Quick Start

### Step 1: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Basic/01-read-the-knowledge-base"   # from the repo root; quotes for the spaces
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
pip install -r requirements-dev.txt  # once: langchain-core and pytest, into .venv/
```

### Step 4: Run It

```bash
python pipeline.py
```

### Or: Run It in One Command

This one command does Steps 2 to 4 for you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/01-read-the-knowledge-base   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs
`python pipeline.py` in this folder with the venv's Python, so there's nothing to activate. The output is the same as
in Step 4.

---

## 🧪 Testing

```bash
python -m pytest                     # 12 passed     (add -v for one line per test)
```

The tests read the sample file and run `pipeline.py` as its own process: 10 Documents, every column as a line in
order, the metadata, the first one is the VPN article, making the loader reads nothing, `load()` and `lazy_load()`
agree, the printed output, the same output whichever folder it's started from, that `knowledge_base.py` and
`utils.py` run on their own print nothing, and what `print_documents()` prints for two Documents, and for none.

---

## 🎓 Key Concepts Demonstrated

### 1. A Document: Text + Metadata

```python
Document(page_content="title: VPN Connection Timeout\nproblem: ...", metadata={"source": "sample_it_kb.csv", "row": 0})
```

`page_content` is the article's text; `metadata` travels with it and says where that text came from: the file, and
the row.

### 2. Configure First, Load Later

```python
loader = KBLoader(KB_FILE)   # says what to do: which file. Nothing is read yet.
docs = loader.load()         # does it: this is the line that reads the file.
```

The settings go in first, and the work happens only when it's asked for. `load_documents()` does both, as
`KBLoader(path).load()`, so the pipeline needs one line: `docs = load_documents()`.

### 3. `lazy_load()` and `load()`

`lazy_load()` hands out one Document at a time, so even a very large file never has to be in memory all at once.
`load()`, from LangChain's `BaseLoader`, just collects them into a list.

### 4. A Path From the File, Not From Where You Run It

```python
KB_FILE = Path(__file__).resolve().parent / "data" / "sample_it_kb.csv"
```

`Path(__file__).resolve().parent` is the folder `knowledge_base.py` is in, so the data file is found whichever
folder you start `pipeline.py` from. A bare `"data/sample_it_kb.csv"` would be looked for in the current folder.

### 5. One File Runs the Steps

```python
def main() -> None:
    print("Step 1: Read the knowledge base")
    docs = load_documents()
    print_documents(docs)


if __name__ == "__main__":
    main()
```

`pipeline.py` is the only file that runs anything: `main()` names each step, then runs it, in order.
`knowledge_base.py` only defines the step, and `utils.py` the helper that prints its result, so importing
them, as the tests do, reads and prints nothing. A new step is one more part of `main()`. `if __name__ == "__main__":`
is true only in the file you run, so `main()` runs from `python pipeline.py`, and not when the file is imported.

### 6. The Step Apart From the Helpers

```python
from knowledge_base import load_documents   # the step: reading the knowledge base
from utils import print_documents           # a helper: showing what was read
```

`knowledge_base.py` holds only what reading the knowledge base needs. Printing the Documents is something the
pipeline does with them, not part of reading them, so it lives in `utils.py`. Each file then has one job.

---

## 🛠️ Troubleshooting

**Issue**: `ModuleNotFoundError: No module named 'langchain_core'`
**Fix**: The venv isn't active, or the packages aren't installed in it. Activate it (Step 2), then
`pip install -r requirements-dev.txt` (Step 3).

**Issue**: `FileNotFoundError: [Errno 2] No such file or directory: '.../data/sample_it_kb.csv'`
**Fix**: The data file is missing from this folder's `data/`. Put `sample_it_kb.csv` back there.

**Issue**: `python knowledge_base.py` or `python utils.py` prints nothing
**Fix**: Those files only define the step and its helper. Run `python pipeline.py` (Step 4), which runs them.

---

## 💡 Ideas to Try

- Change `KB_FILE` to read a copy of the sample with fewer rows, and see fewer Documents.
- Add a Step 2 to `main()` in `pipeline.py` that prints only each Document's `metadata`, to see where each one
  came from.
