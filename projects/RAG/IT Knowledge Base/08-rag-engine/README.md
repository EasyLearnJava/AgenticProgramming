# 08 · RAG engine

## What it does

This step puts steps 02 to 07 in one class, `RAGEngine`, the way the server in step 09 will use them:

- `build()` runs once: it loads the articles, cuts them into chunks, embeds and stores them, and makes the chain.
- `query(question)` then answers a question: the answer, plus up to 3 sources. Each source is a different article,
  with its title, system, category and the start of the chunk's text.
- `stats()` says what the engine holds (10 articles, 28 chunks) and how it's set up.

```text
build(), once:          articles -> chunks -> Gemini -> Qdrant -> the chain
query(), each question: question -> the chain -> answer + up to 3 sources
```

The script builds the engine and answers the three sample questions. Each run makes 7 calls to Gemini: one for the
chunks, then two for each question (its embedding and its answer).

## How to run it

You need Python 3.11 or newer, and a Gemini API key.

```bash
cd "projects/RAG/IT Knowledge Base/08-rag-engine"   # from the repo root; the quotes are for the spaces
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
pip install -r requirements-dev.txt  # once: the packages and pytest, into .venv/
cp .env.example .env                 # once (Windows PowerShell or Command Prompt: copy .env.example .env)
python rag_engine.py
```

Creating the venv, installing and making `.env` are once only; activate the venv again in every new terminal.

**Your key:** open `.env` in an editor and put your key after `GOOGLE_API_KEY=` (`tutorials/09-gemini-key` shows how
to make one). `.env` is in `.gitignore`, so your key never goes into git. Without a key, the script stops with:

```text
Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).
```

`python rag_engine.py` prints what it built, then each question (`Q:`), its answer (`A:`) and its sources. The parts
in `< >` come from Gemini:

```text
Built: 10 articles, 28 chunks

Q: How do I fix VPN connection timeouts?
A: <Gemini's answer>
   source: <article title> (<system>, <category>)
   ...

Q: I can't set up MFA on my mobile device
A: <Gemini's answer>
   ...

Q: My laptop is running very slow
A: <Gemini's answer>
   ...
```

To ask your own question, put it after the script's name:

```bash
python rag_engine.py "printer not found"
```

To run the tests:

```bash
python -m pytest                     # 39 passed, 6 skipped
```

The 6 skipped tests are live tests: they call the real Gemini, so they run only when your key is set.
