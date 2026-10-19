# 05 · Vector store

## What it does

A vector database stores vectors so that they can be searched later. This step stores the 28 chunks in Qdrant,
running inside the Python process ("in memory"): there's no server and nothing to install, and everything in it is
gone when the program ends (step 11 changes that).

`vector_store.py`:

- makes a collection, `it_knowledge_base` (Qdrant's word for a table of points), for vectors of 768 numbers compared
  by cosine similarity: how closely two vectors point the same way;
- loads the articles, cuts them into step 03's 28 chunks and adds them through LangChain's `QdrantVectorStore`.
  `add_documents()` embeds them, with the same call as step 04, and stores each chunk as a point: an id, its vector,
  and a payload with its text (`page_content`) and its labels (`metadata`);
- reads the points back from Qdrant and prints them, to show what was stored.

This is the last step of getting the knowledge base ready to be searched: load, chunk, embed, store. There's still no
question here: the search starts in step 06.

```text
28 chunks  ->  Gemini: 768 numbers each  ->  Qdrant, in memory: 28 points (vector + text + labels)
```

Each run makes 1 call to Gemini, for all 28 chunks. It embeds them again rather than using step 04's vectors, because
each project runs on its own, from the CSV.

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

`python vector_store.py` prints the collection's settings, then every stored point, one line each: its article, where
in the article the chunk starts, its vector's size, its text's length and how many labels it has. Gemini's numbers
aren't printed, so this is exactly what you'll see:

```text
Collection 'it_knowledge_base': 28 points, vectors of 768 numbers, compared by Cosine
Each point holds an id, a vector and a payload with metadata, page_content

Point 1 of 28: VPN Connection Timeout, from character 0: 768 numbers, 457 characters of text, 7 labels
Point 2 of 28: VPN Connection Timeout, from character 459: 768 numbers, 110 characters of text, 7 labels
Point 3 of 28: MFA Setup Failure, from character 0: 768 numbers, 144 characters of text, 7 labels
...
Point 28 of 28: Microsoft Teams Audio Issues, from character 581: 768 numbers, 118 characters of text, 7 labels
```

The 7 labels are the article's 6 from step 02 (`doc_id`, title, system, category, priority, tags), plus
`start_index` from step 03.

To run the tests:

```bash
python -m pytest                     # 20 passed, 2 skipped
```

The 2 skipped tests are live tests: they call the real Gemini, so they run only when your key is set.
