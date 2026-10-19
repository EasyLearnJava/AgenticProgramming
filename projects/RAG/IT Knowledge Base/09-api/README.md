# 09 · API

## What it does

This step puts the RAG engine behind a web server, with FastAPI, so that any program can ask it questions over HTTP.
`main.py` builds the engine once, when the server starts (one call to Gemini for the chunks), then answers requests:

| Request | What it gives back |
|---|---|
| `POST /api/query` with `{"question": "..."}` | the answer and up to 3 sources (2 calls to Gemini) |
| `GET /api/stats` | what the engine holds and how it's set up |
| `GET /api/health` | `{"status":"ok"}`: the server is up |

An empty or blank question, or one over 500 characters, gets a 422 error without calling Gemini. If Gemini doesn't
answer, the server sends a 502 error and prints the reason in its terminal.

```text
a program  ->  POST /api/query  ->  the RAG engine  ->  {"answer": ..., "sources": [...]}
```

## How to run it

You need Python 3.11 or newer, and a Gemini API key.

```bash
cd "projects/RAG/IT Knowledge Base/09-api"   # from the repo root; the quotes are for the spaces
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
pip install -r requirements-dev.txt  # once: the packages and pytest, into .venv/
cp .env.example .env                 # once (Windows PowerShell or Command Prompt: copy .env.example .env)
uvicorn main:app --reload            # the server; Ctrl+C stops it
```

Creating the venv, installing and making `.env` are once only; activate the venv again in every new terminal.

**Your key:** open `.env` in an editor and put your key after `GOOGLE_API_KEY=` (`tutorials/09-gemini-key` shows how
to make one). `.env` is in `.gitignore`, so your key never goes into git. Without a key, the server can't start, and
its terminal shows `Can't build the models: GOOGLE_API_KEY is not set.` and what to do: press Ctrl+C, put your key in
`.env`, and start it again.

`uvicorn main:app --reload` prints these lines, then waits for requests (the numbers in `[ ]` change each time):

```text
INFO:     Will watch for changes in these directories: ['...09-api']
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [16924] using StatReload
INFO:     Started server process [19312]
INFO:     Waiting for application startup.
INFO:     RAG engine built: 10 articles, 28 chunks
INFO:     Application startup complete.
```

`RAG engine built` means the chunks are embedded and stored: the server is ready.

**Try it in the browser:** open http://127.0.0.1:8000/docs, FastAPI's page for trying each route. Click a route, then
**Try it out**, then **Execute**.

**Or with curl**, in a second terminal (the server keeps the first one busy). These are for bash: macOS, Linux,
Codespaces and Git Bash.

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/stats
curl -X POST http://127.0.0.1:8000/api/query -H "Content-Type: application/json" -d '{"question": "How do I fix VPN connection timeouts?"}'
```

Their answers, one per line. The parts in `< >` come from Gemini:

```text
{"status":"ok"}
{"documents":10,"chunks":28,"collection":"it_knowledge_base","chunk_size":512,"chunk_overlap":50,"top_k":5,"embedding_model":"gemini-embedding-001","chat_model":"gemini-3.5-flash-lite"}
{"answer":"<Gemini's answer>","sources":[{"title":"<article title>","system":"<system>","category":"<category>","snippet":"<the start of the chunk's text>"},...]}
```

In GitHub Codespaces, the curl commands work as they are, in the codespace's terminal. In the browser, `127.0.0.1` is
your own computer, not the codespace: open the **Ports** tab next to **Terminal**, click the globe icon on port 8000,
and add `/docs` to the address it opens.

To run the tests:

```bash
python -m pytest                     # 44 passed, 7 skipped
```

The 7 skipped tests are live tests: they call the real Gemini, so they run only when your key is set.
