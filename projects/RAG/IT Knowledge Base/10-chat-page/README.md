# 10 · Chat page

## What it does

This step adds a web page to step 09's server: `index.html`, a page to ask questions in. `main.py` serves it at
http://127.0.0.1:8000, from the same server as the API.

- When the page opens, it shows one line about the knowledge base, from `GET /api/stats`.
- You type a question and click **Ask** (or press Enter). The page sends it to `POST /api/query` and shows the answer
  with its sources, newest first.
- If the question is bad or Gemini doesn't answer, the page shows what went wrong.

```text
the page  ->  POST /api/query  ->  the RAG engine  ->  the answer and its sources, on the page
```

## How to run it

You need Python 3.11 or newer, and a Gemini API key.

```bash
cd "projects/RAG/IT Knowledge Base/10-chat-page"   # from the repo root; the quotes are for the spaces
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

The server prints the same lines as in step 09, ending with `RAG engine built: 10 articles, 28 chunks` and
`Application startup complete.` Then open http://127.0.0.1:8000. The page starts with this line:

```text
10 articles in 28 chunks. Answers by gemini-3.5-flash-lite, search by gemini-embedding-001, 5 chunks per question.
```

The question box already holds `How do I fix VPN connection timeouts?`: click **Ask**. Each question makes 2 calls to
Gemini. The answer shows up under the box: your question, Gemini's answer, then **Sources:** with up to 3 articles,
each with its system, category and the start of its text.

In GitHub Codespaces, `127.0.0.1` is your own computer, not the codespace: open the **Ports** tab next to
**Terminal** and click the globe icon on port 8000.

The API from step 09 is still there, at the same addresses: `/docs`, `/api/query`, `/api/stats` and `/api/health`.

To run the tests:

```bash
python -m pytest                     # 51 passed, 7 skipped
```

The 7 skipped tests are live tests: they call the real Gemini, so they run only when your key is set.
