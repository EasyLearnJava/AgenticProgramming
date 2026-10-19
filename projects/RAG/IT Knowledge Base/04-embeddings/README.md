# 04 · Embeddings

## What it does

An embedding model turns a text into a vector: a list of numbers that stands for its meaning. Texts with close
meanings get vectors that point in close directions, which is what will let a search find chunks by meaning later.

`embed_chunks.py` sends step 03's 28 chunks to Gemini's embedding model, `gemini-embedding-001`, in one call, and gets
back 768 numbers for each chunk:

- Only each chunk's text (`page_content`) is sent. Its labels (`metadata`) aren't embedded.
- `embed_documents()` tells Gemini the texts are documents to be found (`RETRIEVAL_DOCUMENT`).
- The vectors come back in the chunks' order: vector 1 belongs to chunk 1, and so on.

This is the third step of getting the knowledge base ready to be searched: load, chunk, embed. There's no question
here. Step 05 stores the vectors, and the user's question first comes in at step 06.

```text
10 articles  ->  28 chunks  ->  Gemini: 768 numbers each  ->  28 vectors
```

- `config.py` checks your Gemini API key first, the same way as in the tutorials.
- `models.py` makes the embedding model.
- `embed_chunks.py` embeds the chunks and prints what came back.

This is the first step that needs a Gemini API key. Each run makes 1 call to Gemini, for all 28 chunks.

## How to run it

You need Python 3.11 or newer, and a Gemini API key.

```bash
cd "projects/RAG/IT Knowledge Base/04-embeddings"   # from the repo root; the quotes are for the spaces
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
pip install -r requirements-dev.txt  # once: the packages and pytest, into .venv/
cp .env.example .env                 # once (Windows PowerShell or Command Prompt: copy .env.example .env)
python embed_chunks.py
```

Creating the venv, installing and making `.env` are once only; activate the venv again in every new terminal.

**Your key:** open `.env` in an editor and put your key after `GOOGLE_API_KEY=` (`tutorials/09-gemini-key` shows how
to make one). `.env` is in `.gitignore`, so your key never goes into git. Without a key, the script stops with:

```text
Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).
```

If `.env` still says `your-key-here`, it stops with `GOOGLE_API_KEY is still the placeholder from .env.example: put
your real key in .env.` instead.

`python embed_chunks.py` prints how many vectors came back, then every chunk, one line each: where it comes from, how
many numbers its vector has, and the first 5 of them. The numbers in `< >` come from Gemini:

```text
28 chunks -> 28 vectors (gemini-embedding-001)

Chunk 1 of 28: VPN Connection Timeout, from character 0 -> 768 numbers: [<the first 5 numbers>, ...]
Chunk 2 of 28: VPN Connection Timeout, from character 459 -> 768 numbers: [<the first 5 numbers>, ...]
Chunk 3 of 28: MFA Setup Failure, from character 0 -> 768 numbers: [<the first 5 numbers>, ...]
...
Chunk 28 of 28: Microsoft Teams Audio Issues, from character 581 -> 768 numbers: [<the first 5 numbers>, ...]
```

On their own, the numbers don't tell you anything: what matters is how close two vectors point. Step 06 uses that to
compare a question with these chunks.

To run the tests:

```bash
python -m pytest                     # 18 passed, 2 skipped
```

The 2 skipped tests are live tests: they call the real Gemini, so they run only when your key is set.
