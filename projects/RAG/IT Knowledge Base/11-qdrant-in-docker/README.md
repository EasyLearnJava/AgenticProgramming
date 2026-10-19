# 11 · Qdrant in Docker

## What it does

Until now, Qdrant ran inside the Python process: every start embedded all 28 chunks again (a call to Gemini), and
they were gone when the program ended. This step runs Qdrant as a server of its own, in Docker, which keeps the chunks
on disk between runs.

- `docker-compose.yml` starts the Qdrant server (`qdrant/qdrant:v1.19.1`) on port 6333, with its data in a Docker
  volume.
- `.env` says where the server is: `QDRANT_URL=http://localhost:6333`.
- Each chunk gets an id made from its text. When the engine builds, it checks what the server holds. If it's exactly
  these 28 chunks, the engine reuses them, with no call to Gemini. If not (the first run, or after an article changed),
  it stores them anew.

The engine, the API and the chat page work as in step 10.

```text
first run:   28 chunks  ->  Gemini  ->  the Qdrant server, which keeps them
later runs:  the Qdrant server already holds them  ->  no call to Gemini for the chunks
```

## How to run it

You need Python 3.11 or newer, a Gemini API key, and Docker (Docker Desktop on Windows and macOS; GitHub Codespaces
has Docker already).

```bash
cd "projects/RAG/IT Knowledge Base/11-qdrant-in-docker"   # from the repo root; the quotes are for the spaces
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
pip install -r requirements-dev.txt  # once: the packages and pytest, into .venv/
cp .env.example .env                 # once (Windows PowerShell or Command Prompt: copy .env.example .env)
docker compose up -d                 # start the Qdrant server, in the background
python rag_engine.py                 # the three sample questions
uvicorn main:app --reload            # or the server and the chat page; Ctrl+C stops it
```

Creating the venv, installing and making `.env` are once only; activate the venv again in every new terminal.

**Your key:** open `.env` in an editor and put your key after `GOOGLE_API_KEY=` (`tutorials/09-gemini-key` shows how
to make one). `.env` is in `.gitignore`, so your key never goes into git. Leave the `QDRANT_URL` line as it is.

**Qdrant:** `docker compose up -d` starts the server and leaves it running, even after you close the terminal. The
first time, Docker downloads the Qdrant image. Qdrant's own dashboard is at http://localhost:6333/dashboard. To stop
it, run `docker compose down` in this folder: the stored chunks stay for next time (`docker compose down -v` deletes
them too).

The first `python rag_engine.py` embeds the chunks and stores them in the server:

```text
Built: 10 articles, 28 chunks (embedded and stored) in Qdrant at http://localhost:6333
```

Every run after that finds them there:

```text
Built: 10 articles, 28 chunks (already stored, reused) in Qdrant at http://localhost:6333
```

Then come the questions and answers, as in step 08. `uvicorn main:app --reload` builds the engine the same way; then
open http://127.0.0.1:8000 for the chat page, as in step 10.

If Qdrant isn't running, the server stops at start-up with this message (the part in `< >` is the connection error):

```text
RuntimeError: Can't reach Qdrant at http://localhost:6333 (<the connection error>). Start it first, in this folder:   docker compose up -d
```

`python rag_engine.py` stops too, with a long error that ends in `ResponseHandlingException` and the connection error.
Either way: run `docker compose up -d`, then try again.

To run the tests (they don't need Docker):

```bash
python -m pytest                     # 55 passed, 7 skipped
```

The 7 skipped tests are live tests: they call the real Gemini, so they run only when your key is set.
