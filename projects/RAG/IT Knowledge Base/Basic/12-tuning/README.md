# 12 · Tuning

Measure how well the search finds what an answer needs, to help choose the settings. `tuning.py` asks 10 test
questions, each with the fact a good answer needs, for three chunk sizes, and counts how many find that fact among the
closest 1, 3 and 5 chunks. Gemini's search races two that make no calls, a keyword count and a random order, so its
scores have something to beat. The engine, the API and the chat page answer questions as before, from chunks kept on
disk in `qdrant_data/`. Built with **LangChain**, **Gemini** (`gemini-embedding-001` and `gemini-3.5-flash-lite`),
**Qdrant** and **FastAPI**.

In a RAG app, an answer is meant to use only what the search finds, so the search is what to measure first.

> **Needs:** Python 3.11 or newer, and a Gemini API key. `tuning.py` makes 13 calls to Gemini, which embed 97 texts,
> and runs in memory; with `--answers`, 17 calls and 99 texts. The engine, the API and the chat page keep their chunks
> in `qdrant_data/`.

---

## 🎯 What This Project Does

- **Asks 10 test questions**, each with its article and the fact a good answer needs, word for word as the article
  has it ("UDP 500 and 4500", "30 minutes"). No question uses a word of its article's title
- **Tries three chunk sizes**, 200, 512 and 1000 characters: for each, it stores that size's chunks and searches with
  every question
- **Counts the hits**: how many questions found a chunk holding their fact among the closest 1, 3 and 5 (k)
- **Races three searches**: Gemini's embeddings; the chunks sharing the most words with the question (keywords, no
  calls); and a random order, worked out as what luck finds on average
- **With `--answers`**, answers one question twice, from 1 chunk and from 5, to show what the number of chunks does
  to an answer
- **Keeps the app**: `python pipeline.py`, the API and the chat page, with the chunks kept on disk in
  `qdrant_data/`

**Try it:** `python tuning.py`, and read how far Gemini's search is ahead of the keywords and of luck.

---

## 🏗️ Architecture

```text
EVAL_SET: 10 (question, its article, the fact a good answer needs)

┌────────────────────────────────────────┐
│  build_stores(): for 200, 512, 1000    │
│  ├─ split_documents()                  │  ← 49, 28 or 10 chunks
│  ├─ embed_chunks()                     │  ← the chunks embedded (1 call per size)
│  └─ a new Qdrant store, in memory      │  ← store_vectors(): one point per chunk
└───────────────────┬────────────────────┘
                    │ evaluate(): each question embedded once (10 calls)
                    ↓
┌────────────────────────────────────────┐
│  for each chunk size, three searches:  │
│  ├─ gemini: the 5 closest chunks       │  ← is the fact in the first 1, 3, 5?
│  ├─ keywords: the most shared words    │  ← the same check; no calls
│  └─ random: random_hit_chance()        │  ← what luck finds, on average; no calls
└───────────────────┬────────────────────┘
                    ↓
     print_table(), in utils.py: one line per chunk size and search
     print_misses(), in utils.py: for each chunk size, the questions Gemini's top 1 missed, by article

with --answers:  compare_top_k()  ← one question answered from 1 chunk, then from 5, from the 512 store
```

### The Pipeline in This Project

1. **For each chunk size** → cut the articles into chunks of that size, embed them (one call to Gemini per size),
   and store them in a new in-memory Qdrant store
2. **Embed the questions** → each of the 10 questions once: 10 calls to Gemini, reused for every chunk size
3. **Search three ways** → for each chunk size and question: Gemini's 5 closest chunks, and the 5 chunks sharing the
   most words with the question
4. **Score** → for k = 1, 3 and 5, count the questions whose fact is in one of the first k chunks; for random,
   add up each question's chance
5. **Print** → the table: one line per chunk size and search; then, for each chunk size, the questions whose fact
   wasn't in Gemini's first chunk, by article
6. **With `--answers`** → the email question answered from 1 chunk and from 5, from the 512-character store

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**, made in the Google Cloud console, under APIs & Services > Credentials. There, under API
  restrictions, restrict it to the Gemini API (the Generative Language API; not Gemini for Google Cloud API, a
  different service), so a leaked key can't be used for anything else. Every call to Gemini uses your key's quota

---

## 🚀 Quick Start

### Step 1: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Basic/12-tuning"   # from the repo root; quotes for the spaces
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

Open `.env` in an editor and put your key after `GOOGLE_API_KEY=`. You make a key in the Google Cloud console, under
APIs & Services > Credentials, as `.env.example` says. `.env` is in `.gitignore`, so your key never goes into git.

### Step 5: Run It

```bash
python tuning.py                     # the table
python tuning.py --answers           # or, a minute later: the table, then one question from 1 chunk and from 5
```

### Step 6: Run the App (Optional)

The engine, the API and the chat page keep their chunks in `qdrant_data/`:

```bash
python pipeline.py                   # the three sample questions
uvicorn main:app                     # or the server: the chat page at http://127.0.0.1:8000; Ctrl+C stops it
```

The first run embeds and stores the chunks there; every run after that reuses them. Only one program at a time can
open `qdrant_data/`, so stop the server (Ctrl+C) before running `python pipeline.py`. Delete the folder to start over.

In GitHub Codespaces, `127.0.0.1` is your own computer, not the codespace: open the **Ports** tab next to
**Terminal** and click the globe icon on port 8000.

### Or: Run It in One Command

With your key in `.env` (Step 4), this one command does Steps 2, 3 and 5 for you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/12-tuning   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs `python tuning.py`
in this folder with the venv's Python, so there's nothing to activate. Options after the project's name go to
`tuning.py`: add `--answers` at the end for the two answers. The project's output is the same as in Step 5, after
run.py's own lines saying what it creates, installs and runs.

---

## 🧪 Testing

The plain tests keep Qdrant in memory, or in a folder of each test's own, never in `qdrant_data/`:

```bash
python -m pytest -m "not live"       # 82 passed, 10 deselected  (add -v for one line per test)
```

They use stand-ins for Gemini, so they need no key and make no calls. They check:

- **The test set**: the questions cover every article once; each fact is in its article word for word; and no
  question uses a word of its article's title
- **The race**: each chunk size's chunks are embedded once, and each question once; there are three searches per
  chunk size; a hit needs the fact, not just the article, and a miss in the top 1 is listed by its article; the
  keyword search leaves out common words and ranks by shared words; the random chance is the share of chunks luck
  would find; the table puts each score under its heading, and the misses printed are Gemini's, by article; and
  `compare_top_k()` answers the question once for each k, from the same store
- **The app**: the engine, the reuse of stored chunks and the ids, as in the app before; without a key, `pipeline.py`,
  `tuning.py` and the server stop with the message, not a traceback; and only those two scripts run anything in the
  terminal

The 10 deselected tests are live tests, marked `live`: they call the real Gemini, so they need your key in `.env`;
with no key, `tests/conftest.py` skips them, so plain `python -m pytest` runs only the others. Two of them, like the
app, use `qdrant_data/`: stop the server first. Together they embed far more than 100 texts, the free tier's limit
for a minute, so on the free tier, run them one file at a time, a minute apart:
`python -m pytest -m live tests/test_tuning.py`.

---

## 🎓 Key Concepts Demonstrated

### 1. Measure Before You Tune

Chunk size and k are guesses until something measures them. A fixed set of questions, each with what a right answer
needs, turns "the search seems fine" into a count you can compare between settings.

### 2. Test Questions in Other Words, Scored on the Fact

```python
("After my job changed I'm locked out of our CRM: how long until it works?", "SaaS Access Permission Denied",
 "30 minutes"),
```

No question uses a word of its article's title ("CRM", not "SaaS"; "locked out", not "access denied"), so no hit can
come from the title alone, though most questions still share other words with the chunk holding their fact. And a
hit needs a chunk holding the fact, here "30 minutes": finding the right article's title isn't enough when the chunk
found is the one without the answer.

### 3. A Race Needs Something to Beat

A score means little alone. Two searches that make no calls run beside Gemini's on the same chunks: **keywords**, the
chunks sharing the most words with the question, leaving out common ones such as "the", "to" and "of"; and
**random**, what picking chunks blindly finds on average. The real run:

```text
chunk size  chunks  search    found in top 1  found in top 3  found in top 5
       200      49  gemini           7 of 10         9 of 10        10 of 10
       200      49  keywords         4 of 10         6 of 10         7 of 10
       200      49  random         0.2 of 10       0.7 of 10       1.2 of 10

       512      28  gemini           9 of 10        10 of 10        10 of 10
       512      28  keywords         5 of 10         8 of 10         8 of 10
       512      28  random         0.4 of 10       1.2 of 10       1.9 of 10

      1000      10  gemini          10 of 10        10 of 10        10 of 10
      1000      10  keywords         8 of 10         9 of 10         9 of 10
      1000      10  random           1 of 10         3 of 10         5 of 10

Not in Gemini's top 1, by article:
       200  MFA Setup Failure, Laptop Performance Degradation, Email Attachment Size Limit
       512  Email Attachment Size Limit
      1000  none
```

### 4. Reading the Table

- **Read the top 1 first.** Gemini's search puts the chunk with the fact first for 7, 9 and 10 of the 10 questions
  (its hit rate at k = 1: 70%, 90% and 100%); the keywords manage 4, 5 and 8. That gap is what the embeddings add. The
  CRM question shares no word with the chunk holding its fact, once common words are left out: the keywords never find
  it in their top 5, and Gemini's search puts it first at every size. The lines under the table name the questions
  whose fact Gemini's first chunk missed, by article: MFA, Laptop and Email at 200, only Email at 512, none at 1000.
- **Keywords are strong on exact terms.** A question with "10.50.3.25" or "CorpWiFi-5G" in it shares those words with
  the chunk that has them, and the keyword search usually puts that chunk first. That's why real apps often combine
  the two searches (hybrid search).
- **Read each row against random.** At 1000 characters, each article is one chunk, and the top 5 is half the
  knowledge base: luck alone finds 5 of 10, the keywords 9 and Gemini's search all 10.
- **In the top 1, bigger chunks win, and that's this data.** A bigger chunk holds more: these 10 articles are short
  (569 to 716 characters), so at 1000 each one is a single chunk, and finding the article finds its fact. At 200, a
  fact can land in a chunk without the words a question would match. With long articles, 1000-character chunks
  would be a few mixed pieces of each, and the prompt would get 5: measure your own, don't take these numbers.
- **At the app's k of 5, Gemini's search finds all 10 at every size.** So 512, the app's chunk size, gets the same
  hits as 1000 with less to read, and more hits than 200 in the top 1 and top 3. Bigger chunks cost more: more text,
  so more tokens, sent to Gemini with every question.
- **10 questions is a small test.** One question more or less moves a score by 10%. A real test set has many
  questions, written from what users really ask.

### 5. Embed Each Question Once

`evaluate()` embeds the 10 questions once and reuses their vectors for every chunk size, then searches once per
question for the most chunks needed (5) and checks the first 1, 3 and 5. Fewer calls, the same counts.

### 6. A Fresh Store for Each Setting

Each chunk size gets its own in-memory Qdrant store, so one setting's chunks never mix with another's, and the chunks
kept in `qdrant_data/` stay as they are. `--answers` reuses the 512 store, so the two answers cost no more embedding
than their questions.

### 7. The Number of Chunks in an Answer

`python tuning.py --answers` asks the email question, the one Gemini's first chunk missed at 512, from 1 chunk and
from 5:

```text
--- "What's the largest file I can send to someone outside the company?", answered from 1 chunk:
Based on company policy, email attachments are limited for security, and you should use cloud sharing for files over 10MB.

Articles used: Email Attachment Size Limit

--- "What's the largest file I can send to someone outside the company?", answered from 5 chunks:
The limit is 25MB for external emails (and 50MB for internal emails). For files over 10MB, cloud sharing is encouraged, and files over 100MB should use the secure file transfer system.

Source: [2] Email Attachment Size Limit
```

From 1 chunk, the answer missed the 25MB limit: the chunk found was from the right article, but wasn't the chunk with
the limit. The prompt asks Gemini to say when the articles don't cover a question; instead, it gave the 10MB
cloud-sharing rule, which reads like a limit. From 5, the chunk with the limit was in the prompt too, 2nd (the [2] its
answer cites), and the answer gave it. With k = 1, an answer has nothing to fall back on when that chunk is the wrong
one; with 5, the prompt is longer and more of it is about something else.

---

## 🛠️ Troubleshooting

**Issue**: `.venv\Scripts\Activate.ps1 cannot be loaded because running scripts is disabled on this system.`
**Fix**: Windows PowerShell blocks scripts until you allow them. Allow local ones once, with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or for this window only, with
`Set-ExecutionPolicy -Scope Process Bypass`, then activate again (Step 2). The one command needs no activating.

**Issue**: `GoogleGenerativeAIError: Error embedding content (INVALID_ARGUMENT): 400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'API key not valid. Please pass a valid API key.', ...`
**Fix**: Gemini didn't accept the key in `.env`. Copy it again from the Google Cloud console, with nothing before or
after it.

**Issue**: An error with `403 PERMISSION_DENIED` in it
**Fix**: Google refused the key for this service. In the Google Cloud console, open the key: under API restrictions
it should list the Gemini API (the Generative Language API), not Gemini for Google Cloud API, and under
Application restrictions, None. New settings can take up to 5 minutes to work.

**Issue**: `GoogleGenerativeAIError: Error embedding content (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, ...`
**Fix**: Your key has used its quota. On the free tier, that's 100 embedded texts a minute, and `tuning.py` embeds 97
(99 with `--answers`): run it at the start of a minute with nothing else using the key. The message ends with
"Please retry in" and a number of seconds. Wait that long, then run it again.

**Issue**: A question gets `{"detail":"Couldn't answer the question (...)."}` with status 502, or the page says so
**Fix**: The server's terminal has a `Couldn't answer:` line with the reason, then the traceback. Fix what it says,
then ask again.

**Issue**: `Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).`
**Fix**: There's no `.env` with a key in this folder. Do Step 4.

**Issue**: `Can't build the models: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Replace it with your key.

**Issue**: `Can't build the models: .env isn't saved as UTF-8 text. Open it in an editor and save it with UTF-8 encoding.`
**Fix**: `.env` was saved in another encoding, often UTF-16 by Windows PowerShell 5's `echo ... > .env`. Save it
again as UTF-8, or make it with `copy .env.example .env` and edit it.

**Issue**: `python pipeline.py`, or the server's start-up, stops with `RuntimeError: Storage folder .../qdrant_data is already accessed by another instance of Qdrant client. If you require concurrent access, use Qdrant server instead.`
**Fix**: Another program has `qdrant_data/` open: usually the server (`uvicorn main:app`) while you run
`python pipeline.py`, or the other way round. Only one program at a time can open the folder. Stop the other one
(Ctrl+C), then try again. `tuning.py` never opens it.

**Issue**: `ModuleNotFoundError: No module named 'langchain_core'` (or another of the packages)
**Fix**: The venv isn't active, or the packages aren't installed in it. Activate it (Step 2), then
`pip install -r requirements-dev.txt` (Step 3).

**Issue**: An error with `[Errno 10048]` or `address already in use` in it, and the server stops
**Fix**: Another server, often another project's, already has port 8000. Stop it (Ctrl+C in its terminal), or
start this one on another port, `uvicorn main:app --port 8001`, and use 8001 in the address.

**Issue**: `uvicorn` isn't found: PowerShell says it `is not recognized`, bash says `command not found`
**Fix**: The venv isn't active, so its `uvicorn` isn't on the path. Activate it (Step 2), or use the one command,
which needs no activating.

---

## 💡 Ideas to Try

- Replace 200 with 300 in `CHUNK_SIZES` in `tuning.py`, and see where it lands in the table. Wait a minute between
  runs.
- Reword one question in `EVAL_SET` to use its article's title words, and see whether that question's keyword hit
  changes. A test checks that no question does, so put it back before you run the tests.
- Add a question about the VPN's busy times ("peak hours" is in both the VPN and the Database articles), with "ISP
  throttling" as its fact, and see whether the search tells the two near-misses apart. Tests check that each article
  has one question, using none of its title's words, so take it out before you run the tests.
- In the `--answers` loop in `tuning.py`, also print whether `EVAL_SET[7][2]`, "25MB", is in each answer. An
  exact-text check like that would miss "25 MB" written with a space: answers are hard to score by text.
