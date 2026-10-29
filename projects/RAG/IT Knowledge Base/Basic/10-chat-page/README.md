# 10 · Chat Page

A web page to ask the IT knowledge base questions in, served by the same server as the API. You type a question, and
the page shows Gemini's answer with the articles the search found. Built with **FastAPI**, plain **HTML and
JavaScript**, **LangChain**, **Gemini** (`gemini-embedding-001` and `gemini-3.5-flash-lite`) and **Qdrant**, running
in memory.

> **Needs:** Python 3.11 or newer, a Gemini API key, and a web browser. Starting the server makes 1 call to Gemini;
> each question makes 2.

---

## 🎯 What This Project Does

- **Serves a chat page**, `index.html`, at http://127.0.0.1:8000, from the same server as the API
- **Shows what the knowledge base holds** when the page opens, as a row of labels, from `GET /api/stats`
- **Offers the three sample questions** as buttons: click one to ask it
- **Looks the part**: light and dark themes that follow your system's setting, and a card for each answer with
  its numbered sources; it's all in `index.html`, with no fonts or scripts from anywhere else
- **Sends your question** to `POST /api/query` when you click **Ask** or press Enter, and shows the answer with its
  sources, newest first
- **Has no memory**: each question goes to the server on its own, so a follow-up like "and on Windows?" isn't read
  with the question before it
- **Shows what went wrong** when a question is bad or can't be answered
- **Keeps the API**: `/docs`, `/api/query`, `/api/stats` and `/api/health` answer as before
- **Keeps the engine in `pipeline.py`**, which holds all the code, as in 09; the server is `main.py`, and two
  helpers are apart: `config.py`, which checks the key, and `utils.py`, which prints answers in the terminal

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
│  RAGEngine, from pipeline.py                     │  ← built at start-up; the 5 closest chunks, then Gemini's answer
└──────────────────────────────────────────────────┘
```

### The Pipeline in This Project

1. **Start** → `uvicorn main:app` builds the engine once: the chunks are embedded and stored (one call to Gemini)
2. **Open the page** → `GET /` sends `index.html`; the page asks `GET /api/stats` for its first line
3. **Ask** → the page sends the question to `POST /api/query`
4. **Answer** → the engine's retriever finds the 5 closest chunks (1 call), then Gemini answers from them (1 call)
5. **Show** → the page adds the question, the answer and up to 3 sources above the earlier answers

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**, made in the Google Cloud console, under APIs & Services > Credentials. There, under API
  restrictions, restrict it to the Gemini API (the Generative Language API; not Gemini for Google Cloud API, a
  different service), so a leaked key can't be used for anything else. Every call to Gemini uses your key's quota
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
uvicorn main:app                     # the server; Ctrl+C stops it
```

When it prints `Uvicorn running on http://127.0.0.1:8000`, the server is ready: the chunks are embedded and stored,
and it has the port.

### Step 6: Open the Page

Open http://127.0.0.1:8000.

The question box already holds `How do I fix VPN connection timeouts?`: click **Ask**. The answer shows up under the
box: your question, Gemini's answer, then **Found by the search:** with up to 3 articles, each with its system,
category and the start of the chunk the search found. They're the articles the search found and Gemini was given, not
a checked list of what the answer used. Any [1], [2] in an answer number the 5 chunks in the prompt (07 prints it),
not the articles under **Found by the search:**.

In GitHub Codespaces, `127.0.0.1` is your own computer, not the codespace: open the **Ports** tab next to
**Terminal** and click the globe icon on port 8000.

### Or: Run It in One Command

With your key in `.env` (Step 4), this one command does Steps 2, 3 and 5 for you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/10-chat-page   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs
`uvicorn main:app` in this folder with the venv's Python, so there's nothing to activate. Ctrl+C stops the
server. Then open the page as in Step 6.

---

## 🧪 Testing

```bash
python -m pytest -m "not live"       # 55 passed, 9 deselected  (add -v for one line per test)
```

The plain tests use stand-ins for Gemini, so they need no key and make no calls. For the page, they check that it's
served at `/` and `/index.html` as HTML, with `Cache-Control: no-cache`, and that it calls `/api/query` and
`/api/stats`; and that it handles an unexpected status and never puts the server's text in as HTML. For the API, they
check each route, the 422 for a bad question, the 502 for a failed answer, with the traceback in the log, and that
with no key the server stops with the message, not a traceback. For `pipeline.py`, they check the engine and its
parts, as in 09, and that `aquery()` gives what `query()` gives; that it builds the engine, then answers each
question, or one of your own; and that no other file runs anything in the terminal.

The 9 deselected tests are live tests, marked `live`: they call the real Gemini, so they need your key in `.env`;
with no key, `tests/conftest.py` skips them, so plain `python -m pytest` runs only the others. Together they embed
176 texts, more than the free tier's limit of 100 a minute, so on the free tier, run them in three goes, a minute
apart: `python -m pytest -m live tests/test_main.py` (29 texts), then
`python -m pytest -m live -k answer tests/test_pipeline.py` (59), then
`python -m pytest -m live -k "not answer" tests/test_pipeline.py` (88).

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

### 5. The Code in One File, the Server and the Helpers Apart

```python
from pipeline import RAGEngine                     # main.py: the server's engine, from pipeline.py
from config import MissingKeyError, load_api_key   # pipeline.py: checks the key, before the models are built
from utils import print_result                     # pipeline.py: a helper, showing each answer in the terminal
```

`pipeline.py` holds the project's code, as in 09: the settings, the parts from the loader to the prompt, `RAGEngine`
and `main()`, the terminal's way in (`python pipeline.py`). Three files stay apart. `main.py` is the server's way in
(`uvicorn main:app`): it makes the engine, builds it at start-up, serves the page and answers each request with the
engine. `utils.py` holds `print_result()`, which needs nothing from `pipeline.py`. `config.py` holds the key check,
because the tests need it before `pipeline.py` is imported: `tests/conftest.py` asks it whether there's a real key,
and gives the models a fake one when there isn't.

---

## 🛠️ Troubleshooting

**Issue**: `.venv\Scripts\Activate.ps1 cannot be loaded because running scripts is disabled on this system.`
**Fix**: Windows PowerShell blocks scripts until you allow them. Allow local ones once, with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or for this window only, with
`Set-ExecutionPolicy -Scope Process Bypass`, then activate again (Step 2). The one command needs no activating.

**Issue**: The terminal shows `GoogleGenerativeAIError: Error embedding content (INVALID_ARGUMENT): 400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'API key not valid. Please pass a valid API key.', ...`, and the server doesn't start
**Fix**: Gemini didn't accept the key in `.env`. Copy it again from the Google Cloud console, with nothing before or
after it.

**Issue**: An error with `403 PERMISSION_DENIED` in it
**Fix**: Google refused the key for this service. In the Google Cloud console, open the key: under API restrictions
it should list the Gemini API (the Generative Language API), not Gemini for Google Cloud API, and under
Application restrictions, None. New settings can take up to 5 minutes to work.

**Issue**: `GoogleGenerativeAIError: Error embedding content (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, ...`
**Fix**: Your key has used its quota. On the free tier, that's 100 embedded texts a minute; starting the server
embeds 28, and each question 1 more. The message ends with "Please retry in" and a number of seconds. Wait that
long, then try again.

**Issue**: The terminal shows `Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).`, and the server doesn't start
**Fix**: The server stops at once. Put your key in `.env` (Step 4), and start it again.

**Issue**: `Can't build the models: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Replace it with your key.

**Issue**: `Can't build the models: .env isn't saved as UTF-8 text. Open it in an editor and save it with UTF-8 encoding.`
**Fix**: `.env` was saved in another encoding, often UTF-16 by Windows PowerShell 5's `echo ... > .env`. Save it
again as UTF-8, or make it with `copy .env.example .env` and edit it.

**Issue**: `ModuleNotFoundError: No module named 'langchain_core'` (or another of the packages)
**Fix**: The venv isn't active, or the packages aren't installed in it. Activate it (Step 2), then
`pip install -r requirements-dev.txt` (Step 3).

**Issue**: An error with `[Errno 10048]` or `address already in use` in it, and the server stops
**Fix**: Another server, often another project's, already has port 8000. Stop it (Ctrl+C in its terminal), or
start this one on another port, `uvicorn main:app --port 8001`, and use 8001 in the address.

**Issue**: `uvicorn` isn't found: PowerShell says it `is not recognized`, bash says `command not found`
**Fix**: The venv isn't active, so its `uvicorn` isn't on the path. Activate it (Step 2), or use the one command,
which needs no activating.

**Issue**: The page shows `... The server's terminal says why.`
**Fix**: The question couldn't be answered. The server's terminal has a `Couldn't answer:` line with the reason,
then the traceback.

**Issue**: The page shows `Something went wrong: ...`
**Fix**: The server isn't running, or it answered with an error the page didn't expect. Check the server's terminal.

**Issue**: http://127.0.0.1:8000 doesn't open in Codespaces
**Fix**: `127.0.0.1` is your own computer. Open the **Ports** tab next to **Terminal** and click the globe icon on
port 8000.

---

## 💡 Ideas to Try

- Click **Ask** with an empty box, and read the message the page shows.
- Ask three questions, and see the newest answer appear at the top.
- Ask "How do I fix VPN connection timeouts?", then "and if that doesn't work?": the second question arrives on its
  own, so the search has nothing about VPNs to go on.
- Change the question in the box's `value` in `index.html`, reload the page, and see the new default question.
