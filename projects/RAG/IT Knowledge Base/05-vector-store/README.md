# 05 · Vector store

## What it does

A vector database stores vectors and finds the ones closest to a question's vector. This step uses Qdrant, running
inside the Python process ("in memory"): there's no server and nothing to install, and everything in it is gone when
the program ends.

`vector_store.py`:

- makes a collection, `it_knowledge_base`, for vectors of 768 numbers compared by cosine similarity, and wraps it in
  LangChain's `QdrantVectorStore`;
- loads the articles, cuts them into step 03's 28 chunks and adds them: Gemini embeds every chunk, and each one is
  stored as a point with its vector, its text and its labels;
- searches: it embeds the question and gets back the 5 closest chunks, with their scores.

```text
28 chunks  ->  Gemini: 768 numbers each  ->  Qdrant, in memory  ->  a question's 5 closest chunks
```

Each run makes 2 calls to Gemini: one for all 28 chunks, one for the question.

## How to run it

You need Python 3.11 or newer, and a Gemini API key.

```bash
cd "projects/RAG/IT Knowledge Base/05-vector-store"   # from the repo root; the quotes are for the spaces
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
pip install -r requirements-dev.txt  # once: the packages and pytest, into .venv/
cp .env.example .env                 # once (Windows PowerShell or Command Prompt: copy .env.example .env)
python vector_store.py
```

Creating the venv, installing and making `.env` are once only; activate the venv again in every new terminal.

**Your key:** open `.env` in an editor and put your key after `GOOGLE_API_KEY=` (`tutorials/09-gemini-key` shows how
to make one). `.env` is in `.gitignore`, so your key never goes into git. Without a key, the script stops with:

```text
Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).
```

`python vector_store.py` prints how many chunks it stored, then the 5 chunks closest to the question: each one's
score, its article and where in the article it starts. The parts in `< >` come from Gemini:

```text
28 chunks stored in the collection 'it_knowledge_base'

The 5 chunks closest to "My VPN won't connect":
  <score>  <article title>, from character <start_index>
  ...
```

To ask your own question, put it after the script's name:

```bash
python vector_store.py "lost printer"
```

To run the tests:

```bash
python -m pytest                     # 19 passed, 2 skipped
```

The 2 skipped tests are live tests: they call the real Gemini, so they run only when your key is set.
