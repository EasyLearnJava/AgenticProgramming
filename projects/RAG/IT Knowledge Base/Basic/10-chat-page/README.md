# 10 · Chat Page

A web page to ask the IT knowledge base questions in, served by the same server as the API. You type a question, and
the page shows Gemini's answer with the articles it came from. Built with **FastAPI**, plain **HTML and JavaScript**,
**LangChain**, **Gemini** (`gemini-embedding-001` and `gemini-3.5-flash-lite`) and **Qdrant**, running in memory.

> **Needs:** Python 3.11 or newer, a Gemini API key, and a web browser. Starting the server makes 1 call to Gemini;
> each question makes 2.

---

## 🎯 What This Project Does

- **Serves a chat page**, `index.html`, at http://127.0.0.1:8000, from the same server as the API
- **Shows one line about the knowledge base** when the page opens, from `GET /api/stats`
- **Sends your question** to `POST /api/query` when you click **Ask** or press Enter, and shows the answer with its
  sources, newest first
- **Shows what went wrong** when a question is bad or Gemini doesn't answer
- **Keeps the API**: `/docs`, `/api/query`, `/api/stats` and `/api/health` answer as before

**Try it:** start the server, open http://127.0.0.1:8000, and click **Ask**.

---

## 🏗️ Architecture

```text
the browser
   │ GET /                                  │ POST /api/query {"question": "..."}
   ↓                                        ↓
┌──────────────────────────────────────────────────┐
│  FastAPI app (main.py)                           │
│  ├─ page()      → index.html (no-cache)          │  ← the chat page
│  ├─ stats()     → engine.stats()                 │  ← the page's first line
│  ├─ query()     → await engine.aquery(question)  │  ← the answer and its sources
│  └─ health()    → {"status": "ok"}               │
└────────────────────────┬─────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────┐
│  RAGEngine, built at start-up                    │  ← the 5 closest chunks, then Gemini's answer
└──────────────────────────────────────────────────┘
```

### The Pipeline in This Project

1. **Start** → `uvicorn main:app` builds the engine once: the chunks are embedded and stored (one call to Gemini)
2. **Open the page** → `GET /` sends `index.html`; the page asks `GET /api/stats` for its first line
3. **Ask** → the page sends the question to `POST /api/query`
4. **Answer** → the engine finds the 5 closest chunks and has Gemini answer from them (2 calls)
5. **Show** → the page adds the question, the answer and up to 3 sources above the earlier answers

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**: every call to Gemini uses your key's quota
- **A web browser**

---

## 🚀 Quick Start

### Step 1: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Basic/10-chat-page"   # from the repo root; quotes for the spaces
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

### Step 5: Start the Server

```bash
uvicorn main:app --reload            # the server; Ctrl+C stops it
```

It prints uvicorn's start-up lines, ending with these two. Then it waits for requests:

```text
INFO:     RAG engine built: 10 articles, 28 chunks
INFO:     Application startup complete.
```

### Step 6: Open the Page

Open http://127.0.0.1:8000. The page starts with this line:

```text
10 articles in 28 chunks. Answers by gemini-3.5-flash-lite, search by gemini-embedding-001, 5 chunks per question.
```

The question box already holds `How do I fix VPN connection timeouts?`: click **Ask**. The answer shows up under the
box: your question, Gemini's answer, then **Sources:** with up to 3 articles, each with its system, category and the
start of its text.

In GitHub Codespaces, `127.0.0.1` is your own computer, not the codespace: open the **Ports** tab next to
**Terminal** and click the globe icon on port 8000.

### Or: Run It in One Command

With your key in `.env` (Step 4), this one command does Steps 2, 3 and 5 for you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/10-chat-page   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs
`uvicorn main:app --reload` in this folder with the venv's Python, so there's nothing to activate. Ctrl+C stops the
server. Then open the page as in Step 6.

---

## 📁 Project Structure

```text
10-chat-page/
├── index.html                            # the chat page: the stats line, the question box, the answers
├── pipeline.py                           # the same steps in the terminal: build, then answer the sample questions
├── main.py                               # the FastAPI app: start-up, the page, the three API routes
├── rag_engine.py                         # RAGEngine: build(), query(), aquery(), stats(); print_result()
├── rag_chain.py                          # the prompt and make_rag_chain(): retrieval, then the answer
├── retriever.py                          # make_retriever() (5 chunks per question), format_docs(), sample questions
├── vector_store.py                       # make_vector_store() (Qdrant, in memory), add_knowledge_base()
├── models.py                             # the Gemini models: the embedding model and the chat model
├── config.py                             # load_api_key(): the key from .env, checked before anything else
├── chunking.py                           # split_documents(): chunks of at most 512 characters
├── knowledge_base.py                     # load_documents(): the 10 articles as Documents
├── data/
│   └── sample_it_kb.csv                  # the knowledge base: 10 IT support articles
├── tests/
│   ├── conftest.py                       # skips the live tests when there's no key
│   ├── fakes.py                          # stand-ins for Gemini, so the plain tests make no calls
│   └── test_*.py                         # one test file per module
├── .env.example                          # copy it to .env and put your key in it
├── requirements.txt                      # the packages, pinned to exact versions, FastAPI and uvicorn included
├── requirements-dev.txt                  # requirements.txt plus pytest and httpx2, for the tests
├── pytest.ini                            # finds the tests in tests/, and defines the "live" marker
└── README.md                             # you are here
```

---

## 🧪 Testing

```bash
python -m pytest                     # 56 passed, 7 skipped     (add -v for one line per test)
```

The plain tests use stand-ins for Gemini, so they need no key and make no calls. For the page, they check that it's
served at `/` and `/index.html` as HTML, with `Cache-Control: no-cache`, and that it calls `/api/query` and
`/api/stats`; and that it handles an unexpected status and never puts the server's text in as HTML. For the API, they
check each route, the 422 for a bad question, the 502 for a failed Gemini call, and the message when there's no key.
For `pipeline.py`, they check that it builds the engine, then answers each question, or one of your own; and that no
other file runs anything in the terminal.

The 7 skipped tests are live tests, marked `live`: they call the real Gemini, so `tests/conftest.py` skips them when
no key is set. With your key in `.env`, they run too. To run only the plain ones: `python -m pytest -m "not live"`.

---

## 📊 Understanding the Output

What the page shows:

| Where | What | From |
|---|---|---|
| Under the title | one line about the knowledge base | `GET /api/stats`, when the page opens |
| Under the box, while it works | `Searching the knowledge base and asking Gemini…` | the page itself; **Ask** is greyed out until the answer comes |
| Above earlier answers | your question, the answer, then `Sources:` with up to 3 articles | `POST /api/query` |
| Under the box, after it | `Done.`, or what went wrong | the answer's status |

What went wrong, as the page shows it:

| Status | The page shows |
|---|---|
| 422, a bad question (an empty one) | `question: String should have at least 1 character` |
| 502, Gemini didn't answer | the server's `detail`, then `The server's terminal says why.` |
| anything else, or no server | `Something went wrong: ...` |

The box takes at most 500 characters, the same limit the API checks.

---

## 🎓 Key Concepts Demonstrated

### 1. One Server for the Page and the API

```python
@app.get("/")
@app.get("/index.html")
async def page():
    return FileResponse(PAGE, headers={"Cache-Control": "no-cache"})
```

The page comes from the same server as the API, so its requests need no full address: `fetch("/api/query")` goes
back to where the page came from. `no-cache` makes the browser ask the server again before reusing its saved copy
of the page, so it never shows an old one.

### 2. A Form That Doesn't Reload the Page

```javascript
document.getElementById("form").addEventListener("submit", async (event) => {
  event.preventDefault();
  ...
});
```

Clicking **Ask** or pressing Enter submits the form. `preventDefault()` stops the browser from reloading the page;
the script sends the question with `fetch` and adds the answer to the page itself.

### 3. The Server's Text Is Shown as Text

```javascript
a.textContent = data.answer;
```

Every piece of the answer goes in with `textContent`, never `innerHTML`, so text from the server is shown as text and
can't add HTML to the page.

### 4. Every Status Has Its Own Message

A 422 shows which field is wrong and why, a 502 shows the server's short message, and anything else shows
`Something went wrong:` with the reason. The page never stays silent.

---

## 🛠️ Troubleshooting

**Issue**: The terminal shows `Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).`, and the server doesn't start
**Fix**: Press Ctrl+C (with `--reload`, uvicorn keeps waiting), put your key in `.env` (Step 4), and start it again.

**Issue**: `Can't build the models: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Replace it with your key.

**Issue**: The page shows `... The server's terminal says why.`
**Fix**: Gemini didn't answer. The server's terminal has a `Gemini call failed:` line with the reason.

**Issue**: The page shows `Something went wrong: ...`
**Fix**: The server isn't running, or it answered with an error the page didn't expect. Check the server's terminal.

**Issue**: http://127.0.0.1:8000 doesn't open in Codespaces
**Fix**: `127.0.0.1` is your own computer. Open the **Ports** tab next to **Terminal** and click the globe icon on port
8000.

---

## 📚 Next Steps

**[11 · Qdrant in Docker](../11-qdrant-in-docker/README.md)**: this project keeps the chunks in memory, so every
start embeds them again. 11 keeps them in a Qdrant server, in Docker, between runs.

**[Advanced · 10 · Chat Page](../../Advanced/10-chat-page/README.md)** (planned): the same project, production
grade. Its README lists what it will add.

### Ideas to Try

- Click **Ask** with an empty box, and read the message the page shows.
- Ask three questions, and see the newest answer appear at the top.
- Change the question in the box's `value` in `index.html`, reload the page, and see the new default question.
