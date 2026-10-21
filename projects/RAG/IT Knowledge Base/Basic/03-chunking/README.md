# 03 · Chunking

Read the IT knowledge base's 10 articles into LangChain `Document`s, then cut each one into smaller pieces, called
chunks, of at most 512 characters: 28 in all. Built with **LangChain** (`langchain-core` and
`langchain-text-splitters`) and Python's `csv` module.

> **Needs:** Python 3.11 or newer, and nothing else: this project only reads a local file.

---

## 🎯 What This Project Does

- **Reads** `data/sample_it_kb.csv` into 10 `Document`s: each article's text (title, problem, resolution, notes) and
  its labels (`doc_id`, title, system, category, priority, tags)
- **Cuts each article into chunks** of at most 512 characters with LangChain's `RecursiveCharacterTextSplitter`. The
  articles are 569 to 716 characters long, so each becomes 2 or 3 chunks: 28 in all
- **Cuts at the biggest break it can find**: first the blank lines between Title, Problem, Resolution and Notes, then
  line breaks, then spaces
- **Repeats up to 50 characters** from the end of one chunk at the start of the next (the overlap), when it has to
  cut inside a section
- **Keeps each chunk's labels**: every chunk is a `Document` of its own, with its article's labels plus
  `start_index`, where in the article's text the chunk starts
- **Prints** how many chunks each article made, then every chunk, with where it starts and how long it is

**Try it:** `python chunking.py`, then `python chunking.py 200`, and compare the two.

---

## 🏗️ Architecture

```text
data/sample_it_kb.csv                       10 rows × 8 columns
          │
          ↓
┌──────────────────────────────────┐
│  load_documents()                │  ← knowledge_base.py: 10 Documents, text + labels
└────────────────┬─────────────────┘
                 │ 10 Documents
                 ↓
┌──────────────────────────────────┐
│  split_documents(docs)           │  ← chunking.py
│  └─ make_splitter()              │     RecursiveCharacterTextSplitter(chunk_size=512,
│                                  │       chunk_overlap=50, add_start_index=True)
└────────────────┬─────────────────┘
                 │ 28 chunks: Documents with their article's labels + start_index
                 ↓
┌──────────────────────────────────┐
│  python chunking.py [size]       │  ← how many chunks each article made, then every chunk
└──────────────────────────────────┘
```

### The Pipeline in This Project

1. **Load** → `load_documents()` reads the CSV into 10 `Document`s, text kept apart from labels
2. **Make the splitter** → `make_splitter()`: chunks of at most 512 characters, up to 50 repeated, `start_index` on
3. **Split** → `split_documents(docs)` cuts every article at the biggest breaks that keep each chunk within 512
4. **Label** → each chunk gets a copy of its article's labels, plus `start_index`
5. **Print** → the chunks per article, then every chunk in full

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- Nothing else: once the packages are installed, it runs without a network

---

## 🚀 Quick Start

### Step 1: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Basic/03-chunking"   # from the repo root; quotes for the spaces
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
pip install -r requirements-dev.txt  # once: LangChain's core and text splitters, and pytest, into .venv/
```

### Step 4: Run It

```bash
python chunking.py
```

It prints how many chunks each article made. Then it prints every article's chunks: a heading for each article, then
each chunk with where in the article it starts and how long it is. The start of what you'll see:

```text
10 articles -> 28 chunks of at most 512 characters
  2 from VPN Connection Timeout (569 characters)
  2 from MFA Setup Failure (653 characters)
  3 from Laptop Performance Degradation (668 characters)
  3 from SaaS Access Permission Denied (672 characters)
  3 from WiFi Connectivity Issues Office (668 characters)
  3 from Password Reset Failed (716 characters)
  3 from Printer Not Found (627 characters)
  3 from Email Attachment Size Limit (660 characters)
  3 from Database Connection Timeout (689 characters)
  3 from Microsoft Teams Audio Issues (699 characters)

Article 1 of 10: VPN Connection Timeout, cut into 2 chunks

Chunk 1 of 2, from character 0 (457 characters):
Title: VPN Connection Timeout

Problem: Users experience timeout errors when attempting to connect to the corporate VPN from remote locations

Resolution: 1. Verify internet connection stability. 2. Check firewall settings and ensure VPN ports (UDP 500 and 4500) are open. 3. Restart VPN client application. 4. Clear VPN cache in application settings. 5. If issue persists restart the VPN service on the server. 6. Contact network team if problem continues.

Chunk 2 of 2, from character 459 (110 characters):
Notes: Common issue during peak hours especially for users on home networks. May be related to ISP throttling.

Article 2 of 10: MFA Setup Failure, cut into 2 chunks
...
```

The `...` stands for the rest: your terminal shows all 10 articles and their 28 chunks.

Try other chunk sizes by giving one after the script's name:

```bash
python chunking.py 200               # 49 chunks
python chunking.py 1000              # 10 chunks: every article whole
```

`python knowledge_base.py` on its own prints the 10 articles before they're cut: which columns went into the text
and which into the labels, then every Document.

### Or: Run It in One Command

This one command does Steps 2 to 4 for you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/03-chunking   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs
`python chunking.py` in this folder with the venv's Python, so there's nothing to activate. The output is the same as
in Step 4.

---

## 📁 Project Structure

```text
03-chunking/
├── chunking.py                           # make_splitter(), split_documents(), and the lines that print the chunks
├── knowledge_base.py                     # KBLoader and load_documents(): the 10 articles, text + labels
├── data/
│   └── sample_it_kb.csv                  # the knowledge base: 10 IT support articles
├── tests/
│   ├── test_chunking.py                  # 8 tests: the chunks, their sizes, labels and breaks, the script
│   └── test_knowledge_base.py            # 5 tests: the Documents, their text and labels, the script
├── requirements.txt                      # langchain-core and langchain-text-splitters, pinned
├── requirements-dev.txt                  # requirements.txt plus pytest, for the tests
├── pytest.ini                            # lets the tests import the scripts, and finds them in tests/
└── README.md                             # you are here
```

| Setting in `chunking.py` | Value | What it does |
|---|---|---|
| `CHUNK_SIZE` | 512 | the most characters a chunk can have |
| `CHUNK_OVERLAP` | 50 | the most characters repeated from the end of one chunk at the start of the next |

---

## 🧪 Testing

```bash
python -m pytest                     # 13 passed     (add -v for one line per test)
```

The tests read the sample file and run the scripts as their own processes:

- **The chunks**: 512 characters cut each article into 2 or 3 chunks; no chunk is longer than the chunk size (checked
  at 200, 512 and 1000); each chunk keeps its article's labels and where it starts; chunks break between sections
  first; 1000 characters keep every article whole; and the exact printed output
- **The Documents**: 10 of them; each text has the title, problem, resolution and notes in order; the labels are in
  the metadata, not the text; making the loader reads nothing until `load()`; and the exact printed output

---

## 📊 Understanding the Output

```text
Chunk 1 of 2, from character 0 (457 characters):        ← this chunk is characters 0 to 456 of the article's text
...
Chunk 2 of 2, from character 459 (110 characters):      ← this one starts at character 459
```

`from character` is the chunk's `start_index`: where in the article's text it starts. Chunk 1 holds characters 0 to
456, and chunk 2 starts at 459: characters 457 and 458 are the blank line (`\n\n`) at the cut, which goes in neither
chunk.

Each chunk's labels are its article's, plus `start_index`:

```python
chunk.metadata  ->  {'doc_id': '0', 'title': 'VPN Connection Timeout', 'system': 'VPN', 'category': 'Remote Access',
                     'priority': 'High', 'tags': 'vpn;timeout;remote;connection', 'start_index': 459}
```

---

## 🎓 Key Concepts Demonstrated

### 1. A Chunk Is a Piece of an Article

A whole article mixes its problem, its fix and its notes. A chunk holds one or two of those sections, so a program
can work with the part of an article that matters rather than all of it. Each chunk is still a `Document`, and its
labels say which article it came from.

### 2. Recursive: the Biggest Break First

`RecursiveCharacterTextSplitter` tries the biggest breaks first: the blank lines between sections, then line breaks,
then spaces. It only cuts inside a word if nothing else fits. With 512, every cut in this knowledge base falls
between sections.

### 3. 512 Is a Maximum, Not a Target

The splitter never makes a chunk longer than 512 characters, but it makes a shorter one rather than cut through the
middle of a section. The MFA article shows it:

```text
Article 2 of 10: MFA Setup Failure, cut into 2 chunks

Chunk 1 of 2, from character 0 (144 characters):
Title: MFA Setup Failure

Problem: Employee cannot complete Multi-Factor Authentication setup on mobile device using Microsoft Authenticator app

Chunk 2 of 2, from character 146 (507 characters):
Resolution: 1. Ensure device time is synchronized (Settings > Date & Time > Automatic). 2. Clear cache and data for Microsoft Authenticator app. 3. Uninstall and reinstall the authenticator app. 4. Re-scan the QR code from the MFA setup page. 5. If QR code fails use manual entry method. 6. Verify company app is not blocking authenticator app. 7. Contact security team for account reset if needed.

Notes: Time synchronization is the most common root cause. iOS users should check Screen Time restrictions.
```

First the splitter breaks the article at its blank lines (`\n\n`), into its 4 sections:

| Section | Characters |
|---|---|
| Title | 24 |
| Problem | 118 |
| Resolution | 398 |
| Notes | 107 |

Then it joins them back together in order, adding the next section only while the chunk stays at 512 or under. Each
join puts back the blank line between them, which is 2 characters (`\n\n`):

| Step | Sum | Result |
|---|---|---|
| Title | 24 | fits |
| + Problem | 24 + 2 + 118 = **144** | fits |
| + Resolution | 144 + 2 + 398 = 544 | over 512, so chunk 1 ends at 144 |
| Resolution, starting chunk 2 | 398 | fits |
| + Notes | 398 + 2 + 107 = **507** | fits, so chunk 2 is 507 |

Chunk 2 starts at character 146: characters 144 and 145 are the blank line at the cut, which goes in neither chunk.

**Why it doesn't fill chunk 1 up to 512:** it could cut the Resolution partway, but that would split the fix's steps
across two chunks. The splitter only cuts inside a section (at a line break, then at a space) when the section alone
is over 512, and the Resolution is 398. So the chunks come out uneven, but each one is whole sections: chunk 1 is
what's wrong, and chunk 2 is how to fix it.

The VPN article works the same way. Its Title, Problem and Resolution make 29 + 2 + 110 + 2 + 314 = **457**. Adding
the Notes would make 457 + 2 + 110 = 569, over 512, so the Notes (110 characters) become chunk 2, from character 459.

### 4. The Overlap: Only When a Section Is Cut

The overlap repeats up to 50 characters of whole pieces from the end of one chunk at the start of the next, so a
sentence cut at the edge can still be whole in one of them. With 512, every cut falls between sections, so nothing is
repeated: in the MFA article, the piece before the cut, the Problem, is 118 characters, more than 50. With
`python chunking.py 200`, sections are too long to fit and get cut at spaces, and the overlap shows:

```text
Chunk 2 of 4, from character 143 (198 characters):
Resolution: 1. Verify internet connection stability. 2. Check firewall settings and ensure VPN ports (UDP 500 and 4500) are open. 3. Restart VPN client application. 4. Clear VPN cache in application

Chunk 3 of 4, from character 295 (162 characters):
application. 4. Clear VPN cache in application settings. 5. If issue persists restart the VPN service on the server. 6. Contact network team if problem continues.
```

Chunk 3 starts with `application. 4. Clear VPN cache in application`, the last 46 characters of chunk 2.

### 5. Each Chunk Remembers Where It Came From

```python
RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=50, add_start_index=True)
```

`split_documents()` gives each chunk a copy of its article's labels, and `add_start_index=True` adds `start_index`.
So every chunk can be traced back to its article and to its place in the article's text.

---

## 🛠️ Troubleshooting

**Issue**: `ModuleNotFoundError: No module named 'langchain_core'` (or `'langchain_text_splitters'`)
**Fix**: The venv isn't active, or the packages aren't installed in it. Activate it (Step 2), then
`pip install -r requirements-dev.txt` (Step 3).

**Issue**: `ValueError: invalid literal for int() with base 10: 'abc'`
**Fix**: The chunk size after `python chunking.py` must be a whole number, like `python chunking.py 200`.

**Issue**: `ValueError: Got a larger chunk overlap (50) than chunk size (40), should be smaller.`
**Fix**: The chunk size must be bigger than the overlap, 50. Use a size of 51 or more.

**Issue**: `FileNotFoundError: [Errno 2] No such file or directory: '.../data/sample_it_kb.csv'`
**Fix**: The data file is missing from this folder's `data/`. Put `sample_it_kb.csv` back there.

---

## 📚 Next Steps

**[04 · Embeddings](../04-embeddings/README.md)**: this project cut the articles into 28 chunks. 04 turns each
chunk's text into a vector, a list of numbers that stands for its meaning, with Gemini's embedding model.

**[Advanced · 03 · Chunking](../../Advanced/03-chunking/README.md)** (planned): the same project, production grade.
Its README lists what it will add.

### Ideas to Try

- Run `python chunking.py 1000`: every article fits in one chunk, so you get 10.
- Run `python chunking.py 200` and find the other places where the overlap repeats the end of a chunk.
- In `chunking.py`, change `CHUNK_OVERLAP` to `0`, run `python chunking.py 200` again, and see the repeats disappear.
