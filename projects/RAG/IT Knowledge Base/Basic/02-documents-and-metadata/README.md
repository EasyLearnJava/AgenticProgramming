# 02 · Documents and Metadata

Read the IT knowledge base, a CSV file of 10 IT support articles, into LangChain `Document`s, with each article split
into two parts: the text to read, and the labels that describe it. Built with **LangChain** and Python's `csv`
module.

> **Needs:** Python 3.11 or newer, and nothing else: this project only reads a local file.

---

## 🎯 What This Project Does

- **Reads** `data/sample_it_kb.csv`, one row at a time
- **Puts the article's content into its text** (`page_content`): the title, problem, resolution and notes, each
  with its label, and a blank line between them
- **Puts the facts about the article into its labels** (`metadata`): `doc_id` (the article's number), title,
  system, category, priority and tags
- **Prints** which columns went where, then every `Document` in full

The title is in both: it's part of what the article says, and it names the article.

**Try it:** `python knowledge_base.py`, and see each article's text and labels side by side.

---

## 🏗️ Architecture

```text
data/sample_it_kb.csv                 10 rows × 8 columns
          │
          ↓
┌──────────────────────────────┐
│  load_documents()            │  ← KBLoader(path).load(): one Document per row
│  └─ KBLoader.lazy_load()     │     reads the file one row at a time, and splits each row:
│                              │       title, problem, resolution, notes      → page_content
│                              │       doc_id, title, system, category,
│                              │       priority, tags                         → metadata
└──────────────┬───────────────┘
               │ 10 Documents
               ↓
┌──────────────────────────────┐
│  python knowledge_base.py    │  ← which columns went where, then every Document
└──────────────────────────────┘
```

### The Pipeline in This Project

1. **Read** → `csv.DictReader` gives each row as `{column: value}`
2. **Build the text** → `Title: ...`, `Problem: ...`, `Resolution: ...` and `Notes: ...`, a blank line between them
3. **Build the labels** → `doc_id`, then the title, system, category, priority and tags, as a dictionary
4. **Convert** → each row becomes a `Document(page_content=text, metadata=labels)`
5. **Print** → which columns went where, then every `Document`

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
python knowledge_base.py
```

It prints how many documents it read, and which columns went into the text and which into the labels. Then it prints
every document in full: a heading, its text, then its labels. The start and the end of what you'll see:

```text
10 documents
text:     title, problem, resolution, notes
metadata: doc_id, title, system, category, priority, tags

Document 1 of 10
Text (page_content):
Title: VPN Connection Timeout

Problem: Users experience timeout errors when attempting to connect to the corporate VPN from remote locations

Resolution: 1. Verify internet connection stability. 2. Check firewall settings and ensure VPN ports (UDP 500 and 4500) are open. 3. Restart VPN client application. 4. Clear VPN cache in application settings. 5. If issue persists restart the VPN service on the server. 6. Contact network team if problem continues.

Notes: Common issue during peak hours especially for users on home networks. May be related to ISP throttling.

Labels (metadata):
{'doc_id': '0', 'title': 'VPN Connection Timeout', 'system': 'VPN', 'category': 'Remote Access', 'priority': 'High', 'tags': 'vpn;timeout;remote;connection'}

Document 2 of 10
Text (page_content):
Title: MFA Setup Failure
...

Document 10 of 10
Text (page_content):
Title: Microsoft Teams Audio Issues
...

Labels (metadata):
{'doc_id': '9', 'title': 'Microsoft Teams Audio Issues', 'system': 'Microsoft Teams', 'category': 'Collaboration', 'priority': 'Medium', 'tags': 'teams;audio;collaboration;windows'}
```

The `...` lines stand for the parts left out here: your terminal shows all 10 documents in full.

---

## 📁 Project Structure

```text
02-documents-and-metadata/
├── knowledge_base.py                     # KBLoader, load_documents(), and the lines that print them
├── data/
│   └── sample_it_kb.csv                  # the knowledge base: 10 IT support articles
├── tests/
│   └── test_knowledge_base.py            # 5 tests: the Documents, their text and labels, the script
├── requirements.txt                      # langchain-core, pinned to an exact version
├── requirements-dev.txt                  # requirements.txt plus pytest, for the tests
├── pytest.ini                            # lets the tests import knowledge_base, and finds them in tests/
└── README.md                             # you are here
```

In `knowledge_base.py`, two lists decide where each column goes:

| Name | Columns | Where they go |
|---|---|---|
| `TEXT_COLUMNS` | title, problem, resolution, notes | the Document's text (`page_content`) |
| `METADATA_COLUMNS` | title, system, category, priority, tags | the Document's labels (`metadata`), after `doc_id` |

---

## 🧪 Testing

```bash
python -m pytest                     # 5 passed     (add -v for one line per test)
```

The tests read the sample file and run the script as its own process: 10 Documents; each text has the title,
problem, resolution and notes in that order; the labels are in `metadata` and not in the text; making the loader
reads nothing until `load()`; and the exact printed output.

---

## 📊 Understanding the Output

Each Document has two parts:

```text
Document 1 of 10
Text (page_content):                           ← title, problem, resolution and notes, each with its label
Title: VPN Connection Timeout

Problem: Users experience timeout errors ...

Resolution: 1. Verify internet connection stability. ...

Notes: Common issue during peak hours ...

Labels (metadata):                             ← the article's number, then the facts about it
{'doc_id': '0', 'title': 'VPN Connection Timeout', 'system': 'VPN', 'category': 'Remote Access', 'priority': 'High', 'tags': 'vpn;timeout;remote;connection'}
```

`doc_id` is the article's place in the file, counted from 0, as text: `'0'` is the first article and `'9'` the last.

---

## 🎓 Key Concepts Demonstrated

### 1. Text and Labels Kept Apart

```python
Document(page_content="Title: VPN Connection Timeout\n\nProblem: ...", metadata={"doc_id": "0", "system": "VPN", ...})
```

`page_content` is what the article says: the part meant to be read. `metadata` holds facts about the article, as
separate fields. A program can then use a label directly, `doc.metadata["system"]`, rather than look for it inside
the text, and the text stays free of fields that aren't part of the article's content.

### 2. Every Part of the Text Keeps Its Label

```python
text = "\n\n".join(f"{column.capitalize()}: {row[column]}" for column in TEXT_COLUMNS)
```

Each part starts with what it is, `Problem:` or `Resolution:`, so a reader of the text can tell the symptom from the
fix. The blank lines (`\n\n`) between the parts keep them apart.

### 3. Two Lists Decide What Goes Where

`TEXT_COLUMNS` and `METADATA_COLUMNS` are the only place the split is written down. To move a column from one part to
the other, you change a list, not the loop. The title is in both lists, so it's read with the text and is also there
as a label.

### 4. One Function for Every Article

```python
docs = load_documents()      # KBLoader(KB_FILE).load(): the 10 Documents, as a list
```

`load_documents()` is the one call that gives every article as a Document, so code that needs the knowledge base
doesn't have to know about the loader or the file.

---

## 🛠️ Troubleshooting

**Issue**: `ModuleNotFoundError: No module named 'langchain_core'`
**Fix**: The venv isn't active, or the packages aren't installed in it. Activate it (Step 2), then
`pip install -r requirements-dev.txt` (Step 3).

**Issue**: `FileNotFoundError: [Errno 2] No such file or directory: '.../data/sample_it_kb.csv'`
**Fix**: The data file is missing from this folder's `data/`. Put `sample_it_kb.csv` back there.

---

## 📚 Next Steps

**[03 · Chunking](../03-chunking/README.md)**: this project made one Document per article. 03 cuts each article into
smaller pieces, chunks of at most 512 characters, each with its article's labels.

**[Advanced · 02 · Documents and Metadata](../../Advanced/02-documents-and-metadata/README.md)** (planned): the same
project, production grade. Its README lists what it will add.

### Ideas to Try

- Move `"priority"` from `METADATA_COLUMNS` to `TEXT_COLUMNS`, and see it appear in the text instead of the labels.
- Print only `doc.metadata["system"]` for each Document, to list the systems the knowledge base covers.
