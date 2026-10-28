# 02 · Documents and Metadata

Read the IT knowledge base, a CSV file of 10 IT support articles, into LangChain `Document`s, with each article
divided into two parts: the text to read, and the labels that describe it. Built with **LangChain** and Python's `csv`
module.

In a RAG app, `page_content` is what gets embedded and matched; the labels travel beside it as metadata, to name, show
or filter the article.

> **Needs:** Python 3.11 or newer, and nothing else: this project only reads a local file.

---

## 🎯 What This Project Does

- **Reads** `data/sample_it_kb.csv`, one row at a time
- **Puts the article's content into its text** (`page_content`): the title, problem, resolution and notes, each
  starting with its name, and a blank line between them
- **Puts the facts about the article into its labels** (`metadata`): `doc_id` (the article's number), title,
  system, category, priority and tags
- **Prints** which columns went where, then every `Document` in full
- **All the code in one file**, `pipeline.py`: the loader, and `main()`, which names the step, then runs it. The
  helper that prints the Documents is apart, in `utils.py`

The title is in both: it's part of what the article says, and it names the article.

**Try it:** `python pipeline.py`, and see each article's text and labels side by side.

---

## 🏗️ Architecture

```text
┌──────────────────────────────┐
│  pipeline.py: main()         │  ← the one file to run: it holds the loader below, and calls each step in order
└──────────────┬───────────────┘
               │ Step 1: Read the knowledge base
               ↓
┌──────────────────────────────┐
│  load_documents()            │  ← KBLoader(path).load(): data/sample_it_kb.csv, one Document per row
│  └─ KBLoader.lazy_load()     │     reads the file one row at a time, and divides each row:
│                              │       title, problem, resolution, notes      → page_content
│                              │       doc_id, title, system, category,
│                              │       priority, tags                         → metadata
└──────────────┬───────────────┘
               │ 10 Documents
               ↓
┌──────────────────────────────┐
│  print_documents()           │  ← utils.py: which columns went where, then every Document
└──────────────────────────────┘
```

### The Pipeline in This Project

1. **Run** → `python pipeline.py`: `main()` prints the step's name, then runs it
2. **Read** → `csv.DictReader` gives each row as `{column: value}`
3. **Build the text** → `Title: ...`, `Problem: ...`, `Resolution: ...` and `Notes: ...`, a blank line between them
4. **Build the labels** → `doc_id`, then the title, system, category, priority and tags, as a dictionary
5. **Convert** → each row becomes a `Document(page_content=text, metadata=labels)`
6. **Print** → `print_documents()`, from `utils.py`: which columns went where, then every `Document`

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- Nothing else: once the packages are installed, it runs without a network

---

## 🚀 Quick Start

### Step 1: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Basic/02-documents-and-metadata"   # from the repo root; quotes for the spaces
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
python "projects/RAG/IT Knowledge Base/run.py" Basic/02-documents-and-metadata   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs `python
pipeline.py` in this folder with the venv's Python, so there's nothing to activate. The project's output is the same
as in Step 4, after run.py's own lines saying what it creates, installs and runs.

---

## 🧪 Testing

```bash
python -m pytest                     # 8 passed     (add -v for one line per test)
```

The tests read the sample file and run `pipeline.py` as its own process:

- **The Documents**: 10 of them, from the CSV file next to the script; each text has the title, problem, resolution
  and notes in that order, and none is empty; the labels are in `metadata` and not in the text; and making the
  loader reads nothing until `load()`
- **The printing**: what `print_documents()` prints: which columns went where, then every Document
- **Running it**: its exact output; the same whichever folder it's started from; and no other file runs anything

---

## 🎓 Key Concepts Demonstrated

### 1. Text and Labels Kept Apart

The VPN article prints as:

```text
Document 1 of 10
Text (page_content):
Title: VPN Connection Timeout

Problem: Users experience timeout errors when attempting to connect to the corporate VPN from remote locations

Resolution: 1. Verify internet connection stability. 2. Check firewall settings and ensure VPN ports (UDP 500 and 4500) are open. 3. Restart VPN client application. 4. Clear VPN cache in application settings. 5. If issue persists restart the VPN service on the server. 6. Contact network team if problem continues.

Notes: Common issue during peak hours especially for users on home networks. May be related to ISP throttling.

Labels (metadata):
{'doc_id': '0', 'title': 'VPN Connection Timeout', 'system': 'VPN', 'category': 'Remote Access', 'priority': 'High', 'tags': 'vpn;timeout;remote;connection'}
```

`page_content` is what the article says, and in a RAG app it's what gets searched and read, so it holds only the
article's content. `metadata` holds facts about the article, as separate fields. They travel with the text and say
which article it is, so an answer can name the article it came from, and a program can read a label directly,
`doc.metadata["system"]`, rather than look for it inside the text.

**Before and after.** In 01, the same article had all 8 columns in its text, and only
`{'source': 'sample_it_kb.csv', 'row': 0}` as metadata. Here, system, category, priority and tags have moved out of
the text into the labels. `doc_id` holds 01's row number, as text, and `source` is gone: all 10 articles come from
the same file.

### 2. Every Part of the Text Says What It Is

```python
text = "\n\n".join(f"{column.capitalize()}: {row[column]}" for column in TEXT_COLUMNS)
```

Each part starts with what it is, `Problem:` or `Resolution:`, so whoever reads the text, a person or a model, can
tell the symptom from the fix. The blank lines (`\n\n`) between the parts keep them apart.

### 3. Two Lists Decide What Goes Where

`TEXT_COLUMNS` and `METADATA_COLUMNS` are the only place the division is written down. To move a column from one part
to the other, you change a list, not the loop. The title is in both lists, so it's read with the text and is also
there as a label.

### 4. One Function for Every Article

```python
docs = load_documents()      # KBLoader(KB_FILE).load(): the 10 Documents, as a list
```

`load_documents()` is the one call that gives every article as a Document, so code that needs the knowledge base
doesn't have to know about the loader or the file.

### 5. One File Runs the Steps

```python
def main() -> None:
    print("Step 1: Read the knowledge base")
    docs = load_documents()
    print_documents(docs, TEXT_COLUMNS, METADATA_COLUMNS)
```

`pipeline.py` is the only file that runs anything: `main()` names each step, then runs it, in order. `utils.py`
only defines the helper that prints its result, so importing it prints nothing. A new step is one more part of
`main()`.

### 6. The Code in One File, the Helper Apart

```python
from utils import print_documents   # a helper: showing what was read
```

`pipeline.py` holds the project's code, top to bottom in the order it's used: the path to the data file, the two
column lists, the loader (`KBLoader` and `load_documents()`), then `main()`, which runs them. Printing the Documents
is something the pipeline does with them, not part of reading them, so it lives in `utils.py`. `main()` hands it
the two lists, so it prints the columns the loader used, and `utils.py` needs nothing from `pipeline.py`.

---

## 🛠️ Troubleshooting

**Issue**: `.venv\Scripts\Activate.ps1 cannot be loaded because running scripts is disabled on this system.`
**Fix**: Windows PowerShell blocks scripts until you allow them. Allow local ones once, with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or for this window only, with
`Set-ExecutionPolicy -Scope Process Bypass`, then activate again (Step 2). The one command needs no activating.

**Issue**: `ModuleNotFoundError: No module named 'langchain_core'`
**Fix**: The venv isn't active, or the packages aren't installed in it. Activate it (Step 2), then
`pip install -r requirements-dev.txt` (Step 3).

**Issue**: `FileNotFoundError: [Errno 2] No such file or directory: '.../data/sample_it_kb.csv'`
**Fix**: The data file is missing from this folder's `data/`. Put `sample_it_kb.csv` back there.

**Issue**: `python utils.py` prints nothing
**Fix**: That file only defines the helper that prints the Documents. Run `python pipeline.py` (Step 4), which
uses it.

---

## 💡 Ideas to Try

- Move `"priority"` from `METADATA_COLUMNS` to `TEXT_COLUMNS` in `pipeline.py`, and see it appear in the text
  instead of the labels. The tests expect the division as it is, so move it back before `python -m pytest`.
- Add a Step 2 to `main()` in `pipeline.py` that prints only `doc.metadata["system"]` for each Document, to list the
  systems the knowledge base covers. One test checks the pipeline's exact output, so take Step 2 out before
  `python -m pytest`.
